"""Offline regression checks for the public 2.1 tools; no live requests or home scan."""
import contextlib
import copy
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock
import urllib.error

ROOT = Path(__file__).resolve().parents[1]


def module(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / (name + ".py"))
    loaded = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(loaded)
    return loaded


coach = module("coachkit")
fetch = module("fetch_official")


class CoachingTests(unittest.TestCase):
    def setUp(self):
        self.games = coach.read_json(ROOT / "examples/question-chain/research-games.json")
        self.scenario = coach.read_json(ROOT / "examples/question-chain/scenario.json")

    def pair(self, output):
        return next(row for row in output["pairs"] if set(row["heroes"]) == {"赵云", "王昭君"})

    def test_research_demo_has_four_games_forty_picks_and_expected_pair(self):
        original = copy.deepcopy(self.games)
        result = coach.analyze(self.games, "纸鸢队")
        self.assertEqual((result["games_in_dataset"], result["lineups_in_dataset"]), (4, 8))
        self.assertEqual(sum(len(side["picks"]) for game in self.games["games"] for side in game["sides"]), 40)
        self.assertEqual(result["team_observations"], 4)
        self.assertEqual((result["wins"], result["losses"]), (2, 2))
        pair = self.pair(result)
        self.assertEqual((pair["appearances"], pair["wins"], pair["losses"]), (2, 1, 1))
        self.assertEqual(pair["sample_win_rate"], .5)
        self.assertEqual(result["dataset_kind"], "synthetic")
        self.assertIn("SYNTHETIC", result["notice"])
        self.assertEqual(original, self.games)

    def test_opposing_picks_never_count_as_teammates(self):
        self.games["games"][2]["sides"][1]["picks"] = ["项羽", "赵云", "王昭君", "后羿", "张飞"]
        filtered = coach.analyze(self.games, "纸鸢队")
        all_sides = coach.analyze(self.games)
        self.assertEqual(self.pair(filtered)["appearances"], 2)
        self.assertEqual(self.pair(all_sides)["appearances"], 3)

    def test_bans_never_enter_pair_counts(self):
        result = coach.analyze(self.games, "纸鸢队")
        self.assertFalse(any("澜" in pair["heroes"] or "镜" in pair["heroes"] for pair in result["pairs"]))
        self.assertEqual(sum(row["appearances"] for row in result["pairs"]), 40)

    def test_unknown_team_is_an_error(self):
        with self.assertRaises(ValueError):
            coach.analyze(self.games, "不存在的队")

    def test_duplicate_battle_rejected(self):
        self.games["games"].append(copy.deepcopy(self.games["games"][0]))
        with self.assertRaises(ValueError):
            coach.analyze(self.games)

    def test_conflicting_series_game_rejected(self):
        self.games["games"][1]["series_id"] = self.games["games"][0]["series_id"]
        with self.assertRaises(ValueError):
            coach.analyze(self.games)

    def test_every_side_must_have_five_distinct_picks(self):
        for picks in (["夏侯惇"] * 5, ["夏侯惇", "赵云", "王昭君", "狄仁杰"]):
            with self.subTest(picks=picks):
                data = copy.deepcopy(self.games)
                data["games"][0]["sides"][0]["picks"] = picks
                with self.assertRaises(ValueError):
                    coach.analyze(data)

    def test_sides_cannot_select_same_hero(self):
        self.games["games"][0]["sides"][1]["picks"][0] = "赵云"
        with self.assertRaises(ValueError):
            coach.analyze(self.games)

    def test_winner_must_be_one_of_two_sides(self):
        self.games["games"][0]["winner"] = "外部队伍"
        with self.assertRaises(ValueError):
            coach.analyze(self.games)

    def test_filtered_out_sides_are_still_validated(self):
        self.games["games"][3]["sides"][1]["picks"].pop()
        with self.assertRaises(ValueError):
            coach.analyze(self.games, "纸鸢队")

    def test_research_pick_cannot_also_be_banned(self):
        self.games["games"][0]["sides"][0]["bans"].append("赵云")
        with self.assertRaises(ValueError):
            coach.analyze(self.games)

    def test_unknown_schema_or_source_kind_fail(self):
        for key, value in (("schema_version", 99), ("schema_version", True),
                           ("dataset_kind", "official_certified"), ("unexpected", "field")):
            with self.subTest(key=key, value=value):
                data = copy.deepcopy(self.games)
                data[key] = value
                with self.assertRaises(ValueError):
                    coach.analyze(data)

    def test_full_bp_main_and_branch_pass_as_conditional_only(self):
        original = copy.deepcopy(self.scenario)
        result = coach.check_bp(self.scenario)
        self.assertTrue(result["checks_passed"])
        self.assertEqual(result["status"], "conditional_candidates")
        self.assertEqual(result["formal_match_legality"], "not_certified")
        self.assertEqual([row["games_checked"] for row in result["plans"]], [3, 3])
        self.assertEqual([row["distinct_own_heroes"] for row in result["plans"]], [15, 15])
        branch = self.scenario["branches"][0]["lineups"]
        self.assertEqual([row["picks"]["青禾"] for row in branch], ["牛魔", "太乙真人", "孙膑"])
        self.assertEqual(original, self.scenario)

    def test_missing_alias_rejected(self):
        del self.scenario["lineups"][0]["picks"]["青禾"]
        with self.assertRaises(ValueError):
            coach.check_bp(self.scenario)

    def test_hero_outside_players_pool_rejected(self):
        self.scenario["lineups"][0]["picks"]["青禾"] = "后羿"
        with self.assertRaises(ValueError):
            coach.check_bp(self.scenario)

    def test_duplicate_role_rejected(self):
        self.scenario["team"]["roster"][0]["role"] = "游走"
        with self.assertRaises(ValueError):
            coach.check_bp(self.scenario)

    def test_known_pool_hero_still_cannot_be_reused_across_games(self):
        self.scenario["lineups"][1]["picks"]["松石"] = "赵云"
        with self.assertRaises(ValueError):
            coach.check_bp(self.scenario)

    def test_branch_must_update_later_game_not_only_first_game(self):
        self.scenario["branches"][0]["lineups"][1]["picks"]["青禾"] = "牛魔"
        with self.assertRaises(ValueError):
            coach.check_bp(self.scenario)

    def test_supplied_ban_applies_to_branch(self):
        self.scenario["branches"][0]["lineups"][0]["picks"]["青禾"] = "张飞"
        with self.assertRaises(ValueError):
            coach.check_bp(self.scenario)

    def test_provided_opponent_pick_excludes_own_pick(self):
        self.scenario["lineups"][0]["opponent_picks"] = ["王昭君"]
        with self.assertRaises(ValueError):
            coach.check_bp(self.scenario)

    def test_incomplete_branch_is_rejected(self):
        self.scenario["branches"][0]["lineups"].pop()
        with self.assertRaises(ValueError):
            coach.check_bp(self.scenario)

    def test_cannot_claim_complete_tournament_certification(self):
        self.scenario["rules"]["complete_tournament_rules_verified"] = True
        with self.assertRaises(ValueError):
            coach.check_bp(self.scenario)

    def test_unknown_bp_fields_are_rejected(self):
        self.scenario["rules"]["guess_future_bans"] = True
        with self.assertRaises(ValueError):
            coach.check_bp(self.scenario)

    def test_training_budgets_are_positive_contiguous_and_exact(self):
        for minutes in (15, 30, 90, 135, 240, 480):
            with self.subTest(minutes=minutes):
                result = coach.training(minutes)
                phases = result["phases"]
                self.assertEqual(sum(phase["minutes"] for phase in phases), minutes)
                self.assertTrue(all(phase["minutes"] > 0 for phase in phases))
                self.assertEqual(phases[0]["start_minute"], 0)
                self.assertEqual(phases[-1]["end_minute"], minutes)
                self.assertTrue(all(a["end_minute"] == b["start_minute"] for a, b in zip(phases, phases[1:])))
        self.assertEqual([p["minutes"] for p in coach.training(90)["phases"]], [10, 15, 40, 17, 8])

    def test_invalid_training_budgets_fail(self):
        for value in (0, 14, 481, True, 90.5):
            with self.subTest(value=value), self.assertRaises(ValueError):
                coach.training(value)

    def test_json_rejects_duplicate_keys_and_nonfinite_numbers(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "bad.json"
            for raw in ('{"schema_version":1,"schema_version":2}', '{"x":NaN}'):
                path.write_text(raw)
                with self.assertRaises(ValueError):
                    coach.read_json(path)

    def test_cli_prints_no_success_json_on_bad_input(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "bad.json"
            path.write_text('{"schema_version":99}')
            out, err = io.StringIO(), io.StringIO()
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                code = coach.main(["analyze", str(path)])
            self.assertEqual(code, 2)
            self.assertEqual(out.getvalue(), "")
            self.assertIn("coachkit failed", err.getvalue())


class FakeResponse:
    def __init__(self, raw, status=200):
        self.raw, self.status = raw, status
        self.headers = {"Content-Type": "application/json"}
        self.requested_sizes = []

    def read(self, amount):
        self.requested_sizes.append(amount)
        return self.raw[:amount]

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class FakeOpener:
    def __init__(self, response=None, error=None):
        self.response, self.error, self.calls = response, error, []

    def open(self, request, timeout):
        self.calls.append((request.full_url, timeout))
        if self.error is not None:
            raise self.error
        return self.response


class FetchTests(unittest.TestCase):
    def setUp(self):
        self.raw = b'{"code":200,"data":[{"league_id":123}]}'

    def test_five_fixed_endpoints_use_single_eight_second_request(self):
        for name, (path, field) in fetch.ENDPOINTS.items():
            with self.subTest(endpoint=name):
                response = FakeResponse(self.raw)
                client = FakeOpener(response)
                raw, payload, meta = fetch.fetch_once(name, "123" if field else None, client)
                expected = fetch.BASE_URL + path + ("?" + field + "=123" if field else "")
                self.assertEqual(client.calls, [(expected, 8)])
                self.assertEqual(response.requested_sizes, [fetch.MAX_RESPONSE_BYTES + 1])
                self.assertEqual(raw, self.raw)
                self.assertEqual(meta["response_sha256"], hashlib.sha256(self.raw).hexdigest())
                self.assertEqual(meta["game_version"], "unknown")
                self.assertEqual(meta["request_count"], 1)
                self.assertEqual(payload["code"], 200)

    def test_ids_and_endpoints_cannot_be_arbitrary_urls(self):
        for endpoint, identifier in (("other", "1"), ("heroes", None),
                                     ("heroes", "1&x=2"), ("battle", "https://evil.invalid/"),
                                     ("matches", "0"), ("leagues", "1")):
            with self.subTest(endpoint=endpoint, identifier=identifier):
                client = FakeOpener(FakeResponse(self.raw))
                with self.assertRaises(ValueError):
                    fetch.fetch_once(endpoint, identifier, client)
                self.assertEqual(client.calls, [])

    def test_network_error_is_not_retried(self):
        client = FakeOpener(error=urllib.error.URLError("offline test"))
        with self.assertRaises(urllib.error.URLError):
            fetch.fetch_once("leagues", opener=client)
        self.assertEqual(len(client.calls), 1)

    def test_redirects_are_not_followed(self):
        self.assertIsNone(fetch.NoRedirect().redirect_request(None, None, 302, "redirect", {}, "https://evil.invalid"))

    def test_invalid_http_json_service_schema_and_size_are_rejected(self):
        for raw, status in ((self.raw, 503), (b'<html>error</html>', 200),
                            (b'{"code":403,"data":[]}', 200), (b'{"code":200,"data":"unknown"}', 200),
                            (b'{"code":200,"code":0,"data":[]}', 200),
                            (b'{"code":200,"data":[NaN]}', 200),
                            (b'x' * (fetch.MAX_RESPONSE_BYTES + 1), 200)):
            with self.subTest(status=status, size=len(raw)), self.assertRaises(ValueError):
                fetch.fetch_once("leagues", opener=FakeOpener(FakeResponse(raw, status)))

    def test_explicit_new_directory_preserves_raw_bytes_and_provenance(self):
        raw, _, meta = fetch.fetch_once("leagues", opener=FakeOpener(FakeResponse(self.raw)))
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "new-snapshot"
            paths = fetch.save_new_directory(output, raw, meta)
            self.assertEqual(Path(paths["response"]).read_bytes(), self.raw)
            saved = json.loads(Path(paths["provenance"]).read_text())
            self.assertEqual(saved["response_sha256"], hashlib.sha256(self.raw).hexdigest())
            with self.assertRaises(FileExistsError):
                fetch.save_new_directory(output, b"overwrite", meta)
            self.assertEqual(Path(paths["response"]).read_bytes(), self.raw)

    def test_cli_failure_creates_no_success_directory(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "never-created"
            with mock.patch.object(fetch, "fetch_once", side_effect=TimeoutError("offline timeout")) as mocked:
                out, err = io.StringIO(), io.StringIO()
                with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                    result = fetch.main(["leagues", "--output-dir", str(output)])
                self.assertEqual(result, 2)
                self.assertEqual(out.getvalue(), "")
                self.assertIn("no successful snapshot saved", err.getvalue())
                mocked.assert_called_once()
                self.assertFalse(output.exists())

    def test_existing_output_is_rejected_before_network(self):
        with tempfile.TemporaryDirectory() as temporary, mock.patch.object(fetch, "fetch_once") as mocked:
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                result = fetch.main(["leagues", "--output-dir", temporary])
            self.assertEqual(result, 2)
            mocked.assert_not_called()


if __name__ == "__main__":
    unittest.main()

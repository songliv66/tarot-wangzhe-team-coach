#!/usr/bin/env python3
"""Small, offline coaching checks. Python standard library only.

These checks describe supplied records; they do not certify their authenticity,
current game mechanics, player skill, or eligibility under complete match rules.
"""
import argparse
from collections import Counter
import itertools
import json
from pathlib import Path
import sys

MAX_INPUT_BYTES = 4 * 1024 * 1024
ROLES = ("对抗路", "打野", "中单", "发育路", "游走")
DATASET_KINDS = {"synthetic", "user_provided"}


def no_duplicate_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key: " + key)
        result[key] = value
    return result


def invalid_constant(value):
    raise ValueError("non-finite JSON number: " + value)


def read_json(path):
    path = Path(path)
    with path.open("rb") as stream:
        raw = stream.read(MAX_INPUT_BYTES + 1)
    if len(raw) > MAX_INPUT_BYTES:
        raise ValueError("input exceeds 4 MiB")
    return json.loads(raw.decode("utf-8-sig"), object_pairs_hook=no_duplicate_keys,
                      parse_constant=invalid_constant)


def object_fields(value, required, optional=(), label="object"):
    if not isinstance(value, dict):
        raise ValueError(label + " must be an object")
    missing = set(required) - value.keys()
    extra = value.keys() - set(required) - set(optional)
    if missing or extra:
        raise ValueError(f"{label}: missing fields {sorted(missing)}, unknown fields {sorted(extra)}")
    return value


def nonempty(value, label):
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise ValueError(label + " must be a nonempty, trimmed string")
    return value


def positive_int(value, label):
    if type(value) is not int or value < 1:
        raise ValueError(label + " must be a positive integer")
    return value


def strings(value, label, *, unique=True, minimum=0, maximum=100):
    if not isinstance(value, list) or not minimum <= len(value) <= maximum:
        raise ValueError(f"{label}: expected {minimum}..{maximum} items")
    for item in value:
        nonempty(item, label)
    if unique and len(set(value)) != len(value):
        raise ValueError(label + " contains duplicates")
    return value


def dataset_header(data, required, optional=()):
    object_fields(data, {"schema_version", "dataset_kind", *required},
                  {"description", "source_note", *optional}, "dataset")
    if type(data["schema_version"]) is not int or data["schema_version"] != 1:
        raise ValueError("unsupported schema_version; expected 1")
    if not isinstance(data["dataset_kind"], str) or data["dataset_kind"] not in DATASET_KINDS:
        raise ValueError("dataset_kind must be synthetic or user_provided")
    for key in ("description", "source_note"):
        if key in data:
            nonempty(data[key], key)


def data_notice(kind):
    if kind == "synthetic":
        return "SYNTHETIC: invented records, not real matches or official evidence."
    return "USER PROVIDED: supplied records; authenticity and current version are unverified."


def analyze(data, team=None):
    """Count pairs within each selected side, after validating every game."""
    dataset_header(data, {"games"})
    games = data["games"]
    if not isinstance(games, list) or not 1 <= len(games) <= 10000:
        raise ValueError("games must contain 1..10000 records")
    if team is not None:
        nonempty(team, "team filter")
    battle_ids, series_games = set(), set()
    pairs = Counter()
    pair_wins = Counter()
    observations = wins = selected_games = 0
    for game in games:
        object_fields(game, {"battle_id", "series_id", "game", "sides", "winner"}, label="game")
        battle_id = nonempty(game["battle_id"], "battle_id")
        series = nonempty(game["series_id"], "series_id")
        number = positive_int(game["game"], "game number")
        if battle_id in battle_ids or (series, number) in series_games:
            raise ValueError("duplicate battle_id or series/game")
        battle_ids.add(battle_id)
        series_games.add((series, number))
        sides = game["sides"]
        if not isinstance(sides, list) or len(sides) != 2:
            raise ValueError("each game needs exactly two sides")
        teams, all_picks, all_bans = [], [], []
        for side in sides:
            object_fields(side, {"team", "picks", "bans"}, label="side")
            teams.append(nonempty(side["team"], "team"))
            all_picks.extend(strings(side["picks"], "picks", minimum=5, maximum=5))
            all_bans.extend(strings(side["bans"], "bans", maximum=30))
        if len(set(teams)) != 2 or len(set(all_picks)) != 10:
            raise ValueError("sides must be different teams with ten distinct picks")
        if len(set(all_bans)) != len(all_bans) or set(all_bans) & set(all_picks):
            raise ValueError("duplicate bans or a picked hero is banned")
        if game["winner"] not in teams:
            raise ValueError("winner must name one of this game's teams")
        chosen = [side for side in sides if team is None or side["team"] == team]
        selected_games += bool(chosen)
        for side in chosen:
            observations += 1
            won = side["team"] == game["winner"]
            wins += won
            for pair in itertools.combinations(sorted(side["picks"]), 2):
                pairs[pair] += 1
                pair_wins[pair] += won
    if not observations:
        raise ValueError("team filter matched no side")
    return {
        "schema_version": 1, "dataset_kind": data["dataset_kind"],
        "notice": data_notice(data["dataset_kind"]), "team_filter": team,
        "games_in_dataset": len(games), "lineups_in_dataset": 2 * len(games),
        "selected_games": selected_games, "team_observations": observations,
        "wins": wins, "losses": observations - wins,
        "pairs": [{"heroes": list(pair), "appearances": count,
                   "wins": pair_wins[pair], "losses": count - pair_wins[pair],
                   "sample_win_rate": round(pair_wins[pair] / count, 4)}
                  for pair, count in sorted(pairs.items(), key=lambda item: (-item[1], item[0]))],
        "limits": ["Counts use one team-side per game; bans and opponents are not teammates.",
                   "Co-occurrence and sample wins do not establish causation or hero strength.",
                   "No current version, professional relevance, or amateur win rate is certified."],
    }


def check_bp(data):
    """Validate complete conditional plans, including every full alternative."""
    dataset_header(data, {"team", "rules", "lineups", "branches"})
    team = object_fields(data["team"], {"name", "roster"}, label="team")
    nonempty(team["name"], "team name")
    roster = team["roster"]
    if not isinstance(roster, list) or len(roster) != 5:
        raise ValueError("roster must contain exactly five players")
    pools, roles = {}, []
    for player in roster:
        object_fields(player, {"alias", "role", "heroes"}, label="player")
        alias = nonempty(player["alias"], "alias")
        if alias in pools:
            raise ValueError("duplicate roster alias")
        if player["role"] not in ROLES:
            raise ValueError("unknown role")
        roles.append(player["role"])
        pools[alias] = set(strings(player["heroes"], "hero pool", minimum=1, maximum=30))
    if set(roles) != set(ROLES):
        raise ValueError("roster must cover all five different roles")
    rules = object_fields(data["rules"], {
        "best_of", "own_heroes_no_repeat_across_games", "same_game_unique",
        "ban_scope", "complete_tournament_rules_verified"}, label="rules")
    best_of = positive_int(rules["best_of"], "best_of")
    if best_of > 9 or best_of % 2 != 1:
        raise ValueError("best_of must be an odd number from 1 to 9")
    if type(rules["own_heroes_no_repeat_across_games"]) is not bool:
        raise ValueError("own_heroes_no_repeat_across_games must be boolean")
    if rules["same_game_unique"] is not True or rules["ban_scope"] != "provided_only":
        raise ValueError("supported rules require same_game_unique=true and ban_scope=provided_only")
    if rules["complete_tournament_rules_verified"] is not False:
        raise ValueError("this checker cannot certify complete tournament rules")

    def plan(lineups, name):
        if not isinstance(lineups, list) or len(lineups) != best_of:
            raise ValueError(name + ": full plan must cover every possible game")
        numbers, used = [], set()
        for lineup in lineups:
            object_fields(lineup, {"game", "picks", "bans"}, {"opponent_picks"}, "lineup")
            numbers.append(positive_int(lineup["game"], "game number"))
            picks = lineup["picks"]
            if not isinstance(picks, dict) or set(picks) != set(pools):
                raise ValueError(name + ": picks must map all five roster aliases")
            selected = []
            for alias, hero in picks.items():
                nonempty(hero, "picked hero")
                if hero not in pools[alias]:
                    raise ValueError(name + ": hero is outside player's supplied pool: " + alias)
                selected.append(hero)
            if len(set(selected)) != 5:
                raise ValueError(name + ": same-game hero repetition")
            banned = set(strings(lineup["bans"], "provided bans", maximum=30))
            opponents = set(strings(lineup.get("opponent_picks", []), "provided opponent picks", maximum=5))
            if set(selected) & (banned | opponents) or banned & opponents:
                raise ValueError(name + ": a selected hero is banned or taken by the opponent")
            if rules["own_heroes_no_repeat_across_games"] and used & set(selected):
                raise ValueError(name + ": own hero reused across games")
            used.update(selected)
        if numbers != list(range(1, best_of + 1)):
            raise ValueError(name + ": games must be ordered 1..best_of")
        return {"name": name, "games_checked": best_of, "distinct_own_heroes": len(used)}

    plans = [plan(data["lineups"], "main")]
    branches = data["branches"]
    if not isinstance(branches, list) or len(branches) > 100:
        raise ValueError("branches must be a list of at most 100 complete plans")
    names = {"main"}
    for branch in branches:
        object_fields(branch, {"name", "condition", "lineups"}, label="branch")
        name = nonempty(branch["name"], "branch name")
        nonempty(branch["condition"], "branch condition")
        if name in names:
            raise ValueError("duplicate branch name")
        names.add(name)
        plans.append(plan(branch["lineups"], name))
    return {"schema_version": 1, "dataset_kind": data["dataset_kind"],
            "notice": data_notice(data["dataset_kind"]), "team": team["name"],
            "checks_passed": True, "status": "conditional_candidates",
            "formal_match_legality": "not_certified", "plans": plans,
            "limits": ["Only supplied pools, roles, picks, bans, and stated reuse rules were checked.",
                       "Future bans/picks, full organizer rules, version, and player proficiency remain unverified.",
                       "Each branch is a separate possible future, not additional games in the same series."]}


def training(minutes):
    if type(minutes) is not int or not 15 <= minutes <= 480:
        raise ValueError("minutes must be an integer from 15 to 480")
    weights = (10, 15, 40, 17, 8)
    allocated = [minutes * weight // 90 for weight in weights]
    order = sorted(range(5), key=lambda i: (-(minutes * weights[i] % 90), i))
    for i in order[:minutes - sum(allocated)]:
        allocated[i] += 1
    titles = ("目标与分工对齐", "关键片段暂停推演", "有界情景演练", "复盘一至两个关键点", "记录与下次任务")
    phases, cursor = [], 0
    for number, (title, duration) in enumerate(zip(titles, allocated), 1):
        phases.append({"phase": number, "title": title, "minutes": duration,
                       "start_minute": cursor, "end_minute": cursor + duration})
        cursor += duration
    return {"schema_version": 1, "total_minutes": minutes, "phases": phases,
            "limits": ["This is a time budget, not a promise of a fixed number of live games.",
                       "For a hard stop, use replay or bounded scenarios; match duration is not controllable.",
                       "Choose one or two observable training targets from the team's actual evidence."]}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    p = commands.add_parser("analyze", help="describe explicitly supplied research-game records")
    p.add_argument("json", type=Path)
    p.add_argument("--team")
    p = commands.add_parser("check-bp", help="check all complete conditional BP plans")
    p.add_argument("json", type=Path)
    p = commands.add_parser("train", help="scale a five-phase training time budget")
    p.add_argument("--minutes", required=True, type=int)
    args = parser.parse_args(argv)
    try:
        if args.command == "analyze":
            result = analyze(read_json(args.json), args.team)
        elif args.command == "check-bp":
            result = check_bp(read_json(args.json))
        else:
            result = training(args.minutes)
    except (OSError, ValueError, TypeError, KeyError, UnicodeError) as exc:
        print("coachkit failed: " + str(exc), file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""Retrieve one JSON response from a fixed public Tencent webpage endpoint.

Experimental webpage interfaces, not a stable developer API. One request only;
no credentials, retries, crawling, redirects, or game-version certification.
Defaults to stdout. --output-dir must name a new directory under an existing parent.
"""
import argparse
import datetime as dt
import hashlib
import http.client
import json
from pathlib import Path
import re
import sys
import urllib.error
import urllib.parse
import urllib.request

BASE_URL = "https://prod.comp.smoba.qq.com"
TIMEOUT_SECONDS = 8
MAX_RESPONSE_BYTES = 4 * 1024 * 1024
ENDPOINTS = {
    "leagues": ("/leaguesite/leagues/open", None),
    "heroes": ("/leaguesite/league/hero/settle_list/open", "league_id"),
    "matches": ("/leaguesite/matches/open", "league_id"),
    "battles": ("/leaguesite/match/battles/open", "match_id"),
    "battle": ("/leaguesite/battle/open", "battle_id"),
}


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def endpoint_url(endpoint, identifier=None):
    if endpoint not in ENDPOINTS:
        raise ValueError("unsupported endpoint")
    path, field = ENDPOINTS[endpoint]
    if field:
        if not isinstance(identifier, str) or not re.fullmatch(r"[1-9][0-9]{0,19}", identifier):
            raise ValueError(field + " must be an explicit positive numeric ID")
        return BASE_URL + path + "?" + urllib.parse.urlencode({field: identifier})
    if identifier is not None:
        raise ValueError("leagues does not accept an ID")
    return BASE_URL + path


def strict_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate response JSON key")
        result[key] = value
    return result


def bad_constant(value):
    raise ValueError("non-finite response JSON number: " + value)


def fetch_once(endpoint, identifier=None, opener=None):
    url = endpoint_url(endpoint, identifier)
    request = urllib.request.Request(url, headers={
        "User-Agent": "team-coach-open/2.1.0", "Accept": "application/json",
        "Referer": "https://pvp.qq.com/"})
    client = opener if opener is not None else urllib.request.build_opener(NoRedirect())
    with client.open(request, timeout=TIMEOUT_SECONDS) as response:
        status = response.status
        if status != 200:
            raise ValueError("unexpected HTTP status: " + str(status))
        raw = response.read(MAX_RESPONSE_BYTES + 1)
        content_type = response.headers.get("Content-Type", "unknown")
    if len(raw) > MAX_RESPONSE_BYTES:
        raise ValueError("response exceeds 4 MiB")
    payload = json.loads(raw.decode("utf-8-sig"), object_pairs_hook=strict_object,
                         parse_constant=bad_constant)
    if (not isinstance(payload, dict) or type(payload.get("code")) is not int
            or payload["code"] not in (0, 200)):
        raise ValueError("unrecognized response envelope or service error code")
    if not isinstance(payload.get("data", payload.get("results")), (dict, list)):
        raise ValueError("unrecognized data/results schema")
    metadata = {
        "schema_version": 1, "record_kind": "public_endpoint_snapshot",
        "source_url": url, "endpoint": endpoint,
        "retrieved_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "http_status": status, "request_timeout_seconds": TIMEOUT_SECONDS,
        "request_count": 1, "response_bytes": len(raw),
        "response_sha256": hashlib.sha256(raw).hexdigest(),
        "content_type": content_type, "game_version": "unknown",
        "event_time_range": "unknown",
        "limits": ["Raw public webpage response; endpoint stability and permission may change.",
                   "The hash records retrieved bytes, not a Tencent signature or truth certification.",
                   "Retrieval time is not game version, match completion time, or historical cutoff.",
                   "Eight seconds is the socket/request timeout, not a guaranteed total wall-clock deadline."],
    }
    return raw, payload, metadata


def save_new_directory(directory, raw, metadata):
    directory = Path(directory).expanduser()
    directory.mkdir(mode=0o700, parents=False, exist_ok=False)
    created = []
    try:
        for name, content in (
                ("response.json", raw),
                ("provenance.json", (json.dumps(metadata, ensure_ascii=False, indent=2,
                                                allow_nan=False) + "\n").encode("utf-8"))):
            path = directory / name
            with path.open("xb") as stream:
                created.append(path)
                stream.write(content)
    except BaseException:
        for path in reversed(created):
            path.unlink(missing_ok=True)
        directory.rmdir()
        raise
    return {"response": str((directory / "response.json").resolve()),
            "provenance": str((directory / "provenance.json").resolve())}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="endpoint", required=True)
    for endpoint, (_path, field) in ENDPOINTS.items():
        p = sub.add_parser(endpoint)
        if field:
            p.add_argument("--" + field.replace("_", "-"), dest="identifier", required=True)
        p.add_argument("--output-dir", type=Path, help="new directory; existing paths are never overwritten")
    args = parser.parse_args(argv)
    try:
        if args.output_dir is not None and args.output_dir.expanduser().exists():
            raise FileExistsError("output directory already exists")
        raw, payload, metadata = fetch_once(args.endpoint, getattr(args, "identifier", None))
        if args.output_dir is None:
            output = {"schema_version": 1, "source": metadata, "payload": payload}
        else:
            paths = save_new_directory(args.output_dir, raw, metadata)
            output = {"saved": True, "files": paths, "source": metadata}
    except (OSError, ValueError, TypeError, UnicodeError, http.client.HTTPException) as exc:
        print("fetch failed (no successful snapshot saved): " + str(exc), file=sys.stderr)
        return 2
    print(json.dumps(output, ensure_ascii=False, indent=2, allow_nan=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())

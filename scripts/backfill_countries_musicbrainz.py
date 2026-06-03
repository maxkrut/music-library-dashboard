#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from build_readme import (
    MUSICBRAINZ_ARTIST_CACHE,
    TRACKS_CSV,
    all_artists,
    country_from_artist_data,
    norm,
    read_tracks,
)
from enrich_genres_musicbrainz import (
    DEFAULT_USER_AGENT,
    ROOT,
    MusicBrainzClient,
    load_dotenv,
    query_artist,
    read_json,
    resolve_path,
    write_json,
)


def parse_args() -> argparse.Namespace:
    load_dotenv(ROOT / ".env")
    parser = argparse.ArgumentParser(
        description="Backfill country and area fields in the MusicBrainz artist cache."
    )
    parser.add_argument("--artist-cache", type=Path, default=MUSICBRAINZ_ARTIST_CACHE)
    parser.add_argument("--tracks", type=Path, default=TRACKS_CSV)
    parser.add_argument("--sleep", type=float, default=1.1)
    parser.add_argument("--retries", type=int, default=20)
    parser.add_argument("--min-score", type=int, default=90)
    parser.add_argument("--user-agent", default=DEFAULT_USER_AGENT)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--retry-checked", action="store_true")
    parser.add_argument(
        "--fetch-missing-artists",
        action="store_true",
        help="Query MusicBrainz for artists present in tracks.csv but absent from the artist cache.",
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--offline", action="store_true")
    parser.add_argument("--verbose", action="store_true")
    return parser.parse_args()


def needs_country(data: Any) -> bool:
    return isinstance(data, dict) and data.get("matched") and not country_from_artist_data(data)


def artist_path(artist_id: str) -> str:
    return f"/artist/{artist_id}"


def wikidata_id_from_relations(relations: list[dict[str, Any]]) -> str:
    for relation in relations:
        target = ((relation.get("url") or {}).get("resource") or "").rstrip("/")
        if "wikidata.org/wiki/" not in target:
            continue
        return target.rsplit("/", 1)[-1]
    return ""


def wikidata_country(entity_id: str) -> str:
    if not entity_id:
        return ""
    query = f"""
SELECT ?countryLabel WHERE {{
  wd:{entity_id} (wdt:P495|wdt:P27|wdt:P740/wdt:P17) ?country.
  SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en". }}
}}
LIMIT 1
"""
    url = "https://query.wikidata.org/sparql?" + urllib.parse.urlencode(
        {"query": query, "format": "json"}
    )
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": DEFAULT_USER_AGENT,
            "Accept": "application/sparql-results+json",
        },
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        payload = json.loads(response.read().decode("utf-8"))
    bindings = payload.get("results", {}).get("bindings", [])
    if not bindings:
        return ""
    return bindings[0].get("countryLabel", {}).get("value", "")


def console_text(value: object) -> str:
    return str(value).encode("ascii", errors="backslashreplace").decode("ascii")


def country_missing_keys(
    artist_cache: dict[str, Any], retry_checked: bool, limit: int
) -> list[str]:
    keys = [
        key
        for key, data in sorted(artist_cache.items())
        if needs_country(data)
        and isinstance(data, dict)
        and data.get("artist_id")
        and (retry_checked or not data.get("country_checked_at"))
    ]
    return keys[:limit] if limit else keys


def country_missing_without_id(artist_cache: dict[str, Any]) -> list[str]:
    return [
        key
        for key, data in sorted(artist_cache.items())
        if needs_country(data) and isinstance(data, dict) and not data.get("artist_id")
    ]


def main() -> None:
    args = parse_args()
    artist_cache_path = resolve_path(args.artist_cache)
    tracks_path = resolve_path(args.tracks)
    artist_cache: dict[str, Any] = read_json(artist_cache_path, {})
    tracks = read_tracks(tracks_path) if tracks_path.exists() else []

    absent_artists: list[str] = []
    if args.fetch_missing_artists and tracks:
        artists = sorted({artist for row in tracks for artist in all_artists(row)}, key=str.casefold)
        absent_artists = [artist for artist in artists if norm(artist) not in artist_cache]

    missing_keys = country_missing_keys(artist_cache, args.retry_checked, args.limit)
    missing_without_id = country_missing_without_id(artist_cache)
    if args.limit:
        absent_artists = absent_artists[: args.limit]

    print(f"Artists absent from MusicBrainz cache: {len(absent_artists)}")
    print(f"Artists missing country with MusicBrainz ID: {len(missing_keys)}")
    print(f"Artists missing country without MusicBrainz ID: {len(missing_without_id)}")
    if args.dry_run:
        print("Dry run only; cache was not written.")
        return
    if args.offline:
        print("Offline mode; cache was not written.")
        return

    client = MusicBrainzClient(args.user_agent, args.sleep, args.retries)
    fetched_absent = 0
    for index, artist in enumerate(absent_artists, start=1):
        key = norm(artist)
        artist_cache[key] = query_artist(client, artist, args.min_score)
        fetched_absent += 1
        write_json(artist_cache_path, artist_cache)
        if args.verbose:
            status = "matched" if artist_cache[key].get("matched") else "missed"
            country = country_from_artist_data(artist_cache[key]) or "missing"
            print(
                console_text(
                    f"absent {index}/{len(absent_artists)} {status} {artist}: {country}"
                ),
                flush=True,
            )
        if index % 25 == 0:
            write_json(artist_cache_path, artist_cache)

    if fetched_absent:
        write_json(artist_cache_path, artist_cache)
        missing_keys = country_missing_keys(artist_cache, args.retry_checked, args.limit)
        missing_without_id = country_missing_without_id(artist_cache)

    changed = 0
    still_missing = 0
    for index, key in enumerate(missing_keys, start=1):
        data = artist_cache.get(key) or {}
        artist_id = str(data.get("artist_id") or "")
        payload = client.request(artist_path(artist_id), {"inc": "url-rels"})
        wikidata_id = wikidata_id_from_relations(payload.get("relations", []) or [])
        wikidata_origin = ""
        if wikidata_id and not (payload.get("country") or payload.get("area")):
            try:
                wikidata_origin = wikidata_country(wikidata_id)
            except Exception as error:  # noqa: BLE001
                if args.verbose:
                    print(console_text(f"Wikidata failed for {key}: {error}"), flush=True)
        updated = {
            **data,
            "country": payload.get("country", data.get("country", "")),
            "area": payload.get("area") or data.get("area") or {},
            "begin_area": payload.get("begin-area") or data.get("begin_area") or {},
            "end_area": payload.get("end-area") or data.get("end_area") or {},
            "life_span": payload.get("life-span") or data.get("life_span") or {},
            "wikidata_id": wikidata_id or data.get("wikidata_id", ""),
            "wikidata_origin": wikidata_origin or data.get("wikidata_origin", ""),
            "country_checked_at": int(time.time()),
        }
        artist_cache[key] = updated
        if country_from_artist_data(updated):
            changed += 1
        else:
            still_missing += 1

        if args.verbose:
            name = data.get("name") or key
            country = country_from_artist_data(updated) or "missing"
            print(console_text(f"{index}/{len(missing_keys)} {name}: {country}"), flush=True)
        if index % 25 == 0:
            write_json(artist_cache_path, artist_cache)
            print(
                f"Checked {index}/{len(missing_keys)} artists; filled {changed}; still missing {still_missing}.",
                flush=True,
            )

    write_json(artist_cache_path, artist_cache)
    print(f"Filled countries for {changed} artists.")
    print(f"Still missing after lookup: {still_missing + len(missing_without_id)} artists.")
    print(f"Wrote {artist_cache_path}.")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import os
import socket
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from pathlib import Path
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[1]
TRACKS_CSV = ROOT / "data" / "tracks.csv"
CACHE_DIR = ROOT / ".cache"
ARTIST_CACHE = CACHE_DIR / "musicbrainz-artists.json"
RELEASE_GROUP_CACHE = CACHE_DIR / "musicbrainz-release-groups.json"
GENRE_CACHE = CACHE_DIR / "musicbrainz-genres.json"
API_BASE = "https://musicbrainz.org/ws/2"
DEFAULT_USER_AGENT = "myfavmusic-genre-enricher/1.0 (personal local metadata script)"

BROAD_GENRE_MARKERS = {
    "ambient",
    "americana",
    "blackgaze",
    "bluegrass",
    "blues",
    "classical",
    "country",
    "darkwave",
    "doom",
    "downtempo",
    "drone",
    "dub",
    "electronic",
    "experimental",
    "folk",
    "funk",
    "gothic",
    "grindcore",
    "grunge",
    "hardcore",
    "hip hop",
    "house",
    "idm",
    "industrial",
    "jazz",
    "krautrock",
    "metal",
    "neofolk",
    "noise",
    "pop",
    "post-punk",
    "post-rock",
    "prog",
    "psychedelic",
    "psychobilly",
    "punk",
    "rap",
    "reggae",
    "rock",
    "rockabilly",
    "shoegaze",
    "sludge",
    "soul",
    "stoner",
    "synthpop",
    "techno",
    "trance",
    "wave",
}

TAG_DENYLIST = {
    "00s",
    "60s",
    "70s",
    "80s",
    "90s",
    "american",
    "australian",
    "austrian",
    "british",
    "canadian",
    "cover",
    "danish",
    "deutsch",
    "dutch",
    "english",
    "female vocalist",
    "female vocalists",
    "finnish",
    "french",
    "german",
    "instrumental",
    "italian",
    "japanese",
    "live",
    "male vocalist",
    "male vocalists",
    "new zealand",
    "norwegian",
    "polish",
    "russian",
    "scandinavian",
    "seen live",
    "spanish",
    "swedish",
    "uk",
    "usa",
    "vocal",
    "vocalist",
}

GENRE_ALIASES = {
    "neo-folk": "neofolk",
    "prog metal": "progressive metal",
    "prog rock": "progressive rock",
}

GENERIC_PARENT_RULES = {
    "metal": ("metal",),
    "rock": ("rock", "grunge", "shoegaze", "krautrock", "psychobilly", "rockabilly"),
    "punk": ("punk", "hardcore", "grindcore"),
    "folk": ("folk", "americana", "bluegrass", "neofolk"),
    "jazz": ("jazz",),
    "blues": ("blues",),
    "pop": ("pop", "synthpop"),
}


def parse_args() -> argparse.Namespace:
    load_dotenv(ROOT / ".env")
    parser = argparse.ArgumentParser(
        description="Fill blank track genres from MusicBrainz artist tags."
    )
    parser.add_argument("--tracks", type=Path, default=TRACKS_CSV)
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--artist-cache", type=Path, default=ARTIST_CACHE)
    parser.add_argument("--release-group-cache", type=Path, default=RELEASE_GROUP_CACHE)
    parser.add_argument("--genre-cache", type=Path, default=GENRE_CACHE)
    parser.add_argument(
        "--user-agent",
        default=os.getenv("MUSICBRAINZ_USER_AGENT", DEFAULT_USER_AGENT),
        help="MusicBrainz requires a descriptive User-Agent.",
    )
    parser.add_argument("--sleep", type=float, default=float(os.getenv("MUSICBRAINZ_SLEEP", "1.1")))
    parser.add_argument("--retries", type=int, default=int(os.getenv("MUSICBRAINZ_RETRIES", "20")))
    parser.add_argument("--min-score", type=int, default=90)
    parser.add_argument("--max-genres", type=int, default=5)
    parser.add_argument("--limit-artists", type=int, default=0)
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--retry-misses", action="store_true")
    parser.add_argument("--retry-empty-tags", action="store_true")
    parser.add_argument(
        "--offline",
        action="store_true",
        help="Use only cached MusicBrainz artist data and do not make network requests.",
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--verbose", action="store_true")
    return parser.parse_args()


def load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def resolve_path(path: Path) -> Path:
    return path if path.is_absolute() else ROOT / path


def read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as file:
        json.dump(data, file, indent=2, sort_keys=True, ensure_ascii=False)
        file.write("\n")


def read_tracks(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open("r", encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)
        return list(reader.fieldnames or []), list(reader)


def write_tracks(path: Path, fieldnames: list[str], rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fieldnames})


def split_values(value: str) -> list[str]:
    return [part.strip() for part in value.replace(",", ";").split(";") if part.strip()]


def join_unique(values: Iterable[str]) -> str:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        cleaned = value.strip().lower()
        if cleaned and cleaned not in seen:
            seen.add(cleaned)
            result.append(cleaned)
    return "; ".join(result)


def norm(value: str) -> str:
    return " ".join(value.casefold().strip().split())


class MusicBrainzClient:
    def __init__(self, user_agent: str, delay: float, retries: int) -> None:
        self.user_agent = user_agent
        self.delay = max(delay, 0)
        self.retries = max(retries, 1)
        self.last_request = 0.0

    def request(self, path: str, params: dict[str, Any]) -> dict[str, Any]:
        params = {**params, "fmt": "json"}
        url = f"{API_BASE}{path}?{urllib.parse.urlencode(params)}"
        last_error: Exception | None = None
        for attempt in range(self.retries):
            elapsed = time.monotonic() - self.last_request
            if elapsed < self.delay:
                time.sleep(self.delay - elapsed)
            request = urllib.request.Request(url, headers={"User-Agent": self.user_agent})
            try:
                with urllib.request.urlopen(request, timeout=60) as response:
                    self.last_request = time.monotonic()
                    return json.loads(response.read().decode("utf-8"))
            except urllib.error.HTTPError as error:
                self.last_request = time.monotonic()
                if error.code in {503, 502, 500, 429}:
                    time.sleep(min(5 + attempt * 5, 60))
                    last_error = error
                    continue
                body = error.read().decode("utf-8", errors="replace")
                raise RuntimeError(f"MusicBrainz returned {error.code}: {body}") from error
            except (ConnectionError, TimeoutError, socket.timeout, urllib.error.URLError) as error:
                self.last_request = time.monotonic()
                last_error = error
                time.sleep(min(5 + attempt * 5, 60))
        raise RuntimeError(f"MusicBrainz request failed: {last_error}") from last_error


def read_musicbrainz_genres(client: MusicBrainzClient, cache_path: Path) -> set[str]:
    cached = read_json(cache_path, {})
    if cached.get("genres"):
        return {norm(genre) for genre in cached["genres"]}

    genres: list[str] = []
    offset = 0
    limit = 100
    total = None
    while total is None or offset < total:
        payload = client.request("/genre/all", {"limit": limit, "offset": offset})
        total = int(payload.get("genre-count") or 0)
        genres.extend(genre.get("name", "") for genre in payload.get("genres", []))
        offset += limit

    write_json(cache_path, {"genres": sorted(set(genres)), "fetched_at": int(time.time())})
    return {norm(genre) for genre in genres if genre}


def search_artist_candidates(client: MusicBrainzClient, artist_name: str) -> list[dict[str, Any]]:
    escaped = artist_name.replace('"', '\\"')
    queries = [f'artist:"{escaped}"', artist_name]
    candidates: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for query in queries:
        payload = client.request("/artist/", {"query": query, "limit": 5})
        for candidate in payload.get("artists", []) or []:
            candidate_id = candidate.get("id", "")
            if candidate_id and candidate_id in seen_ids:
                continue
            if candidate_id:
                seen_ids.add(candidate_id)
            candidates.append(candidate)
        if candidates and any((candidate.get("tags") or []) for candidate in candidates):
            break
    return candidates


def tag_score(candidate: dict[str, Any]) -> int:
    return sum(max(int(tag.get("count") or 0), 1) for tag in candidate.get("tags", []) or [])


def query_artist(client: MusicBrainzClient, artist_name: str, min_score: int) -> dict[str, Any]:
    candidates = search_artist_candidates(client, artist_name)
    if not candidates:
        return {"matched": False, "query": artist_name, "tags": []}

    viable = [candidate for candidate in candidates if int(candidate.get("score") or 0) >= min_score]
    exact = [candidate for candidate in viable if norm(candidate.get("name", "")) == norm(artist_name)]
    pool = exact or viable
    selected = max(pool, key=lambda candidate: (tag_score(candidate), int(candidate.get("score") or 0))) if pool else candidates[0]
    if int(selected.get("score") or 0) < min_score:
        return {
            "matched": False,
            "query": artist_name,
            "score": int(selected.get("score") or 0),
            "name": selected.get("name", ""),
            "tags": [],
        }

    return {
        "matched": True,
        "query": artist_name,
        "artist_id": selected.get("id", ""),
        "score": int(selected.get("score") or 0),
        "name": selected.get("name", ""),
        "disambiguation": selected.get("disambiguation", ""),
        "tags": selected.get("tags", []) or [],
        "fetched_at": int(time.time()),
    }


def query_release_group(
    client: MusicBrainzClient,
    artist_name: str,
    album_name: str,
    min_score: int,
) -> dict[str, Any]:
    if not artist_name or not album_name:
        return {"matched": False, "query": "", "tags": []}
    artist = artist_name.replace('"', '\\"')
    album = album_name.replace('"', '\\"')
    queries = [
        f'artist:"{artist}" AND release:"{album}"',
        f'artist:"{artist}" AND releasegroup:"{album}"',
        f'{artist_name} {album_name}',
    ]
    candidates: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for query in queries:
        payload = client.request("/release-group/", {"query": query, "limit": 5})
        for candidate in payload.get("release-groups", []) or []:
            candidate_id = candidate.get("id", "")
            if candidate_id and candidate_id in seen_ids:
                continue
            if candidate_id:
                seen_ids.add(candidate_id)
            candidates.append(candidate)
        if candidates and any((candidate.get("tags") or []) for candidate in candidates):
            break
    viable = [candidate for candidate in candidates if int(candidate.get("score") or 0) >= min_score]
    if not viable:
        return {"matched": False, "query": f"{artist_name} | {album_name}", "tags": []}
    selected = max(viable, key=lambda candidate: (tag_score(candidate), int(candidate.get("score") or 0)))
    return {
        "matched": True,
        "query": f"{artist_name} | {album_name}",
        "release_group_id": selected.get("id", ""),
        "score": int(selected.get("score") or 0),
        "title": selected.get("title", ""),
        "tags": selected.get("tags", []) or [],
        "fetched_at": int(time.time()),
    }


def is_genre_tag(tag: str, musicbrainz_genres: set[str]) -> bool:
    tag_norm = canonical_genre(tag)
    if not tag_norm or tag_norm in TAG_DENYLIST:
        return False
    if tag_norm in musicbrainz_genres:
        return True
    return any(marker in tag_norm for marker in BROAD_GENRE_MARKERS)


def canonical_genre(value: str) -> str:
    genre = norm(value)
    return GENRE_ALIASES.get(genre, genre)


def prune_parent_genres(genres: list[str]) -> list[str]:
    genre_set = set(genres)
    pruned: list[str] = []
    for genre in genres:
        markers = GENERIC_PARENT_RULES.get(genre)
        if markers and any(
            other != genre and any(marker in other for marker in markers)
            for other in genre_set
        ):
            continue
        pruned.append(genre)
    return pruned


def ranked_genres_from_tags(
    tags: list[dict[str, Any]],
    musicbrainz_genres: set[str],
    max_genres: int,
) -> list[str]:
    weighted: Counter[str] = Counter()
    first_seen: dict[str, int] = {}
    for index, tag in enumerate(tags):
        name = tag.get("name", "")
        if not is_genre_tag(name, musicbrainz_genres):
            continue
        genre = canonical_genre(name)
        first_seen.setdefault(genre, index)
        weighted[genre] += max(int(tag.get("count") or 0), 1)
    ranked = sorted(weighted, key=lambda genre: (-weighted[genre], first_seen[genre], genre))
    return prune_parent_genres(ranked)[:max_genres]


def ranked_genres_for_artist(
    artist_data: dict[str, Any],
    musicbrainz_genres: set[str],
    max_genres: int,
) -> list[str]:
    return ranked_genres_from_tags(artist_data.get("tags", []) or [], musicbrainz_genres, max_genres)


def artist_names_from_rows(rows: list[dict[str, str]], overwrite: bool) -> list[str]:
    seen: set[str] = set()
    artists: list[str] = []
    for row in rows:
        if not overwrite and row.get("primary_genre") and row.get("genres"):
            continue
        for artist in split_values(row.get("artist_names", "")):
            key = norm(artist)
            if key and key not in seen:
                seen.add(key)
                artists.append(artist)
    return artists


def row_genres(
    row: dict[str, str],
    artist_cache: dict[str, Any],
    musicbrainz_genres: set[str],
    max_genres: int,
) -> list[str]:
    weighted: Counter[str] = Counter()
    first_seen: dict[str, int] = {}
    for artist_index, artist in enumerate(split_values(row.get("artist_names", ""))):
        artist_data = artist_cache.get(norm(artist), {})
        for genre_index, genre in enumerate(ranked_genres_for_artist(artist_data, musicbrainz_genres, max_genres)):
            first_seen.setdefault(genre, artist_index * 100 + genre_index)
            weighted[genre] += max_genres - genre_index
    ranked = sorted(weighted, key=lambda genre: (-weighted[genre], first_seen[genre], genre))
    return prune_parent_genres(ranked)[:max_genres]


def release_group_cache_key(row: dict[str, str]) -> str:
    artist = split_values(row.get("artist_names", ""))
    artist_name = artist[0] if artist else ""
    return f"{norm(artist_name)}|{norm(row.get('album_name', ''))}"


def main() -> None:
    args = parse_args()
    tracks_path = resolve_path(args.tracks)
    output_path = resolve_path(args.output) if args.output else tracks_path
    artist_cache_path = resolve_path(args.artist_cache)
    release_group_cache_path = resolve_path(args.release_group_cache)
    genre_cache_path = resolve_path(args.genre_cache)

    fieldnames, rows = read_tracks(tracks_path)
    client = MusicBrainzClient(args.user_agent, args.sleep, args.retries)
    musicbrainz_genres = read_musicbrainz_genres(client, genre_cache_path)
    artist_cache = read_json(artist_cache_path, {})
    release_group_cache = read_json(release_group_cache_path, {})

    artists = artist_names_from_rows(rows, args.overwrite)
    if args.limit_artists:
        artists = artists[: args.limit_artists]

    fetched = 0
    for artist in artists:
        key = norm(artist)
        cached = artist_cache.get(key)
        should_retry = bool(
            cached
            and (
                (args.retry_misses and not cached.get("matched"))
                or (args.retry_empty_tags and cached.get("matched") and not cached.get("tags"))
            )
        )
        if cached and not should_retry:
            continue
        if args.offline:
            continue
        artist_cache[key] = query_artist(client, artist, args.min_score)
        fetched += 1
        write_json(artist_cache_path, artist_cache)
        if args.verbose:
            status = "matched" if artist_cache[key].get("matched") else "missed"
            print(f"{fetched}: {status} {artist}", flush=True)
        if fetched % 25 == 0:
            write_json(artist_cache_path, artist_cache)
    if fetched:
        write_json(artist_cache_path, artist_cache)

    fetched_release_groups = 0
    changed = 0
    for row in rows:
        if not args.overwrite and row.get("primary_genre") and row.get("genres"):
            continue
        genres = row_genres(row, artist_cache, musicbrainz_genres, args.max_genres)
        if not genres:
            release_key = release_group_cache_key(row)
            release_data = release_group_cache.get(release_key)
            if release_data is None and not args.offline:
                artist = split_values(row.get("artist_names", ""))
                release_data = query_release_group(
                    client,
                    artist[0] if artist else "",
                    row.get("album_name", ""),
                    args.min_score,
                )
                release_group_cache[release_key] = release_data
                fetched_release_groups += 1
                if fetched_release_groups % 25 == 0:
                    write_json(release_group_cache_path, release_group_cache)
            if release_data:
                genres = ranked_genres_from_tags(
                    release_data.get("tags", []) or [],
                    musicbrainz_genres,
                    args.max_genres,
                )
        if not genres:
            continue
        if args.overwrite or not row.get("primary_genre"):
            row["primary_genre"] = genres[0]
        if args.overwrite or not row.get("genres"):
            row["genres"] = join_unique(genres)
        changed += 1

    remaining = sum(1 for row in rows if not (row.get("genres") or row.get("spotify_genres")))
    print(f"Fetched {fetched} MusicBrainz artist records.")
    print(f"Filled genres for {changed} tracks.")
    print(f"Tracks still without effective genres: {remaining}.")
    if args.dry_run:
        print("Dry run only; CSV was not written.")
        return
    if fetched_release_groups:
        write_json(release_group_cache_path, release_group_cache)
    print(f"Fetched {fetched_release_groups} MusicBrainz release-group records.")
    write_tracks(output_path, fieldnames, rows)
    print(f"Wrote {output_path}.")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import html
import json
import os
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable


ROOT = Path(__file__).resolve().parents[1]
TRACKS_CSV = ROOT / "data" / "tracks.csv"
README = ROOT / "README.md"
MUSICBRAINZ_ARTIST_CACHE = ROOT / ".cache" / "musicbrainz-artists.json"
COUNTRY_OVERRIDES_CSV = ROOT / "data" / "country_overrides.csv"

COUNTRY_CODES = {
    "AU": "Australia",
    "AR": "Argentina",
    "AT": "Austria",
    "AZ": "Azerbaijan",
    "BE": "Belgium",
    "BS": "Bahamas",
    "BY": "Belarus",
    "BR": "Brazil",
    "CA": "Canada",
    "CL": "Chile",
    "CO": "Colombia",
    "CU": "Cuba",
    "CY": "Cyprus",
    "CZ": "Czechia",
    "DK": "Denmark",
    "EE": "Estonia",
    "FI": "Finland",
    "FO": "Faroe Islands",
    "FR": "France",
    "DE": "Germany",
    "GR": "Greece",
    "HR": "Croatia",
    "HU": "Hungary",
    "IS": "Iceland",
    "ID": "Indonesia",
    "IE": "Ireland",
    "IL": "Israel",
    "IN": "India",
    "IT": "Italy",
    "JP": "Japan",
    "LT": "Lithuania",
    "MQ": "Martinique",
    "MX": "Mexico",
    "NL": "Netherlands",
    "NZ": "New Zealand",
    "NO": "Norway",
    "PL": "Poland",
    "PT": "Portugal",
    "RU": "Russia",
    "RO": "Romania",
    "ES": "Spain",
    "SE": "Sweden",
    "SI": "Slovenia",
    "SK": "Slovakia",
    "CH": "Switzerland",
    "TG": "Togo",
    "TR": "Turkey",
    "UA": "Ukraine",
    "GB": "United Kingdom",
    "UK": "United Kingdom",
    "US": "United States",
    "USA": "United States",
    "XE": "Europe",
    "ZA": "South Africa",
}

COUNTRY_MARKERS = {
    "american": "United States",
    "australian": "Australia",
    "austrian": "Austria",
    "belgian": "Belgium",
    "brazilian": "Brazil",
    "british": "United Kingdom",
    "canadian": "Canada",
    "chilean": "Chile",
    "czech": "Czechia",
    "danish": "Denmark",
    "deutsch": "Germany",
    "dutch": "Netherlands",
    "english": "United Kingdom",
    "finnish": "Finland",
    "french": "France",
    "german": "Germany",
    "greek": "Greece",
    "icelandic": "Iceland",
    "irish": "Ireland",
    "italian": "Italy",
    "japanese": "Japan",
    "mexican": "Mexico",
    "new zealand": "New Zealand",
    "norwegian": "Norway",
    "polish": "Poland",
    "portuguese": "Portugal",
    "russian": "Russia",
    "scottish": "United Kingdom",
    "spanish": "Spain",
    "swedish": "Sweden",
    "swiss": "Switzerland",
    "u k": "United Kingdom",
    "u s": "United States",
    "uk": "United Kingdom",
    "ukrainian": "Ukraine",
    "united kingdom": "United Kingdom",
    "united states": "United States",
    "us": "United States",
    "usa": "United States",
    "welsh": "United Kingdom",
}

TrackRow = dict[str, str]
RankedRows = list[tuple[str, int]]

SUPER_GENRE_RULES = [
    ("Metal", ("metal", "doom", "blackgaze", "djent", "deathgrind", "grindcore", "mathcore", "sludge", "thrash")),
    (
        "Rock / Psych / Prog",
        ("rock", "grunge", "shoegaze", "krautrock", "psychobilly", "rockabilly", "psych", "psychedelic", "prog", "jam band"),
    ),
    (
        "Electronic / Ambient",
        (
            "electronic",
            "electronica",
            "ambient",
            "techno",
            "house",
            "idm",
            "synth",
            "trance",
            "dub",
            "downtempo",
            "drone",
            "dungeon synth",
            "drum and bass",
            "jungle",
            "breakbeat",
            "breakcore",
            "chillstep",
            "vaporwave",
            "dance",
            "electro",
            "dark wave",
            "darkwave",
            "coldwave",
        ),
    ),
    ("Punk / Hardcore", ("punk", "hardcore", "crust", "d-beat", "post-hardcore", "emo")),
    (
        "Folk / World",
        ("folk", "americana", "bluegrass", "neofolk", "country", "world", "celtic", "flamenco", "filmi", "junkanoo", "liedermacher"),
    ),
    ("Jazz / Blues", ("jazz", "blues", "bossa nova", "post-bop", "swing")),
    ("Soul / Funk / R&B", ("soul", "funk", "r&b", "rhythm and blues")),
    ("Reggae / Ska", ("reggae", "ska")),
    ("Afrobeat / Latin", ("afrobeat", "afro-cuban", "latin")),
    ("Classical / Score", ("classical", "orchestral", "score", "soundtrack", "chamber", "opera", "choral", "production music")),
    ("Pop / Songwriter", ("pop", "singer-songwriter", "aor", "new wave")),
    ("Hip-Hop / Rap", ("hip hop", "rap", "trap")),
    ("Experimental / Noise", ("experimental", "noise", "avant-garde", "industrial")),
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build README dashboard from a tracks CSV.")
    parser.add_argument("--input", type=Path, default=TRACKS_CSV)
    parser.add_argument("--output", type=Path, default=README)
    parser.add_argument(
        "--allow-empty",
        action="store_true",
        help="Allow a missing input CSV and render setup content instead of failing.",
    )
    return parser.parse_args()


def resolve_repo_path(path: Path) -> Path:
    return path if path.is_absolute() else ROOT / path


def read_tracks(path: Path, allow_missing: bool = False) -> list[dict[str, str]]:
    if not path.exists():
        if allow_missing:
            return []
        raise FileNotFoundError(f"Track CSV not found: {path}")
    with path.open("r", encoding="utf-8-sig", newline="") as file:
        return list(csv.DictReader(file))


def read_json(path: Path) -> dict[str, object]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as file:
        data = json.load(file)
    return data if isinstance(data, dict) else {}


def read_country_overrides(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8-sig", newline="") as file:
        rows = csv.DictReader(file)
        return {
            norm(row.get("artist_name", "")): row.get("country", "").strip()
            for row in rows
            if row.get("artist_name") and row.get("country")
        }


def split_values(value: str) -> list[str]:
    return [part.strip() for part in value.replace(",", ";").split(";") if part.strip()]


def norm(value: str) -> str:
    return " ".join(value.casefold().strip().split())


def marker_text(value: str) -> str:
    return " ".join(re.sub(r"[^a-z0-9]+", " ", value.casefold()).split())


def country_from_marker(value: str) -> str:
    text = f" {marker_text(value)} "
    for marker, country in COUNTRY_MARKERS.items():
        if f" {marker} " in text:
            return country
    return ""


def country_from_artist_data(data: object) -> str:
    if not isinstance(data, dict) or not data.get("matched", False):
        return ""

    country_code = str(data.get("country") or "").strip().upper()
    if country_code:
        return COUNTRY_CODES.get(country_code, country_code)

    area = data.get("area")
    if isinstance(area, dict):
        area_name = str(area.get("name") or "").strip()
        if area_name:
            return COUNTRY_CODES.get(area_name.upper(), area_name)

    begin_area = data.get("begin_area")
    if isinstance(begin_area, dict):
        begin_area_name = str(begin_area.get("name") or "").strip()
        if begin_area_name:
            return COUNTRY_CODES.get(begin_area_name.upper(), begin_area_name)

    wikidata_origin = str(data.get("wikidata_origin") or "").strip()
    if wikidata_origin:
        return COUNTRY_CODES.get(wikidata_origin.upper(), wikidata_origin)

    for tag in data.get("tags", []) or []:
        if isinstance(tag, dict):
            country = country_from_marker(str(tag.get("name") or ""))
            if country:
                return country

    return country_from_marker(str(data.get("disambiguation") or ""))


def track_countries(
    row: dict[str, str],
    artist_cache: dict[str, object],
    country_overrides: dict[str, str] | None = None,
) -> list[str]:
    countries: list[str] = []
    seen: set[str] = set()
    for artist in all_artists(row):
        country = (country_overrides or {}).get(norm(artist), "")
        if not country:
            country = country_from_artist_data(artist_cache.get(norm(artist)))
        if country and country not in seen:
            seen.add(country)
            countries.append(country)
    return countries


def effective_year(row: dict[str, str]) -> str:
    return (row.get("year") or row.get("spotify_year") or "").strip()


def effective_genres(row: dict[str, str]) -> list[str]:
    return split_values(row.get("genres") or row.get("spotify_genres") or "")


def effective_primary_genre(row: dict[str, str]) -> str:
    primary = (row.get("primary_genre") or "").strip()
    if primary:
        return primary
    genres = effective_genres(row)
    return genres[0] if genres else ""


def all_artists(row: dict[str, str]) -> list[str]:
    return split_values(row.get("artist_names", ""))


def md_escape(value: object) -> str:
    text = str(value if value is not None else "")
    return text.replace("|", "\\|").replace("\n", " ").strip()


def md_link(label: str, target: Path, base_dir: Path) -> str:
    rel = os.path.relpath(target, base_dir).replace("\\", "/")
    return f"[`{label}`]({rel})"


def repo_label(path: Path) -> str:
    try:
        return path.relative_to(ROOT).as_posix()
    except ValueError:
        return path.name


def table(headers: list[str], rows: Iterable[Iterable[object]]) -> str:
    rendered = ["| " + " | ".join(headers) + " |"]
    rendered.append("| " + " | ".join("---" for _ in headers) + " |")
    for row in rows:
        rendered.append("| " + " | ".join(md_escape(value) for value in row) + " |")
    return "\n".join(rendered)


def duration_label(total_ms: int) -> str:
    total_minutes = total_ms // 60000
    hours, minutes = divmod(total_minutes, 60)
    if hours:
        return f"{hours}h {minutes}m"
    return f"{minutes}m"


def top(counter: Counter[str], limit: int = 12) -> list[tuple[str, int]]:
    return [(name, count) for name, count in counter.most_common(limit) if name]


def html_escape(value: object) -> str:
    return html.escape(str(value if value is not None else ""), quote=True)


def rank_lines(rows: RankedRows, limit: int = 10) -> str:
    if not rows:
        return "&nbsp;"
    return "<br>".join(
        f"{html_escape(name)} <strong>{count}</strong>" for name, count in rows[:limit]
    )


def super_genre(genre: str) -> str:
    genre_key = genre.casefold()
    for label, markers in SUPER_GENRE_RULES:
        if any(marker in genre_key for marker in markers):
            return label
    return "Other"


def dominant_row_genre(row: TrackRow) -> str:
    primary = effective_primary_genre(row).lower()
    fallback = effective_genres(row)
    return primary or (fallback[0].lower() if fallback else "")


def artist_country(
    artist: str,
    artist_cache: dict[str, object],
    country_overrides: dict[str, str],
) -> str:
    artist_key = norm(artist)
    return country_overrides.get(artist_key, "") or country_from_artist_data(
        artist_cache.get(artist_key)
    )


def artist_genre_assignments(
    tracks: list[TrackRow],
    genre_rows: RankedRows,
) -> dict[str, str]:
    genre_rank = {genre: index for index, (genre, _count) in enumerate(genre_rows)}
    artist_genres: dict[str, Counter[str]] = {}
    for row in tracks:
        genre = dominant_row_genre(row)
        if not genre:
            continue
        for artist in all_artists(row):
            artist_genres.setdefault(artist, Counter())[genre] += 1

    assignments: dict[str, str] = {}
    for artist, genre_counts in artist_genres.items():
        assignments[artist] = min(
            genre_counts,
            key=lambda genre: (-genre_counts[genre], genre_rank.get(genre, len(genre_rank)), genre),
        )
    return assignments


def artists_assigned_to_genre(
    row: TrackRow,
    artist_genres: dict[str, str],
    genre: str,
) -> list[str]:
    return [artist for artist in all_artists(row) if artist_genres.get(artist) == genre]


def assigned_genre_rows(
    tracks: list[TrackRow],
    artist_genres: dict[str, str],
) -> RankedRows:
    counts: Counter[str] = Counter()
    for row in tracks:
        row_genres = {
            artist_genres.get(artist)
            for artist in all_artists(row)
            if artist_genres.get(artist)
        }
        for genre in row_genres:
            counts[genre] += 1
    return top(counts, len(counts))


def genre_card(
    index: int,
    genre: str,
    count: int,
    tracks: list[TrackRow],
    artist_cache: dict[str, object],
    country_overrides: dict[str, str],
    artist_genres: dict[str, str],
) -> str:
    rows = [
        row for row in tracks if artists_assigned_to_genre(row, artist_genres, genre)
    ]
    genre_artists = Counter(
        artist
        for row in rows
        for artist in artists_assigned_to_genre(row, artist_genres, genre)
    )
    genre_years = Counter(effective_year(row) for row in rows if effective_year(row).isdigit())
    genre_countries = Counter(
        country
        for row in rows
        for artist in artists_assigned_to_genre(row, artist_genres, genre)
        for country in [artist_country(artist, artist_cache, country_overrides)]
        if country
    )
    return f"""
<td valign="top" width="33%">
<strong>{index:02d} · {html_escape(genre)}</strong><br>
<sub>{count} total tracks · top 10</sub>
<table>
<tr><th>Artists</th><th>Years</th><th>Countries</th></tr>
<tr>
<td valign="top">{rank_lines(top(genre_artists, 10))}</td>
<td valign="top">{rank_lines(top(genre_years, 10))}</td>
<td valign="top">{rank_lines(top(genre_countries, 10))}</td>
</tr>
</table>
</td>
"""


def genre_atlas(
    tracks: list[TrackRow],
    artist_cache: dict[str, object],
    country_overrides: dict[str, str],
    genre_rows: RankedRows,
    artist_genres: dict[str, str],
) -> list[str]:
    grouped: dict[str, RankedRows] = {}
    for genre, count in genre_rows:
        grouped.setdefault(super_genre(genre), []).append((genre, count))

    lines: list[str] = []
    group_order = [label for label, _markers in SUPER_GENRE_RULES] + ["Other"]
    card_index = 0
    for group in group_order:
        group_rows = grouped.get(group, [])
        if not group_rows:
            continue
        group_tracks = sum(count for _genre, count in group_rows)
        lines.extend(
            [
                f"## {group}",
                "",
                f"**{len(group_rows)} genres · {group_tracks} tracks**",
                "",
            ]
        )
        cards: list[str] = []
        for genre, count in group_rows:
            card_index += 1
            cards.append(
                genre_card(
                    card_index,
                    genre,
                    count,
                    tracks,
                    artist_cache,
                    country_overrides,
                    artist_genres,
                )
            )
        for offset in range(0, len(cards), 3):
            chunk = cards[offset : offset + 3]
            while len(chunk) < 3:
                chunk.append('<td valign="top" width="33%">&nbsp;</td>')
            lines.extend(["<table>", "<tr>", *chunk, "</tr>", "</table>", ""])
    return lines


def build_dashboard(
    tracks: list[dict[str, str]],
    tracks_csv: Path,
    readme: Path,
) -> str:
    readme_dir = readme.parent
    artist_cache = read_json(MUSICBRAINZ_ARTIST_CACHE)
    country_overrides = read_country_overrides(COUNTRY_OVERRIDES_CSV)
    artists = Counter(artist for row in tracks for artist in all_artists(row))
    genres = Counter(genre.lower() for row in tracks for genre in effective_genres(row))
    countries = Counter(
        country for row in tracks for country in track_countries(row, artist_cache, country_overrides)
    )
    years = Counter(effective_year(row) for row in tracks if effective_year(row).isdigit())
    albums = {
        row.get("album_id") or f"{row.get('artist_names', '')}|{row.get('album_name', '')}"
        for row in tracks
        if row.get("album_id") or row.get("album_name")
    }
    playlists = {
        playlist
        for row in tracks
        for playlist in split_values(row.get("playlist_names", ""))
        if playlist
    }
    duration_ms = sum(int(row.get("duration_ms") or 0) for row in tracks if (row.get("duration_ms") or "").isdigit())

    known_years = [int(year) for year in years if year.isdigit()]
    year_range = f"{min(known_years)}-{max(known_years)}" if known_years else ""
    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    lines: list[str] = [
        "# Maks Krutikov Spotify Library",
        "",
        "Personal Spotify metadata dashboard. No audio files, only generated summaries from a private CSV archive.",
        "",
    ]

    if not tracks:
        lines.extend(
            [
                "## Setup",
                "",
                "1. Create a Spotify app and add `http://127.0.0.1:8888/callback` as a redirect URI.",
                "2. Copy `.env.example` to `.env` and fill `SPOTIFY_CLIENT_ID` and `SPOTIFY_CLIENT_SECRET`.",
                "3. Run `python scripts/export_spotify.py --verbose --skip-genres`.",
                "4. Run `python scripts/apply_genre_rules.py`.",
                "5. Run `python scripts/build_readme.py`.",
                "",
                "For weekly GitHub Actions updates, add `SPOTIFY_CLIENT_ID`, `SPOTIFY_CLIENT_SECRET`, and `SPOTIFY_REFRESH_TOKEN` as repository secrets.",
                "",
            ]
        )
    else:
        top_genres = top(genres, len(genres))
        artist_genres = artist_genre_assignments(tracks, top_genres)
        assigned_genres = assigned_genre_rows(tracks, artist_genres)
        lines.extend(
            [
                table(
                    [
                        "Tracks",
                        "Artists",
                        "Albums",
                        "Tag genres",
                        "Assigned genres",
                        "Countries",
                        "Playlists",
                        "Release years",
                        "Duration",
                    ],
                    [
                        [
                            len(tracks),
                            len(artists),
                            len(albums),
                            len(genres),
                            len(assigned_genres),
                            len(countries),
                            len(playlists),
                            year_range,
                            duration_label(duration_ms),
                        ]
                    ],
                ),
                "",
                "> Each artist is assigned to exactly one dominant genre. Every genre card below shows top 10 artists, years and countries.",
                "",
            ]
        )
        lines.extend(genre_atlas(tracks, artist_cache, country_overrides, assigned_genres, artist_genres))

        lines.extend(
            [
                "## Aggregates",
                "",
                "### Top 20 Countries",
                "",
                table(["Country", "Tracks"], top(countries, 20)),
                "",
                "### Top 20 Genres",
                "",
                table(["Genre", "Tracks"], assigned_genres[:20]),
                "",
                "### Top 20 Groups / Artists",
                "",
                table(["Group / artist", "Tracks"], top(artists, 20)),
                "",
                "<details>",
                "<summary>Workflow</summary>",
                "",
                "",
                "- `python scripts/export_spotify.py` updates `data/tracks.csv` from saved tracks and owned/collaborative playlists.",
                "- `python scripts/enrich_genres_musicbrainz.py` fills blank genres from cached MusicBrainz artist tags.",
                "- `python scripts/backfill_countries_musicbrainz.py --fetch-missing-artists` backfills artist countries from MusicBrainz and Wikidata where available.",
                "- `python scripts/apply_genre_rules.py` fills genres from `data/genre_rules.csv`.",
                "- `python scripts/build_readme.py` regenerates this README.",
                "- `python scripts/debug_spotify.py` checks OAuth and first Spotify API pages without writing CSV.",
                "- Manual fields in `data/tracks.csv` are preserved on export: `year`, `primary_genre`, `genres`, `rating`, `status`, `tags`, `notes`.",
                "- Weekly GitHub Actions use a private data repository for `data/tracks.csv`; this public repository commits only generated summaries and public rules.",
                "",
                "</details>",
                "",
            ]
        )

    lines.extend(
        [
            "<details>",
            "<summary>Repeat this</summary>",
            "",
            "Create a Spotify app, run the local OAuth export once, store the full `data/tracks.csv` in a private data repository, then set public repository secrets described in `DATA.md`. GitHub Actions can refresh the public dashboard weekly without publishing the full CSV.",
            "",
            "</details>",
            "",
            "<details>",
            "<summary>Data</summary>",
            "",
            "- Source table: private `data/tracks.csv` fetched during the weekly workflow and not published in this repository.",
            f"- Data setup: {md_link('DATA.md', ROOT / 'DATA.md', readme_dir)}",
            f"- Track CSV example: {md_link('data/tracks.example.csv', ROOT / 'data' / 'tracks.example.csv', readme_dir)}",
            f"- Genre rules: {md_link('data/genre_rules.csv', ROOT / 'data' / 'genre_rules.csv', readme_dir)}",
            f"- Country overrides: {md_link('data/country_overrides.csv', ROOT / 'data' / 'country_overrides.csv', readme_dir)}",
            f"- README generator: {md_link('scripts/build_readme.py', ROOT / 'scripts' / 'build_readme.py', readme_dir)}",
            f"- Spotify exporter: {md_link('scripts/export_spotify.py', ROOT / 'scripts' / 'export_spotify.py', readme_dir)}",
            f"- MusicBrainz country backfill: {md_link('scripts/backfill_countries_musicbrainz.py', ROOT / 'scripts' / 'backfill_countries_musicbrainz.py', readme_dir)}",
            f"- MusicBrainz genre enricher: {md_link('scripts/enrich_genres_musicbrainz.py', ROOT / 'scripts' / 'enrich_genres_musicbrainz.py', readme_dir)}",
            f"- Genre rule applier: {md_link('scripts/apply_genre_rules.py', ROOT / 'scripts' / 'apply_genre_rules.py', readme_dir)}",
            f"- Spotify API debug: {md_link('scripts/debug_spotify.py', ROOT / 'scripts' / 'debug_spotify.py', readme_dir)}",
            "",
            "</details>",
            "",
            f"_Generated at {generated_at}._",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> None:
    args = parse_args()
    tracks_csv = resolve_repo_path(args.input)
    readme = resolve_repo_path(args.output)
    tracks = read_tracks(tracks_csv, allow_missing=args.allow_empty)
    readme.parent.mkdir(parents=True, exist_ok=True)
    readme.write_text(build_dashboard(tracks, tracks_csv, readme), encoding="utf-8")
    print(f"Wrote {readme}")


if __name__ == "__main__":
    main()

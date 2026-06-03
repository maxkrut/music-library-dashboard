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
ASSETS_DIR = ROOT / "assets"
MUSICBRAINZ_ARTIST_CACHE = ROOT / ".cache" / "musicbrainz-artists.json"
COUNTRY_OVERRIDES_CSV = ROOT / "data" / "country_overrides.csv"
BANNER_SVG = ASSETS_DIR / "banner.svg"
GENRES_SVG = ASSETS_DIR / "genres.svg"
TIMELINE_SVG = ASSETS_DIR / "timeline.svg"

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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build README dashboard from a tracks CSV.")
    parser.add_argument("--input", type=Path, default=TRACKS_CSV)
    parser.add_argument("--output", type=Path, default=README)
    parser.add_argument("--assets-dir", type=Path, default=ASSETS_DIR)
    return parser.parse_args()


def resolve_repo_path(path: Path) -> Path:
    return path if path.is_absolute() else ROOT / path


def read_tracks(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
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


def image_link(label: str, target: Path, base_dir: Path) -> str:
    rel = os.path.relpath(target, base_dir).replace("\\", "/")
    return f"![{label}]({rel})"


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


def year_to_decade(year: str) -> str:
    if not year.isdigit():
        return ""
    return f"{int(year) // 10 * 10}s"


def duration_label(total_ms: int) -> str:
    total_minutes = total_ms // 60000
    hours, minutes = divmod(total_minutes, 60)
    if hours:
        return f"{hours}h {minutes}m"
    return f"{minutes}m"


def top(counter: Counter[str], limit: int = 12) -> list[tuple[str, int]]:
    return [(name, count) for name, count in counter.most_common(limit) if name]


def write_empty_svg(path: Path, title: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="720" height="150" viewBox="0 0 720 150" role="img" aria-label="{html.escape(title)}">
  <rect width="720" height="150" fill="#eef3ef"/>
  <rect x="16" y="16" width="688" height="118" rx="10" fill="#fbfaf5" stroke="#c8d4cc"/>
  <text x="34" y="66" font-family="Segoe UI, Arial, sans-serif" font-size="26" font-weight="700" fill="#1e2f2b">{html.escape(title)}</text>
</svg>
"""
    path.write_text(svg, encoding="utf-8")


def write_banner_svg(path: Path, tracks_count: int, artist_count: int, year_range: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    subtitle = f"{tracks_count} tracks / {artist_count} artists"
    if year_range:
        subtitle += f" / {year_range}"
    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="220" viewBox="0 0 1200 220" role="img" aria-label="Maks Krutikov Spotify Library">
  <defs>
    <linearGradient id="g" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0" stop-color="#eef3ef"/>
      <stop offset=".58" stop-color="#f8f5ee"/>
      <stop offset="1" stop-color="#e7eef2"/>
    </linearGradient>
    <linearGradient id="line" x1="0" y1="0" x2="1" y2="0">
      <stop offset="0" stop-color="#5f8f73"/>
      <stop offset=".52" stop-color="#6d86a6"/>
      <stop offset="1" stop-color="#b8765f"/>
    </linearGradient>
  </defs>
  <rect width="1200" height="220" rx="18" fill="url(#g)"/>
  <circle cx="1024" cy="104" r="58" fill="none" stroke="#d2ded7" stroke-width="18" opacity=".72"/>
  <circle cx="1024" cy="104" r="20" fill="#f8f5ee" stroke="#b7c9bf" stroke-width="2"/>
  <path d="M0 164 C160 134 250 184 396 154 S650 126 790 150 1020 176 1200 132" fill="none" stroke="url(#line)" stroke-width="4" opacity=".75"/>
  <path d="M0 190 C210 176 300 202 456 184 S732 160 900 176 1050 196 1200 172" fill="none" stroke="#6d86a6" stroke-width="2" opacity=".34"/>
  <rect x="32" y="30" width="1136" height="160" rx="14" fill="#fbfaf5" opacity=".9" stroke="#c8d4cc"/>
  <text x="58" y="84" font-family="Segoe UI, Arial, sans-serif" font-size="22" font-weight="700" fill="#5f8f73">PERSONAL SPOTIFY LIBRARY</text>
  <text x="58" y="132" font-family="Segoe UI, Arial, sans-serif" font-size="42" font-weight="800" fill="#1e2f2b">Maks Krutikov Spotify Library</text>
  <text x="60" y="166" font-family="Segoe UI, Arial, sans-serif" font-size="18" fill="#586b63">{html.escape(subtitle)}</text>
  <text x="970" y="72" font-family="Segoe UI, Arial, sans-serif" font-size="16" font-weight="700" fill="#5f8f73">CSV archive</text>
  <text x="970" y="100" font-family="Segoe UI, Arial, sans-serif" font-size="16" font-weight="700" fill="#6d86a6">Genre metadata</text>
  <text x="970" y="128" font-family="Segoe UI, Arial, sans-serif" font-size="16" font-weight="700" fill="#b8765f">Weekly refresh</text>
</svg>
"""
    path.write_text(svg, encoding="utf-8")


def write_bar_svg(path: Path, title: str, rows: list[tuple[str, int]], color: str) -> None:
    if not rows:
        write_empty_svg(path, title)
        return

    width = 720
    left = 245
    right = 56
    row_height = 44
    top_pad = 76
    height = top_pad + row_height * len(rows) + 28
    max_value = max(count for _, count in rows) or 1
    bar_width = width - left - right
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-label="{html.escape(title)}">',
        f'<rect width="{width}" height="{height}" fill="#eef3ef"/>',
        f'<rect x="14" y="14" width="{width - 28}" height="{height - 28}" rx="10" fill="#fbfaf5" stroke="{color}" stroke-opacity=".55"/>',
        f'<text x="32" y="46" font-family="Segoe UI, Arial, sans-serif" font-size="26" font-weight="700" fill="#1e2f2b">{html.escape(title)}</text>',
    ]
    for index, (label, count) in enumerate(rows):
        y = top_pad + index * row_height
        length = int(bar_width * count / max_value)
        display_label = label if len(label) <= 21 else f"{label[:18].rstrip()}..."
        parts.extend(
            [
                f'<text x="32" y="{y + 25}" font-family="Segoe UI, Arial, sans-serif" font-size="20" fill="#1e2f2b">{html.escape(display_label)}</text>',
                f'<rect x="{left}" y="{y + 7}" width="{bar_width}" height="22" rx="5" fill="#e4e9e3"/>',
                f'<rect x="{left}" y="{y + 7}" width="{max(length, 5)}" height="22" rx="5" fill="{color}"/>',
                f'<text x="{left + bar_width + 12}" y="{y + 25}" font-family="Segoe UI, Arial, sans-serif" font-size="18" font-weight="700" fill="#1e2f2b">{count}</text>',
            ]
        )
    parts.append("</svg>")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(parts) + "\n", encoding="utf-8")


def build_dashboard(
    tracks: list[dict[str, str]],
    tracks_csv: Path,
    readme: Path,
    assets_dir: Path,
) -> str:
    banner_svg = assets_dir / "banner.svg"
    genres_svg = assets_dir / "genres.svg"
    timeline_svg = assets_dir / "timeline.svg"
    readme_dir = readme.parent
    artist_cache = read_json(MUSICBRAINZ_ARTIST_CACHE)
    country_overrides = read_country_overrides(COUNTRY_OVERRIDES_CSV)
    artists = Counter(artist for row in tracks for artist in all_artists(row))
    genres = Counter(genre.lower() for row in tracks for genre in effective_genres(row))
    primary_genres = Counter(effective_primary_genre(row).lower() for row in tracks if effective_primary_genre(row))
    countries = Counter(
        country for row in tracks for country in track_countries(row, artist_cache, country_overrides)
    )
    years = Counter(effective_year(row) for row in tracks if effective_year(row).isdigit())
    decades = Counter(year_to_decade(effective_year(row)) for row in tracks if year_to_decade(effective_year(row)))
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

    write_banner_svg(banner_svg, len(tracks), len(artists), year_range)
    write_bar_svg(genres_svg, "Top genres", top(genres, 10), "#5f8f73")
    write_bar_svg(timeline_svg, "Tracks by decade", top(decades, 12), "#b8765f")

    stats_rows: list[list[object]] = [
        ["Tracks", len(tracks)],
        ["Artists", len(artists)],
        ["Albums", len(albums)],
    ]
    if genres:
        stats_rows.append(["Genres", len(genres)])
    if countries:
        stats_rows.append(["Countries", len(countries)])
    if playlists:
        stats_rows.append(["Playlists", len(playlists)])
    if year_range:
        stats_rows.append(["Release years", year_range])
    if duration_ms:
        stats_rows.append(["Total duration", duration_label(duration_ms)])

    lines: list[str] = [
        image_link("Maks Krutikov Spotify Library", banner_svg, readme_dir),
        "",
        "**Maks Krutikov Spotify Library** / personal metadata dashboard. No audio files, only Spotify track data and local CSV edits.",
        "",
    ]
    if genres:
        lines.extend(
            [
                f'<img src="{os.path.relpath(genres_svg, readme_dir).replace("\\", "/")}" width="49%"> '
                f'<img src="{os.path.relpath(timeline_svg, readme_dir).replace("\\", "/")}" width="49%">',
                "",
            ]
        )
    if decades:
        if not genres:
            lines.extend([image_link("Tracks by decade", timeline_svg, readme_dir), ""])

    lines.extend(["## Overview", "", table([row[0] for row in stats_rows], [[row[1] for row in stats_rows]]), ""])

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
        latest = sorted(
            [row for row in tracks if row.get("latest_added_at")],
            key=lambda row: row.get("latest_added_at", ""),
            reverse=True,
        )[:12]

        if genres:
            lines.extend(
                [
                "## Genre Mix",
                "",
                table(["Genre", "Tracks"], top(genres, 50)),
                "",
                ]
            )
        if primary_genres:
            lines.extend(
                [
                "## Primary Genres",
                "",
                table(["Primary genre", "Tracks"], top(primary_genres, 15)),
                "",
                ]
            )
        if countries:
            lines.extend(
                [
                "## Countries",
                "",
                table(["Country", "Tracks"], top(countries, 15)),
                "",
                ]
            )

        lines.extend(
            [
                "## Artists",
                "",
                table(["Artist", "Tracks"], top(artists, 15)),
                "",
            ]
        )
        if decades:
            lines.extend(
                [
                "## Timeline",
                "",
                table(["Decade", "Tracks"], top(decades, 12)),
                "",
                ]
            )
        if latest:
            lines.extend(
                [
                "## Latest",
                "",
                table(
                    ["Track", "Artists", "Year", "Added"],
                    [
                        [
                            row.get("track_name", ""),
                            row.get("artist_names", ""),
                            effective_year(row),
                            row.get("latest_added_at", "")[:10],
                        ]
                        for row in latest
                    ],
                ),
                "",
                ]
            )

        lines.extend(
            [
                "<details>",
                "<summary>Workflow</summary>",
                "",
                "",
                "- `python scripts/export_spotify.py` updates `data/tracks.csv` from saved tracks and owned/collaborative playlists.",
                "- `python scripts/enrich_genres_musicbrainz.py` fills blank genres from cached MusicBrainz artist tags.",
                "- `python scripts/backfill_countries_musicbrainz.py --fetch-missing-artists` backfills artist countries from MusicBrainz and Wikidata where available.",
                "- `python scripts/apply_genre_rules.py` fills genres from `data/genre_rules.csv`.",
                "- `python scripts/build_readme.py` regenerates this README and SVG charts.",
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
    assets_dir = resolve_repo_path(args.assets_dir)
    tracks = read_tracks(tracks_csv)
    readme.parent.mkdir(parents=True, exist_ok=True)
    readme.write_text(build_dashboard(tracks, tracks_csv, readme, assets_dir), encoding="utf-8")
    print(f"Wrote {readme}")
    print(f"Wrote {assets_dir / 'banner.svg'}")
    print(f"Wrote {assets_dir / 'genres.svg'}")
    print(f"Wrote {assets_dir / 'timeline.svg'}")


if __name__ == "__main__":
    main()

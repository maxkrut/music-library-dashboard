#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import html
import os
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable


ROOT = Path(__file__).resolve().parents[1]
TRACKS_CSV = ROOT / "data" / "tracks.csv"
README = ROOT / "README.md"
ASSETS_DIR = ROOT / "assets"
BANNER_SVG = ASSETS_DIR / "banner.svg"
GENRES_SVG = ASSETS_DIR / "genres.svg"
TIMELINE_SVG = ASSETS_DIR / "timeline.svg"


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


def split_values(value: str) -> list[str]:
    return [part.strip() for part in value.replace(",", ";").split(";") if part.strip()]


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
    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="900" height="140" viewBox="0 0 900 140" role="img" aria-label="{html.escape(title)}">
  <rect width="900" height="140" fill="#070a12"/>
  <rect x="16" y="16" width="868" height="108" rx="12" fill="#0d1220" stroke="#00f5ff" stroke-opacity=".55"/>
  <text x="32" y="58" font-family="Segoe UI, Arial, sans-serif" font-size="22" font-weight="700" fill="#f3f7ff">{html.escape(title)}</text>
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
      <stop offset="0" stop-color="#0b1020"/>
      <stop offset=".55" stop-color="#11162a"/>
      <stop offset="1" stop-color="#19091f"/>
    </linearGradient>
    <linearGradient id="line" x1="0" y1="0" x2="1" y2="0">
      <stop offset="0" stop-color="#00f5ff"/>
      <stop offset=".5" stop-color="#ff2bd6"/>
      <stop offset="1" stop-color="#f5ff00"/>
    </linearGradient>
  </defs>
  <rect width="1200" height="220" rx="18" fill="url(#g)"/>
  <path d="M0 160 H240 L270 132 H515 L548 166 H810 L842 138 H1200" fill="none" stroke="url(#line)" stroke-width="3" opacity=".9"/>
  <path d="M0 190 H170 L205 170 H400 L435 192 H660 L700 168 H1200" fill="none" stroke="#00f5ff" stroke-width="1.5" opacity=".35"/>
  <rect x="32" y="30" width="1136" height="160" rx="14" fill="#070a12" opacity=".58" stroke="#ffffff" stroke-opacity=".12"/>
  <text x="58" y="86" font-family="Segoe UI, Arial, sans-serif" font-size="22" font-weight="700" fill="#00f5ff">PERSONAL SPOTIFY INDEX</text>
  <text x="58" y="132" font-family="Segoe UI, Arial, sans-serif" font-size="42" font-weight="800" fill="#f3f7ff">Maks Krutikov Spotify Library</text>
  <text x="60" y="166" font-family="Segoe UI, Arial, sans-serif" font-size="18" fill="#b8c7ff">{html.escape(subtitle)}</text>
  <text x="1004" y="72" font-family="Consolas, monospace" font-size="16" fill="#ff2bd6">README_DASH</text>
  <text x="1004" y="100" font-family="Consolas, monospace" font-size="16" fill="#f5ff00">CSV_SYNC</text>
  <text x="1004" y="128" font-family="Consolas, monospace" font-size="16" fill="#00f5ff">WEEKLY_RUN</text>
</svg>
"""
    path.write_text(svg, encoding="utf-8")


def write_bar_svg(path: Path, title: str, rows: list[tuple[str, int]], color: str) -> None:
    if not rows:
        write_empty_svg(path, title)
        return

    width = 900
    left = 190
    right = 48
    row_height = 34
    top_pad = 74
    height = top_pad + row_height * len(rows) + 28
    max_value = max(count for _, count in rows) or 1
    bar_width = width - left - right
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-label="{html.escape(title)}">',
        f'<rect width="{width}" height="{height}" fill="#070a12"/>',
        f'<rect x="14" y="14" width="{width - 28}" height="{height - 28}" rx="12" fill="#0d1220" stroke="{color}" stroke-opacity=".35"/>',
        f'<text x="32" y="42" font-family="Segoe UI, Arial, sans-serif" font-size="24" font-weight="700" fill="#f3f7ff">{html.escape(title)}</text>',
    ]
    for index, (label, count) in enumerate(rows):
        y = top_pad + index * row_height
        length = int(bar_width * count / max_value)
        parts.extend(
            [
                f'<text x="32" y="{y + 20}" font-family="Segoe UI, Arial, sans-serif" font-size="14" fill="#dbe7ff">{html.escape(label[:28])}</text>',
                f'<rect x="{left}" y="{y + 4}" width="{bar_width}" height="20" rx="4" fill="#1a2238"/>',
                f'<rect x="{left}" y="{y + 4}" width="{max(length, 4)}" height="20" rx="4" fill="{color}"/>',
                f'<text x="{left + bar_width + 12}" y="{y + 20}" font-family="Segoe UI, Arial, sans-serif" font-size="14" fill="#f3f7ff">{count}</text>',
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
    artists = Counter(artist for row in tracks for artist in all_artists(row))
    genres = Counter(genre.lower() for row in tracks for genre in effective_genres(row))
    primary_genres = Counter(effective_primary_genre(row).lower() for row in tracks if effective_primary_genre(row))
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
    write_bar_svg(genres_svg, "Top genres", top(genres, 10), "#00f5ff")
    write_bar_svg(timeline_svg, "Tracks by decade", top(decades, 12), "#ff2bd6")

    stats_rows: list[list[object]] = [
        ["Tracks", len(tracks)],
        ["Artists", len(artists)],
        ["Albums", len(albums)],
    ]
    if genres:
        stats_rows.append(["Genres", len(genres)])
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

    lines.extend(["## Signal", "", table([row[0] for row in stats_rows], [[row[1] for row in stats_rows]]), ""])

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
                "## Frequencies",
                "",
                table(["Genre", "Tracks"], top(genres, 15)),
                "",
                ]
            )
        if primary_genres:
            lines.extend(
                [
                "## Primary",
                "",
                table(["Primary genre", "Tracks"], top(primary_genres, 15)),
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
                "## Decades",
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
                "- `python scripts/apply_genre_rules.py` fills genres from `data/genre_rules.csv`.",
                "- `python scripts/build_readme.py` regenerates this README and SVG charts.",
                "- `python scripts/debug_spotify.py` checks OAuth and first Spotify API pages without writing CSV.",
                "- Manual fields in `data/tracks.csv` are preserved on export: `year`, `primary_genre`, `genres`, `rating`, `status`, `tags`, `notes`.",
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
            "Create a Spotify app, run the local OAuth export once, then store the generated refresh token as a GitHub secret. GitHub Actions can refresh the data weekly without using the local `.env` file.",
            "",
            "</details>",
            "",
            "<details>",
            "<summary>Data</summary>",
            "",
            f"- Source table: {md_link(repo_label(tracks_csv), tracks_csv, readme_dir)}",
            f"- Genre rules: {md_link('data/genre_rules.csv', ROOT / 'data' / 'genre_rules.csv', readme_dir)}",
            f"- README generator: {md_link('scripts/build_readme.py', ROOT / 'scripts' / 'build_readme.py', readme_dir)}",
            f"- Spotify exporter: {md_link('scripts/export_spotify.py', ROOT / 'scripts' / 'export_spotify.py', readme_dir)}",
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

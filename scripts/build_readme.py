#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import html
import json
import os
import re
import shutil
import stat
import tempfile
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable


ROOT = Path(__file__).resolve().parents[1]
TRACKS_CSV = ROOT / "data" / "tracks.csv"
README = ROOT / "README.md"
ASSETS_DIR = ROOT / "assets"
ATLAS_DIR = ASSETS_DIR / "atlas"
MUSICBRAINZ_ARTIST_CACHE = ROOT / ".cache" / "musicbrainz-artists.json"
SPOTIFY_TOP_ITEMS_CACHE = ROOT / ".cache" / "spotify-top-items.json"
SPOTIFY_RECENTLY_PLAYED_CACHE = ROOT / ".cache" / "spotify-recently-played.json"
COUNTRY_OVERRIDES_CSV = ROOT / "data" / "country_overrides.csv"


def write_text_lf(path: Path, content: str) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as file:
        file.write(content)


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

COUNTRY_VALUE_ALIASES = {
    "praha": "Czechia",
    "prague": "Czechia",
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

GENRE_ALIASES = {
    "80s thrash metal": "thrash metal",
    "acid-jazz": "acid jazz",
    "alt-country": "alternative country",
    "american metal": "metal",
    "atmospheric sludge": "atmospheric sludge metal",
    "black-metal": "black metal",
    "black/punk": "black punk metal",
    "black metal/punk": "black punk metal",
    "blackmetal": "black metal",
    "blues/rock": "blues rock",
    "classic metal": "heavy metal",
    "classic pop and rock": "classic rock",
    "dance and electronica": "electronica",
    "dark country": "gothic country",
    "dark wave": "darkwave",
    "doom": "doom metal",
    "doom metal ethereal shoegaze": "doomgaze",
    "death doom": "death-doom metal",
    "death doom metal": "death-doom metal",
    "death metal / death 'n' roll": "death 'n' roll metal",
    "death-doom": "death-doom metal",
    "death/groove-metal": "death groove metal",
    "doom death metal": "death-doom metal",
    "epic doom": "epic doom metal",
    "fairy-doom metal": "fairy doom metal",
    "french metal": "metal",
    "funeral doom": "funeral doom metal",
    "gothenburg metal": "melodic death metal",
    "gothic-doom metal": "gothic doom metal",
    "gratuitous heavy metal umlaut": "heavy metal",
    "heavy/speed-metal": "heavy speed metal",
    "hip hop rnb and dance hall": "hip hop",
    "jazz and blues": "jazz blues",
    "jazz-rock": "jazz rock",
    "melodic/death-metal": "melodic death metal",
    "melodic/death/doom-metal": "melodic death-doom metal",
    "melodic/death/gothic-metal": "melodic death gothic metal",
    "melodic death": "melodic death metal",
    "new metal": "nu metal",
    "neoclassical dark wave": "neoclassical darkwave",
    "norwegian black metal": "black metal",
    "old school death metal": "death metal",
    "pop/rock": "pop rock",
    "post black metal": "post-black metal",
    "post-doom": "post-doom metal",
    "post metal": "post-metal",
    "post rock": "post-rock",
    "post-punk 2k": "post-punk",
    "progressive/folk-rock": "progressive folk rock",
    "progressive/post-rock": "progressive post-rock",
    "progressive death": "progressive death metal",
    "psychedelic blackmetal": "psychedelic black metal",
    "rhythm and blues": "r&b",
    "rock and indie": "rock",
    "rock/metal": "rock metal",
    "sludge": "sludge metal",
    "sludge/doom-metal": "sludge doom metal",
    "sludge/doom/post-metal": "sludge doom post-metal",
    "synthpop": "synth-pop",
    "stoner-doom metal": "stoner doom metal",
    "swedish death metal": "death metal",
    "traditional heavy metal": "heavy metal",
    "traditional doom": "traditional doom metal",
    "true metal": "heavy metal",
    "true norwegian black metal": "black metal",
    "us power metal": "power metal",
    "viking/black-metal": "viking black metal",
}

GENRE_PREFIX_ALIASES = (
    ("epic/atmospheric folk/black metal", "epic atmospheric folk black metal"),
)

TrackRow = dict[str, str]
RankedRows = list[tuple[str, int]]


class SafeHtml(str):
    pass


SUPER_GENRE_RULES = [
    (
        "Metal",
        (
            "metal",
            "metalcore",
            "deathcore",
            "doom",
            "doomgaze",
            "blackgaze",
            "djent",
            "deathgrind",
            "grindcore",
            "mathcore",
            "sludge",
            "thrash",
        ),
    ),
    (
        "Rock / Psych / Prog",
        (
            "rock",
            "grunge",
            "shoegaze",
            "krautrock",
            "psychobilly",
            "rockabilly",
            "slowcore",
            "psych",
            "psychedelic",
            "prog",
            "progressive",
            "jam band",
        ),
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
            "indietronica",
            "psybient",
            "synth",
            "synthwave",
            "chillwave",
            "trance",
            "trip hop",
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
            "darkwave",
            "dark wave",
            "coldwave",
            "ebm",
            "eurodance",
            "future bass",
            "garage",
        ),
    ),
    ("Punk / Hardcore", ("punk", "hardcore", "crust", "d-beat", "post-hardcore", "emo")),
    (
        "Folk / World",
        (
            "folk",
            "americana",
            "bluegrass",
            "neofolk",
            "country",
            "world",
            "celtic",
            "flamenco",
            "filmi",
            "junkanoo",
            "calypso",
            "liedermacher",
        ),
    ),
    ("Jazz / Blues", ("jazz", "blues", "bossa nova", "post-bop", "swing", "dark jazz")),
    ("Soul / Funk / R&B", ("soul", "funk", "r&b", "rhythm and blues", "doo-wop")),
    ("Reggae / Ska", ("reggae", "ska")),
    ("Afrobeat / Latin", ("afrobeat", "afro-cuban", "latin", "son cubano", "cuban")),
    (
        "Classical / Score",
        (
            "classical",
            "orchestral",
            "score",
            "soundtrack",
            "chamber",
            "opera",
            "choral",
            "chant",
            "sacred",
            "production music",
            "epic music",
        ),
    ),
    ("Pop / Songwriter", ("pop", "singer-songwriter", "aor", "new wave")),
    ("Hip-Hop / Rap", ("hip hop", "rap", "rapcore", "trap")),
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
            norm(row.get("artist_name", "")): normalize_country_value(row.get("country", ""))
            for row in rows
            if row.get("artist_name") and row.get("country")
        }


def split_values(value: str) -> list[str]:
    return [part.strip() for part in value.replace(",", ";").split(";") if part.strip()]


def normalize_genre_text(value: str) -> str:
    text = value.casefold().strip()
    text = text.replace("’", "'").replace("‐", "-").replace("‑", "-").replace("–", "-").replace("—", "-")
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"\s*/\s*", "/", text)
    text = re.sub(r"\s*-\s*", "-", text)
    return text.strip(" -/")


def canonical_genre(value: str) -> str:
    text = normalize_genre_text(value)
    if not text:
        return ""
    for source, target in GENRE_PREFIX_ALIASES:
        if text == source:
            return target
    return GENRE_ALIASES.get(text, text)


def canonical_genres(values: Iterable[str]) -> list[str]:
    genres: list[str] = []
    seen: set[str] = set()
    for value in values:
        genre = canonical_genre(value)
        if genre and genre not in seen:
            seen.add(genre)
            genres.append(genre)
    return genres


def split_artist_names(value: str) -> list[str]:
    return [part.strip() for part in value.split(";") if part.strip()]


def norm(value: str) -> str:
    return " ".join(value.casefold().strip().split())


def normalize_country_value(value: str) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    alias = COUNTRY_VALUE_ALIASES.get(norm(text))
    if alias:
        return alias
    return COUNTRY_CODES.get(text.upper(), text)


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
        return normalize_country_value(country_code)

    area = data.get("area")
    if isinstance(area, dict):
        area_name = str(area.get("name") or "").strip()
        if area_name:
            return normalize_country_value(area_name)

    begin_area = data.get("begin_area")
    if isinstance(begin_area, dict):
        begin_area_name = str(begin_area.get("name") or "").strip()
        if begin_area_name:
            return normalize_country_value(begin_area_name)

    wikidata_origin = str(data.get("wikidata_origin") or "").strip()
    if wikidata_origin:
        return normalize_country_value(wikidata_origin)

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


def added_date(row: dict[str, str]) -> str:
    return (row.get("latest_added_at") or row.get("first_added_at") or "").strip()


def parse_iso_date(value: str) -> datetime | None:
    text = value.strip()
    if len(text) < 10:
        return None
    try:
        return datetime.fromisoformat(text[:10])
    except ValueError:
        return None


def date_label(value: str) -> str:
    return value[:10] if len(value) >= 10 else value


def month_label(value: str) -> str:
    text = value.strip()
    return text[:7] if len(text) >= 7 and text[:4].isdigit() and text[5:7].isdigit() else ""


def decade_label(value: str) -> str:
    if not value.isdigit():
        return ""
    year = int(value)
    return f"{year // 10 * 10}s"


def effective_genres(row: dict[str, str]) -> list[str]:
    return canonical_genres(split_values(row.get("genres") or row.get("spotify_genres") or ""))


def effective_primary_genre(row: dict[str, str]) -> str:
    primary = (row.get("primary_genre") or "").strip()
    if primary:
        return canonical_genre(primary)
    genres = effective_genres(row)
    return genres[0] if genres else ""


def all_artists(row: dict[str, str]) -> list[str]:
    return split_artist_names(row.get("artist_names", ""))


def row_assigned_genre(row: TrackRow, artist_genres: dict[str, str]) -> str:
    for artist in all_artists(row):
        genre = artist_genres.get(artist)
        if genre:
            return genre
    return dominant_row_genre(row)


def row_super_genre(row: TrackRow, artist_genres: dict[str, str]) -> str:
    genre = row_assigned_genre(row, artist_genres)
    return super_genre(genre) if genre else "Other"


def count_rows_by_artist(rows: Iterable[TrackRow]) -> RankedRows:
    return top(Counter(artist for row in rows for artist in all_artists(row)), 20)


def track_lookup(tracks: list[TrackRow]) -> dict[str, TrackRow]:
    return {row.get("track_id", ""): row for row in tracks if row.get("track_id")}


def md_escape(value: object) -> str:
    text = str(value if value is not None else "")
    return text.replace("|", "\\|").replace("\n", " ").strip()


def md_link(label: str, target: Path, base_dir: Path) -> str:
    try:
        rel = os.path.relpath(target, base_dir).replace("\\", "/")
    except ValueError:
        rel = target.as_posix()
    return f"[`{label}`]({rel})"


def md_image(label: str, target: Path, base_dir: Path) -> str:
    try:
        rel = os.path.relpath(target, base_dir).replace("\\", "/")
    except ValueError:
        rel = target.as_posix()
    safe_label = label.replace("[", "\\[").replace("]", "\\]")
    return f"![{safe_label}]({rel})"


def external_md_link(label: str, url: str) -> str:
    text = str(label or "").strip()
    target = str(url or "").strip()
    if not target:
        return text
    safe_label = text.replace("[", "\\[").replace("]", "\\]")
    safe_target = target.replace(")", "%29")
    return f"[{safe_label}]({safe_target})"


def external_html_link(label: str, url: str) -> str:
    text = str(label or "").strip()
    target = str(url or "").strip()
    if not target:
        return text
    return SafeHtml(f'<a href="{html_escape(target)}">{compact_html_text(text)}</a>')


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


def compact_html_text(value: object) -> str:
    return (
        html_escape(value)
        .replace(" ", "&nbsp;")
        .replace("-", "&#8209;")
    )


def compact_cell(value: object, *, allow_html: bool = False) -> str:
    cell = str(value if value is not None else "")
    if not allow_html:
        cell = compact_html_text(cell)
    return f"<small><small><small>{cell}</small></small></small>"


def compact_table(headers: list[str], rows: Iterable[Iterable[object]]) -> str:
    rendered = [
        '<div align="center">',
        '<table align="center" cellpadding="0" cellspacing="0">',
        "<thead>",
        "<tr>",
    ]
    for header in headers:
        rendered.append(f'<th align="center" valign="middle" nowrap>{compact_cell(header)}</th>')
    rendered.extend(["</tr>", "</thead>", "<tbody>"])
    for row in rows:
        rendered.append("<tr>")
        for value in row:
            rendered.append(
                f'<td align="center" valign="middle" nowrap>{compact_cell(value, allow_html=isinstance(value, SafeHtml))}</td>'
            )
        rendered.append("</tr>")
    rendered.extend(["</tbody>", "</table>", "</div>"])
    return "\n".join(rendered)


def duration_label(total_ms: int) -> str:
    total_minutes = total_ms // 60000
    hours, minutes = divmod(total_minutes, 60)
    if hours:
        return f"{hours}h {minutes}m"
    return f"{minutes}m"


def ranked_counter_rows(counter: Counter[str]) -> list[tuple[str, int]]:
    return sorted(
        ((name, count) for name, count in counter.items() if name),
        key=lambda item: (-item[1], item[0].casefold()),
    )


def top(counter: Counter[str], limit: int = 12) -> list[tuple[str, int]]:
    return ranked_counter_rows(counter)[:limit]


def html_escape(value: object) -> str:
    return html.escape(str(value if value is not None else ""), quote=True)


def genre_marker_matches(genre: str, marker: str) -> bool:
    genre_text = marker_text(genre)
    marker_text_value = marker_text(marker)
    if not genre_text or not marker_text_value:
        return False
    return bool(re.search(rf"(?:^| ){re.escape(marker_text_value)}(?: |$)", genre_text))


def super_genre(genre: str) -> str:
    for label, markers in SUPER_GENRE_RULES:
        if any(genre_marker_matches(genre, marker) for marker in markers):
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


def recent_liked_rows(tracks: list[TrackRow], limit: int = 20) -> list[list[str]]:
    liked_tracks = [
        row
        for row in tracks
        if "liked" in {source.casefold() for source in split_values(row.get("sources", ""))}
    ]
    liked_tracks.sort(
        key=lambda row: (added_date(row), row.get("track_name", ""), row.get("artist_names", "")),
        reverse=True,
    )
    return [
        [
            date_label(added_date(row)),
            row.get("artist_names", ""),
            external_html_link(row.get("track_name", ""), row.get("spotify_url", "")),
            row.get("album_name", ""),
            effective_year(row),
            effective_primary_genre(row),
        ]
        for row in liked_tracks[:limit]
    ]


def slug(value: str) -> str:
    text = re.sub(r"[^a-z0-9]+", "-", value.casefold()).strip("-")
    return text or "group"


def trim_text(value: str, limit: int) -> str:
    if len(value) <= limit:
        return value
    return value[: max(1, limit - 1)].rstrip() + "…"


def trim_text_to_width(value: str, max_width: float, *, size: int, weight: int = 400) -> str:
    if estimated_text_width(value, size, weight=weight) <= max_width:
        return value
    ellipsis = "…"
    low = 0
    high = len(value)
    while low < high:
        mid = (low + high + 1) // 2
        candidate = value[:mid].rstrip() + ellipsis
        if estimated_text_width(candidate, size, weight=weight) <= max_width:
            low = mid
        else:
            high = mid - 1
    return (value[:low].rstrip() + ellipsis) if low else ellipsis


def estimated_text_width(value: str, size: int, *, weight: int = 400) -> float:
    base_width = size * (0.58 if weight < 700 else 0.62)
    total = 0.0
    for char in value:
        if char == " ":
            total += size * 0.32
        elif char in "il.,'!|":
            total += size * 0.28
        elif char in "mwMW@&":
            total += size * 0.86
        elif char.isdigit():
            total += size * 0.52
        else:
            total += base_width
    return total


def wrap_text_by_width(value: str, max_width: float, *, size: int, weight: int = 400, max_lines: int = 2) -> list[str]:
    if estimated_text_width(value, size, weight=weight) <= max_width:
        return [value]

    words = value.split()
    if len(words) <= 1:
        return [trim_text(value, max(4, int(max_width / (size * 0.62))))]

    lines: list[str] = []
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if current and estimated_text_width(candidate, size, weight=weight) > max_width:
            lines.append(current)
            current = word
            if len(lines) == max_lines - 1:
                break
        else:
            current = candidate

    remainder = " ".join(words[len(" ".join(lines + ([current] if current else [])).split()):])
    if remainder:
        current = f"{current} {remainder}".strip()
    if current:
        lines.append(current)

    if len(lines) > max_lines:
        lines = lines[:max_lines]
    if lines:
        lines[-1] = trim_text(lines[-1], max(4, int(max_width / (size * 0.62))))
    return lines or [value]


def fit_text_lines(value: str, max_width: float, *, size: int, weight: int = 400) -> list[str]:
    estimated_width = estimated_text_width(value, size, weight=weight)
    if estimated_width <= max_width:
        return [value]
    if " " in value and estimated_width <= max_width * 1.42:
        return wrap_text_by_width(value, max_width, size=size, weight=weight)
    return [trim_text_to_width(value, max_width, size=size, weight=weight)]


def svg_text(
    x: float,
    y: float,
    text: object,
    *,
    size: int = 11,
    weight: int = 400,
    fill: str = "#102027",
    anchor: str = "start",
) -> str:
    return (
        f'<text x="{x:.1f}" y="{y:.1f}" font-family="Segoe UI, Arial, sans-serif" '
        f'font-size="{size}" font-weight="{weight}" fill="{fill}" text-anchor="{anchor}">'
        f"{html_escape(text)}</text>"
    )


def genre_stats(
    genre: str,
    tracks: list[TrackRow],
    artist_cache: dict[str, object],
    country_overrides: dict[str, str],
    artist_genres: dict[str, str],
) -> tuple[RankedRows, RankedRows, RankedRows]:
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
    return top(genre_artists, 15), top(genre_years, 15), top(genre_countries, 15)


def build_genre_stat_index(
    tracks: list[TrackRow],
    artist_cache: dict[str, object],
    country_overrides: dict[str, str],
    artist_genres: dict[str, str],
) -> dict[str, tuple[RankedRows, RankedRows, RankedRows]]:
    artist_counts: dict[str, Counter[str]] = {}
    year_counts: dict[str, Counter[str]] = {}
    country_counts: dict[str, Counter[str]] = {}

    for row in tracks:
        artists_by_genre: dict[str, list[str]] = {}
        for artist in all_artists(row):
            genre = artist_genres.get(artist)
            if genre:
                artists_by_genre.setdefault(genre, []).append(artist)

        year = effective_year(row)
        for genre, artists in artists_by_genre.items():
            artist_counts.setdefault(genre, Counter()).update(artists)
            if year.isdigit():
                year_counts.setdefault(genre, Counter())[year] += 1
            country_counter = country_counts.setdefault(genre, Counter())
            for artist in artists:
                country = artist_country(artist, artist_cache, country_overrides)
                if country:
                    country_counter[country] += 1

    genres = set(artist_counts) | set(year_counts) | set(country_counts)
    return {
        genre: (
            top(artist_counts.get(genre, Counter()), 15),
            top(year_counts.get(genre, Counter()), 15),
            top(country_counts.get(genre, Counter()), 15),
        )
        for genre in genres
    }


def display_genre(genre: str, group: str) -> str:
    if group != "Metal":
        return genre
    label = re.sub(r"\bmetal\b", "", genre)
    label = re.sub(r"\s+", " ", label)
    label = label.strip(" -/")
    label = re.sub(r"-$", "", label).strip()
    return label or genre


GROUP_COLORS = {
    "Metal": "#557e64",
    "Rock / Psych / Prog": "#526f92",
    "Electronic / Ambient": "#a96855",
    "Punk / Hardcore": "#8b5d5d",
    "Folk / World": "#7d744e",
    "Jazz / Blues": "#5b7891",
    "Soul / Funk / R&B": "#9a6a3f",
    "Reggae / Ska": "#6f8a58",
    "Afrobeat / Latin": "#b07a45",
    "Classical / Score": "#6f6f88",
    "Pop / Songwriter": "#9a715d",
    "Hip-Hop / Rap": "#6e668a",
    "Experimental / Noise": "#6f7772",
    "Other": "#8a8078",
}


def group_color(group: str, index: int = 0) -> str:
    if group in GROUP_COLORS:
        return GROUP_COLORS[group]
    fallback = ("#557e64", "#526f92", "#a96855", "#7d744e", "#6f7772")
    return fallback[index % len(fallback)]


def group_short_label(group: str) -> str:
    return {
        "Rock / Psych / Prog": "Rock",
        "Electronic / Ambient": "Electronic",
        "Punk / Hardcore": "Punk",
        "Folk / World": "Folk",
        "Jazz / Blues": "Jazz",
        "Soul / Funk / R&B": "Soul",
        "Reggae / Ska": "Reggae",
        "Afrobeat / Latin": "Afrobeat",
        "Classical / Score": "Classical",
        "Pop / Songwriter": "Pop",
        "Hip-Hop / Rap": "Hip-Hop",
        "Experimental / Noise": "Noise",
    }.get(group, group)


def genre_weather_profile(genre: str) -> tuple[str, str, str]:
    text = marker_text(genre)
    if any(marker in text for marker in ("doom", "death", "sludge", "thrash", "heavy", "grind", "hardcore")):
        return "STORM", "heavy", "#557e64"
    if any(marker in text for marker in ("black", "folk", "ritual", "pagan", "neofolk", "dungeon")):
        return "MOON", "ritual", "#7d744e"
    if any(marker in text for marker in ("ambient", "drone", "electronic", "synth", "classical", "score")):
        return "FOG", "ambient", "#526f92"
    if any(marker in text for marker in ("pop", "soul", "funk", "reggae", "ska", "latin", "jazz")):
        return "SUN", "bright", "#a96855"
    if any(marker in text for marker in ("noise", "industrial", "punk", "experimental")):
        return "STATIC", "raw", "#6f7772"
    return "CLOUD", "mixed", "#8a8078"


def taste_drift_data(
    tracks: list[TrackRow],
    artist_genres: dict[str, str],
    *,
    month_limit: int = 18,
    group_limit: int = 5,
) -> tuple[list[str], list[str], dict[str, list[int]]]:
    monthly: dict[str, Counter[str]] = {}
    for row in tracks:
        month = month_label(added_date(row))
        if not month:
            continue
        monthly.setdefault(month, Counter())[row_super_genre(row, artist_genres)] += 1

    months = sorted(monthly)[-month_limit:]
    totals = Counter(
        group
        for month in months
        for group, count in monthly.get(month, Counter()).items()
        for _ in range(count)
    )
    groups = [group for group, _count in top(totals, group_limit)]
    series = {group: [monthly.get(month, Counter()).get(group, 0) for month in months] for group in groups}
    return months, groups, series


def country_decade_data(
    tracks: list[TrackRow],
    artist_cache: dict[str, object],
    country_overrides: dict[str, str],
    *,
    country_limit: int = 12,
) -> tuple[list[str], list[str], dict[tuple[str, str], int]]:
    counts: Counter[str] = Counter()
    matrix: Counter[tuple[str, str]] = Counter()
    decades: set[str] = set()
    for row in tracks:
        decade = decade_label(effective_year(row))
        if not decade:
            continue
        row_countries = track_countries(row, artist_cache, country_overrides)
        if not row_countries:
            continue
        decades.add(decade)
        for country in row_countries:
            counts[country] += 1
            matrix[(country, decade)] += 1

    countries = [country for country, _count in top(counts, country_limit)]
    ordered_decades = sorted(decades, key=lambda label: int(label[:4]))
    return countries, ordered_decades, dict(matrix)


def spotify_cover_wall_items(
    top_cache: dict[str, object],
    recently_played_cache: dict[str, object],
    *,
    limit: int = 36,
) -> list[dict[str, str]]:
    items: list[dict[str, str]] = []
    seen: set[str] = set()

    def add_track(track: object) -> None:
        if not isinstance(track, dict):
            return
        image_url = str(track.get("image_url") or "").strip()
        if not image_url or image_url in seen:
            return
        seen.add(image_url)
        items.append(
            {
                "image_url": image_url,
                "name": str(track.get("name") or "").strip(),
                "artist": str(track.get("artist_names") or "").strip(),
                "url": str(track.get("spotify_url") or "").strip(),
            }
        )

    recent_items = recently_played_cache.get("items")
    if isinstance(recent_items, list):
        for item in recent_items:
            if isinstance(item, dict):
                add_track(item.get("track"))
                if len(items) >= limit:
                    return items

    tracks = top_cache.get("tracks")
    if isinstance(tracks, dict):
        for time_range in ("short_term", "medium_term", "long_term"):
            raw_items = tracks.get(time_range)
            if not isinstance(raw_items, list):
                continue
            for track in raw_items:
                add_track(track)
                if len(items) >= limit:
                    return items

    return items


def spotify_cover_wall_lines(
    top_cache: dict[str, object],
    recently_played_cache: dict[str, object],
) -> list[str]:
    covers = spotify_cover_wall_items(top_cache, recently_played_cache)
    lines = ["### Spotify Covers", ""]
    if not covers:
        return lines + [
            "_No Spotify cover images cached yet. Re-run Spotify export with top/recent scopes._",
            "",
        ]

    lines.append('<p align="left">')
    for item in covers:
        alt = html.escape(" - ".join(part for part in (item["artist"], item["name"]) if part), quote=True)
        src = html.escape(item["image_url"], quote=True)
        url = html.escape(item["url"], quote=True)
        image = f'<img src="{src}" width="72" height="72" alt="{alt}" />'
        if url:
            image = f'<a href="{url}">{image}</a>'
        lines.append(image)
    lines.extend(["</p>", ""])
    return lines

def fallback_top_ranges(tracks: list[TrackRow]) -> tuple[str, dict[str, RankedRows]]:
    dated_rows = [(parse_iso_date(added_date(row)), row) for row in tracks]
    dated = [(date, row) for date, row in dated_rows if date is not None]
    latest_date = max((date for date, _row in dated), default=None)
    if latest_date is None:
        return "library fallback", {
            "short_term": count_rows_by_artist(tracks[:50]),
            "medium_term": count_rows_by_artist(tracks[:250]),
            "long_term": count_rows_by_artist(tracks),
        }

    short_rows = [row for date, row in dated if (latest_date - date).days <= 90]
    medium_rows = [row for date, row in dated if (latest_date - date).days <= 365]
    return "added-date fallback", {
        "short_term": count_rows_by_artist(short_rows),
        "medium_term": count_rows_by_artist(medium_rows),
        "long_term": count_rows_by_artist(tracks),
    }


def cached_top_ranges(cache: dict[str, object]) -> dict[str, RankedRows]:
    artists = cache.get("artists")
    if not isinstance(artists, dict):
        return {}
    ranges: dict[str, RankedRows] = {}
    for time_range in ("short_term", "medium_term", "long_term"):
        raw_items = artists.get(time_range)
        if not isinstance(raw_items, list):
            continue
        rows: RankedRows = []
        for index, item in enumerate(raw_items[:20]):
            if not isinstance(item, dict):
                continue
            name = str(item.get("name") or "").strip()
            if name:
                rows.append((name, 20 - index))
        if rows:
            ranges[time_range] = rows
    return ranges


def top_ranges_data(tracks: list[TrackRow], cache: dict[str, object]) -> tuple[str, dict[str, RankedRows]]:
    cached = cached_top_ranges(cache)
    if all(cached.get(time_range) for time_range in ("short_term", "medium_term", "long_term")):
        return "Spotify top artists", cached
    return fallback_top_ranges(tracks)


def recently_played_track_ids(cache: dict[str, object]) -> list[str]:
    items = cache.get("items")
    if not isinstance(items, list):
        return []
    track_ids: list[str] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        track = item.get("track")
        if not isinstance(track, dict):
            continue
        track_id = str(track.get("id") or "").strip()
        if track_id:
            track_ids.append(track_id)
    return track_ids


def saved_vs_played_data(
    tracks: list[TrackRow],
    artist_genres: dict[str, str],
    recently_played_cache: dict[str, object],
) -> tuple[str, RankedRows, RankedRows, int, int]:
    saved_counts = Counter(row_super_genre(row, artist_genres) for row in tracks)
    lookup = track_lookup(tracks)
    recent_ids = recently_played_track_ids(recently_played_cache)
    source = "Spotify recently played" if recent_ids else "latest saved fallback"
    if recent_ids:
        recent_rows = [lookup[track_id] for track_id in recent_ids if track_id in lookup]
        outside_library = sum(1 for track_id in recent_ids if track_id not in lookup)
    else:
        recent_rows = sorted(tracks, key=lambda row: added_date(row), reverse=True)[:50]
        outside_library = 0

    played_counts = Counter(row_super_genre(row, artist_genres) for row in recent_rows)
    if outside_library:
        played_counts["Outside library"] += outside_library
    rediscovered = len({row.get("track_id", "") for row in recent_rows if row.get("track_id")})
    ignored = max(0, len(tracks) - rediscovered)
    return source, top(saved_counts, 8), top(played_counts, 8), rediscovered, ignored


def svg_rank_column(
    rows: RankedRows,
    *,
    x: float,
    y: float,
    width: float,
    max_chars: int,
    limit: int = 15,
    row_height: int = 18,
    wrap_names: bool = False,
) -> list[str]:
    parts: list[str] = []
    count_x = x + width - 4
    name_width = max(20.0, width - 28)
    for index, (name, count) in enumerate(rows[:limit]):
        row_y = y + index * row_height
        name_lines = (
            fit_text_lines(name, name_width, size=13)
            if wrap_names
            else [trim_text_to_width(trim_text(name, max_chars), name_width, size=13)]
        )
        text_size = 11 if len(name_lines) > 1 else 13
        line_gap = 10 if len(name_lines) > 1 else 13
        text_y = row_y - 2 if len(name_lines) > 1 else row_y
        for line_index, line in enumerate(name_lines):
            parts.append(svg_text(x, text_y + line_index * line_gap, line, size=text_size))
        parts.append(
            svg_text(
                count_x,
                row_y,
                count,
                size=13,
                weight=800,
                fill="#526f92",
                anchor="end",
            )
        )
    return parts


def svg_fitted_text(
    x: float,
    y: float,
    text: object,
    *,
    max_width: float,
    size: int,
    min_size: int = 12,
    weight: int = 800,
    fill: str = "#102027",
    anchor: str = "start",
) -> str:
    value = str(text if text is not None else "")
    fitted_size = size
    while (
        fitted_size > min_size
        and estimated_text_width(value, fitted_size, weight=weight) > max_width
    ):
        fitted_size -= 1
    return svg_text(
        x,
        y,
        trim_text_to_width(value, max_width, size=fitted_size, weight=weight),
        size=fitted_size,
        weight=weight,
        fill=fill,
        anchor=anchor,
    )


def svg_bar_rows(
    rows: RankedRows,
    *,
    x: float,
    y: float,
    width: float,
    accent: str,
    limit: int = 20,
    row_height: int = 24,
) -> list[str]:
    visible_rows = rows[:limit]
    if not visible_rows:
        return [svg_text(x, y, "No data", size=13, fill="#7a827b")]

    parts: list[str] = []
    max_count = max(count for _name, count in visible_rows)
    rank_x = x
    name_x = x + 34
    count_x = x + width - 4
    bar_x = name_x
    bar_width_max = max(24.0, width - 86)
    name_width = max(40.0, width - 104)

    for index, (name, count) in enumerate(visible_rows, start=1):
        row_y = y + (index - 1) * row_height
        bar_width = bar_width_max * count / max_count if max_count else 0
        parts.extend(
            [
                f'<rect x="{bar_x:.1f}" y="{row_y - 14:.1f}" width="{bar_width:.1f}" height="16" fill="{accent}" fill-opacity="0.18"/>',
                svg_text(rank_x, row_y, f"{index:02d}", size=10, weight=800, fill=accent),
                svg_text(
                    name_x,
                    row_y,
                    trim_text_to_width(name, name_width, size=12),
                    size=12,
                ),
                svg_text(count_x, row_y, count, size=12, weight=800, fill=accent, anchor="end"),
            ]
        )
    return parts


def write_overview_svg(path: Path, metrics: list[tuple[str, object]]) -> None:
    width = 1200
    margin = 16
    gap = 8
    columns = 3
    header_height = 54
    card_height = 92
    content_top = margin + header_height + 12
    rows = (len(metrics) + columns - 1) // columns
    card_width = (width - margin * 2 - gap * (columns - 1)) / columns
    height = content_top + rows * card_height + max(0, rows - 1) * gap + margin
    colors = ("#557e64", "#526f92", "#a96855")

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-label="Spotify library overview">',
        f'<rect width="{width}" height="{height}" fill="#f7f6f0"/>',
        f'<rect x="{margin}" y="{margin}" width="{width - margin * 2}" height="{header_height}" fill="#22382d"/>',
        svg_text(margin + 16, margin + 35, "Library Overview", size=28, weight=800, fill="#ffffff"),
        svg_text(
            width - margin - 16,
            margin + 35,
            "Spotify metadata dashboard",
            size=15,
            weight=800,
            fill="#dfe8df",
            anchor="end",
        ),
    ]

    for index, (label, value) in enumerate(metrics):
        row_index, col_index = divmod(index, columns)
        x = margin + col_index * (card_width + gap)
        y = content_top + row_index * (card_height + gap)
        accent = colors[index % len(colors)]
        parts.extend(
            [
                f'<rect x="{x:.1f}" y="{y:.1f}" width="{card_width:.1f}" height="{card_height}" fill="#fffefa" stroke="#c7d0c7"/>',
                f'<rect x="{x:.1f}" y="{y:.1f}" width="4" height="{card_height}" fill="{accent}"/>',
                svg_text(x + 18, y + 30, str(label).upper(), size=13, weight=800, fill=accent),
                svg_fitted_text(
                    x + 18,
                    y + 72,
                    value,
                    max_width=card_width - 36,
                    size=34,
                    min_size=20,
                    weight=800,
                ),
            ]
        )

    parts.append("</svg>")
    path.parent.mkdir(parents=True, exist_ok=True)
    write_text_lf(path, "\n".join(parts) + "\n")


def write_aggregates_svg(
    path: Path,
    country_rows: RankedRows,
    genre_rows: RankedRows,
    artist_rows: RankedRows,
) -> None:
    width = 1200
    margin = 16
    gap = 8
    columns = 3
    header_height = 54
    row_height = 24
    row_limit = 20
    card_top = margin + header_height + 12
    card_width = (width - margin * 2 - gap * (columns - 1)) / columns
    card_height = 72 + row_limit * row_height + 18
    height = card_top + card_height + margin
    sections = [
        ("Top Countries", country_rows, "#557e64"),
        ("Assigned Genres", genre_rows, "#526f92"),
        ("Groups / Artists", artist_rows, "#a96855"),
    ]

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-label="Spotify aggregate top lists">',
        f'<rect width="{width}" height="{height}" fill="#f7f6f0"/>',
        f'<rect x="{margin}" y="{margin}" width="{width - margin * 2}" height="{header_height}" fill="#22382d"/>',
        svg_text(margin + 16, margin + 35, "Aggregate Top Lists", size=28, weight=800, fill="#ffffff"),
        svg_text(
            width - margin - 16,
            margin + 35,
            "Countries, genres and artists",
            size=15,
            weight=800,
            fill="#dfe8df",
            anchor="end",
        ),
    ]

    for index, (title, rows, accent) in enumerate(sections):
        x = margin + index * (card_width + gap)
        y = card_top
        top_count = min(row_limit, len(rows))
        parts.extend(
            [
                f'<rect x="{x:.1f}" y="{y:.1f}" width="{card_width:.1f}" height="{card_height}" fill="#fffefa" stroke="#c7d0c7"/>',
                f'<rect x="{x:.1f}" y="{y:.1f}" width="4" height="{card_height}" fill="{accent}"/>',
                f'<rect x="{x + 4:.1f}" y="{y:.1f}" width="{card_width - 4:.1f}" height="48" fill="#edf2ed"/>',
                svg_fitted_text(
                    x + 16,
                    y + 31,
                    title,
                    max_width=card_width - 118,
                    size=22,
                    min_size=16,
                    weight=800,
                ),
                svg_text(
                    x + card_width - 14,
                    y + 30,
                    f"top {top_count}",
                    size=13,
                    weight=800,
                    fill=accent,
                    anchor="end",
                ),
            ]
        )
        parts.extend(
            svg_bar_rows(
                rows,
                x=x + 16,
                y=y + 74,
                width=card_width - 32,
                accent=accent,
                limit=row_limit,
                row_height=row_height,
            )
        )

    parts.append("</svg>")
    path.parent.mkdir(parents=True, exist_ok=True)
    write_text_lf(path, "\n".join(parts) + "\n")


def write_taste_drift_svg(
    path: Path,
    months: list[str],
    groups: list[str],
    series: dict[str, list[int]],
) -> None:
    width = 1200
    height = 430
    margin = 16
    header_height = 54
    chart_x = 72
    chart_y = 108
    chart_width = 1048
    chart_height = 230
    chart_bottom = chart_y + chart_height
    max_total = max((sum(values) for values in zip(*(series.get(group, []) for group in groups))), default=0)

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-label="Taste drift by month">',
        f'<rect width="{width}" height="{height}" fill="#f7f6f0"/>',
        f'<rect x="{margin}" y="{margin}" width="{width - margin * 2}" height="{header_height}" fill="#22382d"/>',
        svg_text(margin + 16, margin + 35, "Taste Drift", size=28, weight=800, fill="#ffffff"),
        svg_text(width - margin - 16, margin + 35, "Genre mix by added month", size=15, weight=800, fill="#dfe8df", anchor="end"),
        f'<rect x="{chart_x}" y="{chart_y}" width="{chart_width}" height="{chart_height}" fill="#fffefa" stroke="#c7d0c7"/>',
    ]

    if not months or not groups or max_total <= 0:
        parts.append(svg_text(width / 2, 235, "Not enough dated tracks yet", size=18, weight=800, fill="#6f7772", anchor="middle"))
    else:
        x_positions = [
            chart_x + (chart_width * index / max(1, len(months) - 1))
            for index in range(len(months))
        ]
        scale = chart_height / max_total
        cumulative = [0] * len(months)
        for group_index, group in enumerate(groups):
            values = series.get(group, [0] * len(months))
            upper_points: list[tuple[float, float]] = []
            lower_points: list[tuple[float, float]] = []
            for index, value in enumerate(values):
                lower = cumulative[index]
                cumulative[index] += value
                upper_points.append((x_positions[index], chart_bottom - cumulative[index] * scale))
                lower_points.append((x_positions[index], chart_bottom - lower * scale))
            points = " ".join(
                f"{x:.1f},{y:.1f}" for x, y in upper_points + list(reversed(lower_points))
            )
            parts.append(
                f'<polygon points="{points}" fill="{group_color(group, group_index)}" fill-opacity="0.78"/>'
            )

        tick_step = max(1, len(months) // 6)
        for index, month in enumerate(months):
            x = x_positions[index]
            if index % tick_step == 0 or index == len(months) - 1:
                parts.extend(
                    [
                        f'<line x1="{x:.1f}" y1="{chart_bottom}" x2="{x:.1f}" y2="{chart_bottom + 6}" stroke="#7a827b"/>',
                        svg_text(x, chart_bottom + 24, f"{month[5:7]}/{month[2:4]}", size=11, fill="#5d6b62", anchor="middle"),
                    ]
                )
        parts.append(svg_text(chart_x - 12, chart_y + 5, max_total, size=12, weight=800, fill="#526f92", anchor="end"))
        parts.append(svg_text(chart_x - 12, chart_bottom, "0", size=12, fill="#5d6b62", anchor="end"))
        parts.append(f'<line x1="{chart_x}" y1="{chart_bottom}" x2="{chart_x + chart_width}" y2="{chart_bottom}" stroke="#7a827b"/>')

        peak_index = max(range(len(months)), key=lambda index: sum(series[group][index] for group in groups))
        peak_x = x_positions[peak_index]
        peak_total = sum(series[group][peak_index] for group in groups)
        peak_y = chart_bottom - peak_total * scale
        parts.extend(
            [
                f'<circle cx="{peak_x:.1f}" cy="{peak_y:.1f}" r="5" fill="#a96855"/>',
                svg_text(min(peak_x + 10, chart_x + chart_width - 140), max(chart_y + 18, peak_y - 8), f"peak {months[peak_index]}: {peak_total}", size=12, weight=800, fill="#a96855"),
            ]
        )

        legend_x = chart_x
        legend_y = 386
        for group_index, group in enumerate(groups):
            x = legend_x + group_index * 210
            parts.extend(
                [
                    f'<rect x="{x:.1f}" y="{legend_y - 13}" width="14" height="14" fill="{group_color(group, group_index)}"/>',
                    svg_text(x + 22, legend_y, group_short_label(group), size=13, weight=800, fill="#102027"),
                ]
            )

    parts.append("</svg>")
    path.parent.mkdir(parents=True, exist_ok=True)
    write_text_lf(path, "\n".join(parts) + "\n")

def svg_weather_icon(kind: str, x: float, y: float, accent: str) -> list[str]:
    if kind == "STORM":
        return [
            f'<circle cx="{x + 22:.1f}" cy="{y + 18:.1f}" r="15" fill="{accent}" fill-opacity="0.18"/>',
            f'<circle cx="{x + 40:.1f}" cy="{y + 16:.1f}" r="18" fill="{accent}" fill-opacity="0.24"/>',
            f'<rect x="{x + 12:.1f}" y="{y + 20:.1f}" width="48" height="17" rx="8" fill="{accent}" fill-opacity="0.22"/>',
            f'<path d="M{x + 34:.1f},{y + 32:.1f} L{x + 24:.1f},{y + 52:.1f} L{x + 37:.1f},{y + 49:.1f} L{x + 29:.1f},{y + 66:.1f} L{x + 50:.1f},{y + 42:.1f} L{x + 37:.1f},{y + 45:.1f} Z" fill="{accent}"/>',
        ]
    if kind == "MOON":
        return [
            f'<circle cx="{x + 34:.1f}" cy="{y + 34:.1f}" r="25" fill="{accent}" fill-opacity="0.88"/>',
            f'<circle cx="{x + 45:.1f}" cy="{y + 27:.1f}" r="25" fill="#fffefa"/>',
            f'<circle cx="{x + 15:.1f}" cy="{y + 14:.1f}" r="2.5" fill="{accent}" fill-opacity="0.45"/>',
            f'<circle cx="{x + 55:.1f}" cy="{y + 55:.1f}" r="2" fill="{accent}" fill-opacity="0.45"/>',
        ]
    if kind == "FOG":
        return [
            f'<circle cx="{x + 23:.1f}" cy="{y + 18:.1f}" r="14" fill="{accent}" fill-opacity="0.15"/>',
            f'<circle cx="{x + 41:.1f}" cy="{y + 18:.1f}" r="17" fill="{accent}" fill-opacity="0.18"/>',
            f'<path d="M{x + 8:.1f},{y + 39:.1f} C{x + 25:.1f},{y + 31:.1f} {x + 42:.1f},{y + 47:.1f} {x + 62:.1f},{y + 38:.1f}" fill="none" stroke="{accent}" stroke-width="4" stroke-linecap="round" opacity="0.72"/>',
            f'<path d="M{x + 8:.1f},{y + 51:.1f} C{x + 26:.1f},{y + 43:.1f} {x + 43:.1f},{y + 58:.1f} {x + 62:.1f},{y + 50:.1f}" fill="none" stroke="{accent}" stroke-width="4" stroke-linecap="round" opacity="0.52"/>',
        ]
    if kind == "SUN":
        rays = []
        for dx1, dy1, dx2, dy2 in ((34, 0, 34, 9), (34, 59, 34, 68), (0, 34, 9, 34), (59, 34, 68, 34), (10, 10, 17, 17), (51, 51, 58, 58), (58, 10, 51, 17), (17, 51, 10, 58)):
            rays.append(f'<line x1="{x + dx1:.1f}" y1="{y + dy1:.1f}" x2="{x + dx2:.1f}" y2="{y + dy2:.1f}" stroke="{accent}" stroke-width="3" stroke-linecap="round" opacity="0.7"/>')
        return rays + [f'<circle cx="{x + 34:.1f}" cy="{y + 34:.1f}" r="19" fill="{accent}" fill-opacity="0.76"/>']
    if kind == "STATIC":
        return [
            f'<rect x="{x + 8:.1f}" y="{y + 9:.1f}" width="52" height="44" fill="{accent}" fill-opacity="0.13"/>',
            f'<path d="M{x + 12:.1f},{y + 18:.1f} H{x + 58:.1f} M{x + 16:.1f},{y + 30:.1f} H{x + 48:.1f} M{x + 10:.1f},{y + 42:.1f} H{x + 55:.1f}" stroke="{accent}" stroke-width="4" stroke-linecap="square" opacity="0.76"/>',
            f'<path d="M{x + 19:.1f},{y + 9:.1f} V{y + 53:.1f} M{x + 42:.1f},{y + 9:.1f} V{y + 53:.1f}" stroke="{accent}" stroke-width="2" opacity="0.24"/>',
        ]
    return [
        f'<circle cx="{x + 23:.1f}" cy="{y + 22:.1f}" r="17" fill="{accent}" fill-opacity="0.17"/>',
        f'<circle cx="{x + 42:.1f}" cy="{y + 20:.1f}" r="21" fill="{accent}" fill-opacity="0.23"/>',
        f'<circle cx="{x + 54:.1f}" cy="{y + 31:.1f}" r="15" fill="{accent}" fill-opacity="0.19"/>',
        f'<rect x="{x + 11:.1f}" y="{y + 27:.1f}" width="57" height="22" rx="11" fill="{accent}" fill-opacity="0.21"/>',
    ]

def write_genre_weather_svg(path: Path, genre_rows: RankedRows) -> None:
    width = 1200
    margin = 16
    gap = 8
    columns = 4
    tile_width = (width - margin * 2 - gap * (columns - 1)) / columns
    tile_height = 112
    header_height = 54
    rows = (min(24, len(genre_rows)) + columns - 1) // columns
    content_top = margin + header_height + 12
    height = content_top + rows * tile_height + max(0, rows - 1) * gap + margin
    visible = genre_rows[:24]
    max_count = max((count for _genre, count in visible), default=1)

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-label="Genre weather map">',
        f'<rect width="{width}" height="{height}" fill="#f7f6f0"/>',
        f'<rect x="{margin}" y="{margin}" width="{width - margin * 2}" height="{header_height}" fill="#22382d"/>',
        svg_text(margin + 16, margin + 35, "Genre Weather", size=28, weight=800, fill="#ffffff"),
        svg_text(width - margin - 16, margin + 35, "Mood intensity from assigned genres", size=15, weight=800, fill="#dfe8df", anchor="end"),
    ]

    for index, (genre, count) in enumerate(visible):
        row_index, col_index = divmod(index, columns)
        x = margin + col_index * (tile_width + gap)
        y = content_top + row_index * (tile_height + gap)
        icon, mood, accent = genre_weather_profile(genre)
        intensity = max(1, min(5, round(count / max_count * 5)))
        parts.extend(
            [
                f'<rect x="{x:.1f}" y="{y:.1f}" width="{tile_width:.1f}" height="{tile_height}" fill="#fffefa" stroke="#c7d0c7"/>',
                f'<rect x="{x:.1f}" y="{y:.1f}" width="4" height="{tile_height}" fill="{accent}"/>',
                *svg_weather_icon(icon, x + 16, y + 16, accent),
                svg_text(x + 96, y + 28, icon, size=12, weight=800, fill=accent),
                svg_text(x + 96, y + 48, mood.upper(), size=12, weight=800, fill=accent),
                svg_text(x + tile_width - 14, y + 28, count, size=13, weight=800, fill=accent, anchor="end"),
                svg_fitted_text(x + 16, y + 86, genre, max_width=tile_width - 32, size=18, min_size=12, weight=800),
            ]
        )
        for bar_index in range(5):
            bar_x = x + 16 + bar_index * 28
            fill = accent if bar_index < intensity else "#d9ded7"
            parts.append(f'<rect x="{bar_x:.1f}" y="{y + 98}" width="20" height="8" fill="{fill}"/>')

    parts.append("</svg>")
    path.parent.mkdir(parents=True, exist_ok=True)
    write_text_lf(path, "\n".join(parts) + "\n")


def write_country_decade_svg(
    path: Path,
    countries: list[str],
    decades: list[str],
    matrix: dict[tuple[str, str], int],
) -> None:
    width = 1200
    margin = 16
    header_height = 54
    left = 170
    top_y = margin + header_height + 54
    row_height = 30
    cell_gap = 4
    cell_width = (width - left - margin - cell_gap * max(0, len(decades) - 1)) / max(1, len(decades))
    height = top_y + len(countries) * row_height + 42
    max_count = max(matrix.values(), default=1)

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-label="Countries by decade heatmap">',
        f'<rect width="{width}" height="{height}" fill="#f7f6f0"/>',
        f'<rect x="{margin}" y="{margin}" width="{width - margin * 2}" height="{header_height}" fill="#22382d"/>',
        svg_text(margin + 16, margin + 35, "Country x Decade", size=28, weight=800, fill="#ffffff"),
        svg_text(width - margin - 16, margin + 35, "Origin heatmap by release year", size=15, weight=800, fill="#dfe8df", anchor="end"),
    ]

    if not countries or not decades:
        parts.append(svg_text(width / 2, 180, "Country or year data is still too sparse", size=18, weight=800, fill="#6f7772", anchor="middle"))
    else:
        for col_index, decade in enumerate(decades):
            x = left + col_index * (cell_width + cell_gap)
            parts.append(svg_text(x + cell_width / 2, top_y - 14, decade, size=12, weight=800, fill="#5d6b62", anchor="middle"))
        for row_index, country in enumerate(countries):
            y = top_y + row_index * row_height
            parts.append(svg_text(left - 14, y + 18, trim_text_to_width(country, 140, size=13), size=13, fill="#102027", anchor="end"))
            for col_index, decade in enumerate(decades):
                x = left + col_index * (cell_width + cell_gap)
                count = matrix.get((country, decade), 0)
                opacity = 0.08 + (0.84 * count / max_count if count else 0)
                parts.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{cell_width:.1f}" height="24" fill="#557e64" fill-opacity="{opacity:.2f}"/>')
                if count:
                    parts.append(svg_text(x + cell_width / 2, y + 17, count, size=10, weight=800, fill="#102027", anchor="middle"))
        parts.extend(
            [
                svg_text(left, height - 14, "lighter", size=11, fill="#5d6b62"),
                f'<rect x="{left + 52}" y="{height - 24}" width="44" height="10" fill="#557e64" fill-opacity="0.16"/>',
                f'<rect x="{left + 100}" y="{height - 24}" width="44" height="10" fill="#557e64" fill-opacity="0.42"/>',
                f'<rect x="{left + 148}" y="{height - 24}" width="44" height="10" fill="#557e64" fill-opacity="0.78"/>',
                svg_text(left + 204, height - 14, "denser", size=11, fill="#5d6b62"),
            ]
        )

    parts.append("</svg>")
    path.parent.mkdir(parents=True, exist_ok=True)
    write_text_lf(path, "\n".join(parts) + "\n")

def range_delta_label(name: str, current: RankedRows, previous: RankedRows) -> str:
    current_rank = {item_name: index for index, (item_name, _score) in enumerate(current, start=1)}
    previous_rank = {item_name: index for index, (item_name, _score) in enumerate(previous, start=1)}
    if name not in previous_rank:
        return "new"
    delta = previous_rank[name] - current_rank.get(name, previous_rank[name])
    if delta > 0:
        return f"up {delta}"
    if delta < 0:
        return f"down {abs(delta)}"
    return "same"

def write_top_ranges_svg(path: Path, source: str, ranges: dict[str, RankedRows]) -> None:
    width = 1200
    height = 608
    margin = 16
    gap = 8
    header_height = 54
    columns = 3
    card_width = (width - margin * 2 - gap * (columns - 1)) / columns
    card_height = 510
    content_top = margin + header_height + 12
    specs = [
        ("short_term", "Short Term", "#557e64"),
        ("medium_term", "Medium Term", "#526f92"),
        ("long_term", "Long Term", "#a96855"),
    ]

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-label="Top artists across Spotify ranges">',
        f'<rect width="{width}" height="{height}" fill="#f7f6f0"/>',
        f'<rect x="{margin}" y="{margin}" width="{width - margin * 2}" height="{header_height}" fill="#22382d"/>',
        svg_text(margin + 16, margin + 35, "Top Items: Short / Medium / Long", size=28, weight=800, fill="#ffffff"),
        svg_text(width - margin - 16, margin + 35, source, size=15, weight=800, fill="#dfe8df", anchor="end"),
    ]

    previous_rows: RankedRows = []
    for index, (key, title, accent) in enumerate(specs):
        rows = ranges.get(key, [])[:15]
        x = margin + index * (card_width + gap)
        y = content_top
        parts.extend(
            [
                f'<rect x="{x:.1f}" y="{y:.1f}" width="{card_width:.1f}" height="{card_height}" fill="#fffefa" stroke="#c7d0c7"/>',
                f'<rect x="{x:.1f}" y="{y:.1f}" width="4" height="{card_height}" fill="{accent}"/>',
                f'<rect x="{x + 4:.1f}" y="{y:.1f}" width="{card_width - 4:.1f}" height="46" fill="#edf2ed"/>',
                svg_text(x + 16, y + 30, title, size=21, weight=800),
            ]
        )
        if not rows:
            parts.append(svg_text(x + 18, y + 92, "No range data yet", size=14, fill="#6f7772"))
        for row_index, (name, _score) in enumerate(rows, start=1):
            row_y = y + 70 + (row_index - 1) * 28
            tag = range_delta_label(name, rows, previous_rows)
            parts.extend(
                [
                    svg_text(x + 18, row_y, f"{row_index:02d}", size=10, weight=800, fill=accent),
                    svg_text(x + 56, row_y, trim_text_to_width(name, card_width - 126, size=13), size=13),
                    svg_text(x + card_width - 14, row_y, tag, size=10, weight=800, fill=accent, anchor="end"),
                ]
            )
        previous_rows = rows

    parts.append("</svg>")
    path.parent.mkdir(parents=True, exist_ok=True)
    write_text_lf(path, "\n".join(parts) + "\n")


def write_saved_vs_played_svg(
    path: Path,
    source: str,
    saved_rows: RankedRows,
    played_rows: RankedRows,
    rediscovered: int,
    ignored: int,
) -> None:
    width = 1200
    height = 500
    margin = 16
    header_height = 54
    chart_x = 180
    chart_y = 126
    row_height = 42
    bar_width = 410
    gap = 20
    saved = dict(saved_rows)
    played = dict(played_rows)
    groups = [group for group, _count in top(Counter(saved) + Counter(played), 8)]
    max_count = max(list(saved.values()) + list(played.values()) + [1])

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-label="Saved library versus recently played">',
        f'<rect width="{width}" height="{height}" fill="#f7f6f0"/>',
        f'<rect x="{margin}" y="{margin}" width="{width - margin * 2}" height="{header_height}" fill="#22382d"/>',
        svg_text(margin + 16, margin + 35, "Saved vs Played", size=28, weight=800, fill="#ffffff"),
        svg_text(width - margin - 16, margin + 35, source, size=15, weight=800, fill="#dfe8df", anchor="end"),
        svg_text(chart_x, 104, "saved library", size=13, weight=800, fill="#557e64"),
        svg_text(chart_x + bar_width + gap, 104, "recent plays", size=13, weight=800, fill="#526f92"),
    ]

    for index, group in enumerate(groups):
        y = chart_y + index * row_height
        saved_count = saved.get(group, 0)
        played_count = played.get(group, 0)
        saved_width = bar_width * saved_count / max_count
        played_width = bar_width * played_count / max_count
        parts.extend(
            [
                svg_text(chart_x - 14, y + 15, trim_text_to_width(group_short_label(group), 140, size=12), size=12, anchor="end"),
                f'<rect x="{chart_x:.1f}" y="{y:.1f}" width="{bar_width}" height="18" fill="#d9ded7"/>',
                f'<rect x="{chart_x:.1f}" y="{y:.1f}" width="{saved_width:.1f}" height="18" fill="#557e64" fill-opacity="0.78"/>',
                f'<rect x="{chart_x + bar_width + gap:.1f}" y="{y:.1f}" width="{bar_width}" height="18" fill="#d9ded7"/>',
                f'<rect x="{chart_x + bar_width + gap:.1f}" y="{y:.1f}" width="{played_width:.1f}" height="18" fill="#526f92" fill-opacity="0.78"/>',
                svg_text(chart_x + bar_width + 6, y + 15, saved_count, size=11, weight=800, fill="#557e64"),
                svg_text(chart_x + bar_width + gap + played_width + 6, y + 15, played_count, size=11, weight=800, fill="#526f92"),
            ]
        )

    callout_y = height - 54
    parts.extend(
        [
            f'<rect x="{margin}" y="{callout_y - 24}" width="568" height="42" fill="#fffefa" stroke="#c7d0c7"/>',
            f'<rect x="{616}" y="{callout_y - 24}" width="568" height="42" fill="#fffefa" stroke="#c7d0c7"/>',
            svg_text(margin + 16, callout_y + 2, f"rediscovered: {rediscovered} recent library tracks", size=14, weight=800, fill="#557e64"),
            svg_text(632, callout_y + 2, f"ignored favorites: {ignored} saved tracks outside this snapshot", size=14, weight=800, fill="#a96855"),
        ]
    )

    parts.append("</svg>")
    path.parent.mkdir(parents=True, exist_ok=True)
    write_text_lf(path, "\n".join(parts) + "\n")


def write_genre_group_svg(
    path: Path,
    group: str,
    group_rows: RankedRows,
    group_tracks: int,
    card_offset: int,
    genre_stat_index: dict[str, tuple[RankedRows, RankedRows, RankedRows]],
) -> None:
    width = 1200
    margin = 16
    gap = 8
    columns = 2
    top_limit = 15
    rank_row_height = 18
    first_row_offset = 76
    card_width = (width - margin * 2 - gap * (columns - 1)) / columns
    header_height = 48
    content_top = margin + header_height + 12
    colors = ("#557e64", "#526f92", "#a96855")

    card_stats: list[tuple[str, int, RankedRows, RankedRows, RankedRows, int]] = []
    for genre, count in group_rows:
        artists, years, countries = genre_stat_index.get(genre, ([], [], []))
        visible_rows = max(
            1,
            len(artists[:top_limit]),
            len(years[:top_limit]),
            len(countries[:top_limit]),
        )
        card_height = first_row_offset + 10 + visible_rows * rank_row_height
        card_stats.append((genre, count, artists, years, countries, card_height))

    card_positions: list[tuple[float, float]] = []
    row_heights = [
        max(card[-1] for card in card_stats[index : index + columns])
        for index in range(0, len(card_stats), columns)
    ]
    row_offsets: list[float] = []
    current_y = 0.0
    for row_height in row_heights:
        row_offsets.append(current_y)
        current_y += row_height + gap
    for local_index, _card in enumerate(card_stats):
        row_index, col_index = divmod(local_index, columns)
        x = margin + col_index * (card_width + gap)
        y = content_top + row_offsets[row_index]
        card_positions.append((x, y))
    content_height = sum(row_heights) + max(0, len(row_heights) - 1) * gap
    height = content_top + content_height + margin

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-label="{html_escape(group)} genre atlas">',
        f'<rect width="{width}" height="{height}" fill="#f7f6f0"/>',
        f'<rect x="{margin}" y="{margin}" width="{width - margin * 2}" height="{header_height}" fill="#22382d"/>',
        svg_text(margin + 14, margin + 32, group, size=25, weight=800, fill="#ffffff"),
        svg_text(
            width - margin - 14,
            margin + 32,
            f"{len(group_rows)} genres · {group_tracks} tracks",
            size=15,
            weight=800,
            fill="#dfe8df",
            anchor="end",
        ),
    ]

    for local_index, (genre, count, artists, years, countries, card_height) in enumerate(card_stats):
        x, y = card_positions[local_index]
        row_index = local_index // columns
        display_card_height = row_heights[row_index]
        accent = colors[(card_offset + local_index) % len(colors)]
        number = card_offset + local_index + 1
        artists_x = x + 14
        years_x = x + card_width * 0.60
        countries_x = x + card_width * 0.77
        header_y = y + 56

        parts.extend(
            [
                f'<rect x="{x:.1f}" y="{y:.1f}" width="{card_width:.1f}" height="{display_card_height}" fill="#fffefa" stroke="#c7d0c7"/>',
                f'<rect x="{x:.1f}" y="{y:.1f}" width="4" height="{display_card_height}" fill="{accent}"/>',
                f'<rect x="{x + 4:.1f}" y="{y:.1f}" width="{card_width - 4:.1f}" height="40" fill="#edf2ed"/>',
                svg_text(x + 14, y + 27, f"{number:02d}", size=12, weight=800, fill="#a96855"),
                svg_text(x + 52, y + 28, trim_text(display_genre(genre, group), 40), size=22, weight=800),
                svg_text(
                    x + card_width - 12,
                    y + 26,
                    f"{count} total · top 15",
                    size=13,
                    weight=800,
                    fill="#557e64",
                    anchor="end",
                ),
                svg_text(artists_x, header_y, "ARTISTS", size=13, weight=800, fill="#5d6b62"),
                svg_text(years_x, header_y, "YEARS", size=13, weight=800, fill="#5d6b62"),
                svg_text(countries_x, header_y, "COUNTRIES", size=13, weight=800, fill="#5d6b62"),
                f'<line x1="{years_x - 14:.1f}" y1="{y + 50}" x2="{years_x - 14:.1f}" y2="{y + display_card_height - 12}" stroke="#cfd6ce"/>',
                f'<line x1="{countries_x - 14:.1f}" y1="{y + 50}" x2="{countries_x - 14:.1f}" y2="{y + display_card_height - 12}" stroke="#cfd6ce"/>',
            ]
        )
        row_y = y + first_row_offset
        parts.extend(
            svg_rank_column(
                artists,
                x=artists_x,
                y=row_y,
                width=card_width * 0.55 - 24,
                max_chars=30,
                limit=top_limit,
                row_height=rank_row_height,
                wrap_names=True,
            )
        )
        parts.extend(
            svg_rank_column(
                years,
                x=years_x,
                y=row_y,
                width=card_width * 0.14,
                max_chars=4,
                limit=top_limit,
                row_height=rank_row_height,
            )
        )
        parts.extend(
            svg_rank_column(
                countries,
                x=countries_x,
                y=row_y,
                width=card_width * 0.21,
                max_chars=20,
                limit=top_limit,
                row_height=rank_row_height,
            )
        )

    parts.append("</svg>")
    path.parent.mkdir(parents=True, exist_ok=True)
    write_text_lf(path, "\n".join(parts) + "\n")


def replace_directory_after_success(target: Path, source: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    for stale_backup in target.parent.glob(f".{target.name}.backup*"):
        remove_tree_best_effort(stale_backup)
    backup = target.parent / f".{target.name}.backup-{os.getpid()}"
    target_was_moved = False
    try:
        if target.exists():
            target.rename(backup)
            target_was_moved = True
        source.rename(target)
    except Exception:
        if target_was_moved and backup.exists() and not target.exists():
            backup.rename(target)
        raise
    finally:
        remove_tree_best_effort(backup)


def remove_tree_best_effort(path: Path) -> None:
    def clear_readonly(function: object, item_path: str, _error: object) -> None:
        try:
            os.chmod(item_path, stat.S_IWRITE)
            function(item_path)
        except OSError:
            return

    for attempt in range(4):
        if not path.exists():
            return
        try:
            shutil.rmtree(path, onexc=clear_readonly)
            return
        except OSError:
            if attempt == 3:
                return
            time.sleep(0.25)


def genre_atlas(
    tracks: list[TrackRow],
    artist_cache: dict[str, object],
    country_overrides: dict[str, str],
    genre_rows: RankedRows,
    artist_genres: dict[str, str],
    readme_dir: Path,
    atlas_dir: Path,
) -> list[str]:
    atlas_dir.parent.mkdir(parents=True, exist_ok=True)
    staging_dir = Path(
        tempfile.mkdtemp(prefix=f".{atlas_dir.name}.", dir=atlas_dir.parent)
    )
    staging_active = True

    try:
        genre_stat_index = build_genre_stat_index(
            tracks,
            artist_cache,
            country_overrides,
            artist_genres,
        )

        grouped: dict[str, RankedRows] = {}
        for genre, count in genre_rows:
            grouped.setdefault(super_genre(genre), []).append((genre, count))

        lines: list[str] = ["## Genre Atlas", ""]
        group_order = [label for label, _markers in SUPER_GENRE_RULES] + ["Other"]
        card_index = 0
        generated_files: list[Path] = []
        for group in group_order:
            group_rows = grouped.get(group, [])
            if not group_rows:
                continue
            group_tracks = sum(count for _genre, count in group_rows)
            file_name = f"{slug(group)}.svg"
            staging_path = staging_dir / file_name
            final_path = atlas_dir / file_name
            write_genre_group_svg(
                staging_path,
                group,
                group_rows,
                group_tracks,
                card_index,
                genre_stat_index,
            )
            generated_files.append(staging_path)
            rel_path = os.path.relpath(final_path, readme_dir).replace("\\", "/")
            lines.extend(
                [
                    f"## {group}",
                    "",
                    f"![{group} genre atlas]({rel_path})",
                    "",
                ]
            )
            card_index += len(group_rows)

        missing_files = [path for path in generated_files if not path.exists()]
        if missing_files:
            missing = ", ".join(path.name for path in missing_files)
            raise RuntimeError(f"Atlas generation did not create expected SVG(s): {missing}")

        replace_directory_after_success(atlas_dir, staging_dir)
        staging_active = False
        return lines
    finally:
        if staging_active and staging_dir.exists():
            shutil.rmtree(staging_dir)


def listening_maps(
    tracks: list[TrackRow],
    artist_cache: dict[str, object],
    country_overrides: dict[str, str],
    genre_rows: RankedRows,
    artist_genres: dict[str, str],
    readme_dir: Path,
) -> list[str]:
    listening_dir = readme_dir / "assets" / "listening"
    taste_path = listening_dir / "taste-drift.svg"
    weather_path = listening_dir / "genre-weather.svg"
    country_decade_path = listening_dir / "country-decade.svg"
    top_ranges_path = listening_dir / "top-ranges.svg"
    saved_played_path = listening_dir / "saved-vs-played.svg"

    top_cache = read_json(SPOTIFY_TOP_ITEMS_CACHE)
    recently_played_cache = read_json(SPOTIFY_RECENTLY_PLAYED_CACHE)

    months, groups, drift_series = taste_drift_data(tracks, artist_genres)
    write_taste_drift_svg(taste_path, months, groups, drift_series)
    write_genre_weather_svg(weather_path, genre_rows[:24])
    countries, decades, matrix = country_decade_data(tracks, artist_cache, country_overrides)
    write_country_decade_svg(country_decade_path, countries, decades, matrix)
    top_source, top_ranges = top_ranges_data(tracks, top_cache)
    write_top_ranges_svg(top_ranges_path, top_source, top_ranges)
    played_source, saved_rows, played_rows, rediscovered, ignored = saved_vs_played_data(
        tracks,
        artist_genres,
        recently_played_cache,
    )
    write_saved_vs_played_svg(
        saved_played_path,
        played_source,
        saved_rows,
        played_rows,
        rediscovered,
        ignored,
    )

    return [
        "## Listening Maps",
        "",
        md_image("Taste drift by month", taste_path, readme_dir),
        "",
        md_image("Genre weather map", weather_path, readme_dir),
        "",
        md_image("Countries by decade heatmap", country_decade_path, readme_dir),
        "",
        *spotify_cover_wall_lines(top_cache, recently_played_cache),
        md_image("Top items across time ranges", top_ranges_path, readme_dir),
        "",
        md_image("Saved library versus recently played", saved_played_path, readme_dir),
        "",
    ]


def build_dashboard(
    tracks: list[dict[str, str]],
    tracks_csv: Path,
    readme: Path,
) -> str:
    readme_dir = readme.parent
    atlas_dir = readme_dir / "assets" / "atlas"
    overview_path = readme_dir / "assets" / "overview.svg"
    aggregates_path = readme_dir / "assets" / "aggregates.svg"
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
        top_countries = top(countries, 20)
        top_assigned_genres = assigned_genres[:20]
        top_artists = top(artists, 20)
        write_overview_svg(
            overview_path,
            [
                ("Tracks", len(tracks)),
                ("Artists", len(artists)),
                ("Albums", len(albums)),
                ("Tag genres", len(genres)),
                ("Assigned genres", len(assigned_genres)),
                ("Countries", len(countries)),
                ("Playlists", len(playlists)),
                ("Release years", year_range),
                ("Duration", duration_label(duration_ms)),
            ],
        )
        write_aggregates_svg(
            aggregates_path,
            top_countries,
            top_assigned_genres,
            top_artists,
        )
        lines.extend(
            [
                md_image("Spotify library overview", overview_path, readme_dir),
                "",
                "> Each artist is assigned to exactly one dominant genre. Every genre card below shows top 15 artists, years and countries.",
                "",
            ]
        )
        lines.extend(
            listening_maps(
                tracks,
                artist_cache,
                country_overrides,
                assigned_genres,
                artist_genres,
                readme_dir,
            )
        )
        lines.extend(
            genre_atlas(
                tracks,
                artist_cache,
                country_overrides,
                assigned_genres,
                artist_genres,
                readme_dir,
                atlas_dir,
            )
        )

        lines.extend(
            [
                "## Latest 20 Liked Tracks",
                "",
                compact_table(
                    ["Added", "Artist", "Track", "Album", "Year", "Genre"],
                    recent_liked_rows(tracks, 20),
                ),
                "",
                "## Aggregates",
                "",
                md_image("Spotify aggregate top lists", aggregates_path, readme_dir),
                "",
                "<details>",
                "<summary>Workflow</summary>",
                "",
                "",
                "- `python scripts/export_spotify.py` updates `data/tracks.csv` from saved tracks and owned/collaborative playlists, plus optional Spotify top/recent snapshots.",
                "- `python scripts/enrich_genres_musicbrainz.py` fills blank genres from cached MusicBrainz artist tags.",
                "- `python scripts/backfill_countries_musicbrainz.py --fetch-missing-artists` backfills artist countries from MusicBrainz and Wikidata where available.",
                "- `python scripts/apply_genre_rules.py --overwrite` applies curated genres from `data/genre_rules.csv`.",
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
            "Create a Spotify app, run the local OAuth export once, store the full `data/tracks.csv` in a private data repository, then set public repository secrets described in `DATA.md`. GitHub Actions can refresh the public dashboard weekly without publishing the full CSV. Spotify user refresh tokens expire after six months; when the workflow reports `invalid_grant`, or after adding `user-top-read` / `user-read-recently-played`, reauthorize locally and update the `SPOTIFY_REFRESH_TOKEN` secret.",
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
    write_text_lf(readme, build_dashboard(tracks, tracks_csv, readme))
    print(f"Wrote {readme}")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import fnmatch
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TRACKS_CSV = ROOT / "data" / "tracks.csv"
RULES_CSV = ROOT / "data" / "genre_rules.csv"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Apply local genre rules to data/tracks.csv.")
    parser.add_argument("--tracks", type=Path, default=TRACKS_CSV)
    parser.add_argument("--rules", type=Path, default=RULES_CSV)
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Replace existing primary_genre and genres values instead of only filling blanks.",
    )
    return parser.parse_args()


def resolve_path(path: Path) -> Path:
    return path if path.is_absolute() else ROOT / path


def split_values(value: str) -> list[str]:
    return [part.strip() for part in value.split(";") if part.strip()]


def norm(value: str) -> str:
    return value.strip().casefold()


def wildcard_match(pattern: str, value: str) -> bool:
    pattern_norm = norm(pattern)
    value_norm = norm(value)
    if not pattern_norm or not value_norm:
        return False
    if any(mark in pattern_norm for mark in "*?[]"):
        return fnmatch.fnmatchcase(value_norm, pattern_norm)
    return pattern_norm == value_norm


def row_values(row: dict[str, str], match_type: str) -> list[str]:
    if match_type == "artist":
        return split_values(row.get("artist_names", ""))
    if match_type == "album":
        return [row.get("album_name", "")]
    if match_type == "track":
        return [row.get("track_name", "")]
    if match_type == "playlist":
        return split_values(row.get("playlist_names", ""))
    if match_type == "source":
        return split_values(row.get("sources", ""))
    return []


def read_csv(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open("r", encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)
        return list(reader.fieldnames or []), list(reader)


def read_rules(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    _, rules = read_csv(path)
    valid = [rule for rule in rules if rule.get("match_type") and rule.get("pattern")]
    return sorted(valid, key=lambda rule: int(rule.get("priority") or 0), reverse=True)


def apply_rules_to_row(
    row: dict[str, str],
    rules: list[dict[str, str]],
    overwrite: bool,
) -> bool:
    if not overwrite and row.get("primary_genre") and row.get("genres"):
        return False

    for rule in rules:
        match_type = norm(rule.get("match_type", ""))
        pattern = rule.get("pattern", "")
        values = row_values(row, match_type)
        if not any(wildcard_match(pattern, value) for value in values):
            continue

        primary = rule.get("primary_genre", "").strip()
        genres = rule.get("genres", "").strip()
        if not primary and genres:
            primary = split_values(genres)[0] if split_values(genres) else ""
        if not genres and primary:
            genres = primary

        changed = False
        if primary and (overwrite or not row.get("primary_genre")):
            row["primary_genre"] = primary
            changed = True
        if genres and (overwrite or not row.get("genres")):
            row["genres"] = genres
            changed = True
        return changed

    return False


def write_tracks(path: Path, fieldnames: list[str], rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fieldnames})


def main() -> None:
    args = parse_args()
    tracks_path = resolve_path(args.tracks)
    rules_path = resolve_path(args.rules)
    output_path = resolve_path(args.output) if args.output else tracks_path

    fieldnames, rows = read_csv(tracks_path)
    rules = read_rules(rules_path)
    changed = sum(1 for row in rows if apply_rules_to_row(row, rules, args.overwrite))
    write_tracks(output_path, fieldnames, rows)
    print(f"Applied genre rules to {changed} tracks using {rules_path}")


if __name__ == "__main__":
    main()

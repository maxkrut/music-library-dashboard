#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import fnmatch
from pathlib import Path

from file_utils import atomic_text_writer


ROOT = Path(__file__).resolve().parents[1]
TRACKS_CSV = ROOT / "data" / "tracks.csv"
RULES_CSV = ROOT / "data" / "genre_rules.csv"
VALID_MATCH_TYPES = {"artist", "album", "track", "playlist", "source"}
REQUIRED_RULE_FIELDS = {
    "match_type",
    "pattern",
    "primary_genre",
    "genres",
    "priority",
    "notes",
}


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


def rule_has_content(rule: dict[str, str]) -> bool:
    return any((value or "").strip() for value in rule.values())


def validate_rule_schema(fieldnames: list[str], path: Path) -> None:
    missing = sorted(REQUIRED_RULE_FIELDS.difference(fieldnames))
    if missing:
        raise ValueError(f"{path} is missing required column(s): {', '.join(missing)}")


def validate_rule(rule: dict[str, str], line_number: int) -> None:
    match_type = norm(rule.get("match_type", ""))
    pattern = (rule.get("pattern") or "").strip()
    if not rule_has_content(rule):
        return
    if not match_type or not pattern:
        raise ValueError(f"Invalid genre rule on line {line_number}: match_type and pattern are required")
    if match_type not in VALID_MATCH_TYPES:
        valid = ", ".join(sorted(VALID_MATCH_TYPES))
        raise ValueError(f"Invalid genre rule match_type {match_type!r} on line {line_number}; expected one of: {valid}")


def rule_priority(rule: dict[str, str]) -> int:
    value = (rule.get("priority") or "").strip()
    if not value:
        return 0
    try:
        return int(value)
    except ValueError as error:
        match_type = rule.get("match_type", "")
        pattern = rule.get("pattern", "")
        raise ValueError(
            f"Invalid genre rule priority {value!r} for {match_type}:{pattern}"
        ) from error


def read_rules(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    fieldnames, rules = read_csv(path)
    validate_rule_schema(fieldnames, path)
    for line_number, rule in enumerate(rules, start=2):
        validate_rule(rule, line_number)
    valid = [rule for rule in rules if rule.get("match_type") and rule.get("pattern")]
    return sorted(valid, key=rule_priority, reverse=True)


def complete_existing_genres(row: dict[str, str]) -> bool:
    primary = (row.get("primary_genre") or "").strip()
    genres = (row.get("genres") or "").strip()
    if primary and not genres:
        row["genres"] = primary
        return True
    if genres and not primary:
        values = split_values(genres)
        if values:
            row["primary_genre"] = values[0]
            return True
    return False


def apply_rules_to_row(
    row: dict[str, str],
    rules: list[dict[str, str]],
    overwrite: bool,
) -> bool:
    if not overwrite and complete_existing_genres(row):
        return True
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
        if not primary and not genres:
            continue

        changed = False
        if primary and (overwrite or not row.get("primary_genre")):
            if row.get("primary_genre") != primary:
                row["primary_genre"] = primary
                changed = True
        if genres and (overwrite or not row.get("genres")):
            if row.get("genres") != genres:
                row["genres"] = genres
                changed = True
        return changed

    return False


def write_tracks(path: Path, fieldnames: list[str], rows: list[dict[str, str]]) -> None:
    with atomic_text_writer(path, newline="") as file:
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

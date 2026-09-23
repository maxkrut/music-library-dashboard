"""Private snapshot history and public, aggregate-only dashboard annotations."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from file_utils import atomic_text_writer


def timestamp(value: object) -> datetime | None:
    try:
        if isinstance(value, (int, float)):
            return datetime.fromtimestamp(value, timezone.utc)
        if not value:
            return None
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed.astimezone(timezone.utc)
    except (ValueError, TypeError, OverflowError, OSError):
        return None


def freshness(value: object, now: datetime) -> str:
    date = timestamp(value)
    if date is None:
        return "Unavailable"
    age = (now - date).total_seconds() / 86400
    if age < -1:
        return "Invalid future timestamp"
    label = date.strftime("%Y-%m-%d %H:%M UTC")
    return f"{label} · {'stale' if age > 8 else 'current'}"


def snapshot(
    tracks: list[dict[str, str]],
    countries: dict[str, str],
    genre_counts: dict[str, int],
    now: datetime,
) -> dict:
    def values(field: str) -> list[str]:
        return sorted({part.strip().casefold() for row in tracks for part in row.get(field, "").split(";") if part.strip()})

    return {
        "observed_at": now.isoformat(),
        "track_ids": sorted({row["track_id"] for row in tracks if row.get("track_id")}),
        "liked_ids": sorted({row["track_id"] for row in tracks if row.get("track_id") and "liked" in {part.strip() for part in row.get("sources", "").casefold().split(";")}}),
        "artists": values("artist_names"),
        "albums": sorted({row.get("album_id") or f"{row.get('artist_names', '')}|{row.get('album_name', '')}" for row in tracks if row.get("album_id") or row.get("album_name")}),
        "countries": sorted(set(countries.values()) - {""}),
        "genre_counts": genre_counts,
    }


def history_snapshots(path: Path) -> list[dict]:
    if not path.exists():
        return []
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or payload.get("version") != 1:
        raise ValueError("Unsupported dashboard history format")
    rows = payload.get("snapshots", [])
    if not isinstance(rows, list) or any(not isinstance(row, dict) or timestamp(row.get("observed_at")) is None for row in rows):
        raise ValueError("Invalid dashboard history snapshots")
    return rows


def save_snapshot(path: Path, current: dict) -> None:
    history = history_snapshots(path)
    day = current["observed_at"][:10]
    # Rebuilding on the same day replaces only today's observation.
    history = [row for row in history if str(row.get("observed_at", ""))[:10] != day]
    history.append(current)
    history.sort(key=lambda row: row["observed_at"])
    with atomic_text_writer(path, newline="\n") as file:
        json.dump({"version": 1, "snapshots": history[-90:]}, file, ensure_ascii=False, indent=2)
        file.write("\n")


def weekly_lines(current: dict, history: list[dict]) -> list[str]:
    now = timestamp(current["observed_at"])
    eligible = [row for row in history if timestamp(row.get("observed_at")) <= now - timedelta(days=7)]
    lines = ["## This Week in the Library", ""]
    if not eligible:
        return lines + ["Collecting a baseline. Changes will appear after a second observation at least seven days later.", ""]
    previous = max(eligible, key=lambda row: timestamp(row["observed_at"]))
    lines += [f"Changes between observations on {previous['observed_at'][:10]} and {current['observed_at'][:10]}. These are library changes, not listening counts.", ""]
    changes = []
    for field, label in (("track_ids", "tracks"), ("liked_ids", "liked tracks"), ("artists", "artists"), ("albums", "albums"), ("countries", "countries")):
        count = len(set(current[field]) - set(previous.get(field, [])))
        changes.append(f"**{count}** new {label}")
    lines += [" · ".join(changes), ""]
    removed = len(set(previous.get("track_ids", [])) - set(current["track_ids"]))
    lines += [f"Removed from the library: **{removed}** tracks.", ""]
    before, after = previous.get("genre_counts", {}), current["genre_counts"]
    before_total, after_total = sum(before.values()), sum(after.values())
    if before_total and after_total:
        shifts = [(group, 100 * after.get(group, 0) / after_total - 100 * before.get(group, 0) / before_total) for group in before.keys() | after.keys()]
        shifts.sort(key=lambda item: (-abs(item[1]), item[0]))
        significant = [f"{group}: {delta:+.1f} pp" for group, delta in shifts[:3] if abs(delta) >= 0.05]
        if significant:
            lines += ["Genre share changes: " + "; ".join(significant) + ". Metadata corrections can also change these shares.", ""]
    return lines


def quality_lines(
    tracks: list[dict[str, str]],
    genre_known: int,
    country_known: int,
    export_cache: dict,
    top_cache: dict,
    recent_cache: dict,
    now: datetime,
) -> list[str]:
    total = len(tracks)
    def coverage(count: int) -> str:
        return f"{count:,} / {total:,} ({100 * count / total:.1f}%)" if total else "No library data"
    recent_items = recent_cache.get("items", [])
    times = sorted(date for item in recent_items if isinstance(item, dict) and (date := timestamp(item.get("played_at"))) is not None)
    window = f"{times[0].strftime('%Y-%m-%d %H:%M')} – {times[-1].strftime('%Y-%m-%d %H:%M')} UTC; {len(times)} plays" if times else "No listening history available"
    export_status = freshness(export_cache.get("fetched_at"), now)
    if export_cache.get("complete_sources") is False:
        export_status += " · partial export (explicit override)"
    return [
        "## Data Quality & Freshness", "",
        "| Source / coverage | Status |", "| --- | --- |",
        f"| Library export | {export_status} |",
        f"| Spotify top artists | {freshness(top_cache.get('fetched_at'), now)} |",
        f"| Recently played snapshot | {freshness(recent_cache.get('fetched_at'), now)} |",
        f"| Listening sample | {window} |",
        f"| Tracks with a usable genre | {coverage(genre_known)} |",
        f"| Tracks awaiting genre confirmation | {sum((row.get('genre_status') or '').strip().casefold() == 'unverified' for row in tracks):,} |",
        f"| Tracks with a known artist country | {coverage(country_known)} |",
        "", "Coverage measures completeness, not verification of every genre or country. Build time above is separate from source freshness.", "",
    ]

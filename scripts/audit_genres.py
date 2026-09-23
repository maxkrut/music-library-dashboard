"""Audit all artists locally; the detailed report must stay in the private cache."""
from __future__ import annotations

import argparse
import csv
import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

import apply_genre_rules as rules_module
import build_readme as dashboard
import enrich_genres_musicbrainz as enrichment
from file_utils import atomic_text_writer


def matching_rule(row: dict, rules: list[dict]) -> dict:
    for rule in rules:
        if not (rule.get("primary_genre") or rule.get("genres") or rules_module.rule_marks_unverified(rule)):
            continue
        if rules_module.rule_matches(row, rule):
            return rule
    return {}


def curated_primary_matches(row: dict, rule: dict) -> bool:
    if not rule or rules_module.rule_marks_unverified(rule):
        return False
    primary = rule.get("primary_genre", "").strip()
    if not primary:
        genres = rules_module.split_values(rule.get("genres", ""))
        primary = genres[0] if genres else ""
    return dashboard.effective_primary_genre(row) == dashboard.canonical_genre(primary)


def curated_secondary_matches(row: dict, rule: dict) -> bool:
    if not rule or rules_module.rule_marks_unverified(rule):
        return False
    expected = rules_module.split_values(rule.get("genres", ""))
    if not expected:
        return True  # A primary-only rule does not assert a secondary style.
    actual = rules_module.split_values(row.get("genres", ""))
    return set(dashboard.canonical_genres(actual)) == set(dashboard.canonical_genres(expected))


def rule_evidence_category(row: dict, rule: dict) -> str:
    if dashboard.norm(row.get("genre_status") or "") == "unverified" or rules_module.rule_marks_unverified(rule):
        return "unverified"
    if not rule:
        return "no_rule"
    if not curated_primary_matches(row, rule) or not curated_secondary_matches(row, rule):
        return "rule_not_applied"
    # A source link is traceability, not proof that every tag was verified.
    if "https://" in rule.get("notes", "") or "http://" in rule.get("notes", ""):
        return "source_linked_rule"
    return "rule_without_source"


def rule_uses_guest(row: dict, rule: dict) -> bool:
    match_type = rule.get("match_type", "")
    if match_type not in {"artist", "artist_id"}:
        return False
    values = rules_module.row_values(row, match_type)
    if not values:
        return False
    pattern = rule.get("pattern", "").strip()
    return pattern != values[0] if match_type == "artist_id" else not rules_module.wildcard_match(pattern, values[0])


def audit(tracks: list[dict], artist_cache: dict, rules: list[dict]) -> dict:
    genre_counts = Counter(
        genre for row in tracks for genre in dashboard.effective_genres(row)
    )
    artist_profiles = dashboard.read_artist_genre_profiles(dashboard.ARTIST_GENRE_PROFILES_CSV)
    identity_exclusions = enrichment.read_identity_exclusions(enrichment.IDENTITY_EXCLUSIONS_CSV)
    dashboard_genres = dashboard.artist_genre_assignments(
        tracks,
        dashboard.top(genre_counts, len(genre_counts)),
        artist_profiles,
    )
    artists: dict[str, list[dict]] = defaultdict(list)
    for row in tracks:
        for artist in dashboard.all_artists(row):
            artists[artist].append(row)
    records = []
    for artist, rows in sorted(artists.items(), key=lambda item: item[0].casefold()):
        primary_rows = [row for row in rows if dashboard.all_artists(row)[:1] == [artist]]
        data = artist_cache.get(dashboard.norm(artist), {})
        excluded_namesake_cache = bool(data.get("artist_id") and any(
            data["artist_id"] in identity_exclusions.get(dashboard.lead_artist_key(row), set())
            for row in primary_rows
        ))
        if excluded_namesake_cache:
            data = {}
        flags = set()
        if any(dashboard.norm(row.get("genre_status") or "") == "unverified" for row in primary_rows):
            flags.add("unverified_genre")
        if any(not dashboard.effective_primary_genre(row) for row in primary_rows):
            flags.add("missing_genre")
        if any(dashboard.super_genre(dashboard.effective_primary_genre(row)) == "Other" for row in primary_rows if dashboard.effective_primary_genre(row)):
            flags.add("unmapped_genre_family")
        if data.get("matched") and enrichment.identity_name(data.get("name", "")) != enrichment.identity_name(artist) and not data.get("identity_verified"):
            flags.add("musicbrainz_name_mismatch")
        if data.get("reason") == "ambiguous name":
            flags.add("ambiguous_musicbrainz_identity")
        genres = Counter(dashboard.effective_primary_genre(row) for row in rows)
        tagged = enrichment.ranked_genres_from_tags(data.get("tags", []), set(), 5)
        tagged_groups = {dashboard.super_genre(genre) for genre in tagged}
        for row in primary_rows:
            genre = dashboard.effective_primary_genre(row)
            rule = matching_rule(row, rules)
            if rule and rules_module.rule_marks_unverified(rule) and dashboard.norm(row.get("genre_status") or "") != "unverified":
                flags.add("genre_review_hold_not_applied")
            if rule and not rules_module.rule_marks_unverified(rule) and not curated_primary_matches(row, rule):
                flags.add("curated_primary_not_applied")
            if rule and not rules_module.rule_marks_unverified(rule) and not curated_secondary_matches(row, rule):
                flags.add("curated_secondary_not_applied")
            if genre and tagged_groups and dashboard.super_genre(genre) not in tagged_groups and not curated_primary_matches(row, rule):
                flags.add("genre_family_disagrees_with_cache")
        if len({row.get("artist_ids", "").split(";")[0].strip() for row in primary_rows}) > 1:
            flags.add("multiple_spotify_identities")
        if not primary_rows:
            flags.add("collaborator_only_recordings")
        evidence = []
        for row in rows:
            rule = matching_rule(row, rules)
            if rule:
                evidence.append(f"{rule['match_type']}:{rule['pattern']} | {rule.get('notes', '')}")
        identity_flags = {"musicbrainz_name_mismatch", "ambiguous_musicbrainz_identity", "multiple_spotify_identities"}
        unverified_tracks = []
        for row in primary_rows:
            genre = dashboard.effective_primary_genre(row)
            rule = matching_rule(row, rules)
            curated = curated_primary_matches(row, rule)
            missing_or_unmapped = not genre or dashboard.super_genre(genre) == "Other"
            conflicting_evidence = bool(flags & identity_flags) or (bool(tagged_groups) and dashboard.super_genre(genre) not in tagged_groups)
            if missing_or_unmapped or (rule and (not curated or not curated_secondary_matches(row, rule))) or (conflicting_evidence and not curated):
                unverified_tracks.append({"track_id": row.get("track_id", ""), "track": row.get("track_name", ""),
                                          "album": row.get("album_name", ""), "primary_genre": genre,
                                          "stored_primary_genre": row.get("primary_genre", ""),
                                          "genre_status": row.get("genre_status", "")})
        curated_lead_count = sum(curated_primary_matches(row, matching_rule(row, rules)) for row in primary_rows)
        evidence_counts = dict(Counter(rule_evidence_category(row, matching_rule(row, rules)) for row in primary_rows))
        lead_genre_votes = Counter(dashboard.dominant_row_genre(row) for row in primary_rows)
        lead_genre_votes.pop("", None)
        artist_key = dashboard.lead_artist_key(primary_rows[0]) if primary_rows else ""
        profile = artist_profiles.get(artist_key)
        top_vote = max(lead_genre_votes.values(), default=0)
        tied = sum(count == top_vote for count in lead_genre_votes.values()) > 1
        profile_applied = bool(profile and (profile[1] == "always" or (profile[1] == "tie" and tied)))
        profile_confirmed = bool(profile and profile[1] == "confirm" and dashboard_genres.get(artist_key) == profile[0])
        if profile and profile[1] == "confirm" and not profile_confirmed:
            flags.add("artist_profile_mismatch")
        records.append({
            "artist": artist, "track_count": len(rows), "lead_track_count": len(primary_rows),
            "genres": dict(genres), "families": sorted({dashboard.super_genre(genre) for genre in genres if genre}),
            "lead_genre_votes": dict(lead_genre_votes),
            "dashboard_genre": dashboard_genres.get(artist_key, ""),
            "dashboard_genre_basis": ("source_linked_artist_profile" if profile_applied else
                                      "source_linked_confirmation" if profile_confirmed else
                                      "library_vote" if artist_key in dashboard_genres else ""),
            "albums": sorted({row.get("album_name", "") for row in rows}),
            "musicbrainz_name": data.get("name", ""), "musicbrainz_description": data.get("disambiguation", ""),
            "musicbrainz_id": data.get("artist_id", ""), "musicbrainz_genres": tagged,
            "musicbrainz_namesake_cache_excluded": excluded_namesake_cache,
            "flags": sorted(flags), "rules": sorted(set(evidence)),
            "identity_review_required": bool(flags & identity_flags),
            "genre_review_required": bool(unverified_tracks),
            "genre_review_tracks": unverified_tracks,
            "curated_lead_track_count": curated_lead_count,
            "rule_evidence_counts": evidence_counts,
            "review_level": ("guest recordings only; solo genre not assessed" if not primary_rows
                             else "all lead recordings match source-linked rules; see evidence limitations" if evidence_counts.get("source_linked_rule") == len(primary_rows)
                             else "some lead recordings match source-linked rules; see evidence limitations" if evidence_counts.get("source_linked_rule")
                             else "local rule consistency only; sources not recorded" if curated_lead_count
                             else "automated metadata checks only"),
        })
    actionable = {"missing_genre", "unmapped_genre_family", "musicbrainz_name_mismatch", "ambiguous_musicbrainz_identity", "genre_family_disagrees_with_cache", "multiple_spotify_identities", "curated_primary_not_applied", "curated_secondary_not_applied", "unverified_genre", "genre_review_hold_not_applied", "artist_profile_mismatch"}
    scope_warnings = []
    for row in tracks:
        rule = matching_rule(row, rules)
        if rule_uses_guest(row, rule):
            scope_warnings.append({"track_id": row.get("track_id", ""), "artists": row.get("artist_names", ""),
                                   "track": row.get("track_name", ""), "album": row.get("album_name", ""),
                                   "rule": f"{rule['match_type']}:{rule['pattern']}",
                                   "reason": "winning artist rule matches a guest rather than the lead artist"})
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "track_count": len(tracks), "artist_count": len(records),
        "artists_with_review_flags": sum(bool(set(record["flags"]) & actionable) for record in records),
        "artists_requiring_genre_review": sum(record["genre_review_required"] for record in records),
        "tracks_requiring_genre_review": sum(len(record["genre_review_tracks"]) for record in records),
        "artists_requiring_identity_review": sum(record["identity_review_required"] for record in records),
        "artists_with_source_linked_profiles": sum(record["dashboard_genre_basis"] in {"source_linked_artist_profile", "source_linked_confirmation"} for record in records),
        "artists_with_excluded_namesake_cache": sum(record["musicbrainz_namesake_cache_excluded"] for record in records),
        "flag_counts": dict(Counter(flag for record in records for flag in record["flags"])),
        "rule_evidence_counts": dict(Counter(rule_evidence_category(row, matching_rule(row, rules)) for row in tracks)),
        "rule_scope_warnings": scope_warnings,
        "scope": "Every artist and track scanned. Dashboard genre is the lead artist's library majority, with source-linked tie breaks and career-wide exceptions. Source-linked confirmations do not override the vote and flag a mismatch if the vote changes. Known same-name MusicBrainz cache entries are excluded from artist evidence and future enrichment by Spotify ID. Flags and rule-scope warnings are review candidates, not proven errors. Source links provide traceability, not independent verification of every secondary tag. Guest recordings do not define an artist's solo genre.",
        "artists": records,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tracks", type=Path, default=dashboard.TRACKS_CSV)
    parser.add_argument("--rules", type=Path, default=rules_module.RULES_CSV)
    parser.add_argument("--artist-cache", type=Path, default=dashboard.MUSICBRAINZ_ARTIST_CACHE)
    parser.add_argument("--output", type=Path, default=dashboard.ROOT / ".cache" / "genre-audit.json")
    args = parser.parse_args()
    report = audit(dashboard.read_tracks(args.tracks), dashboard.read_json(args.artist_cache), rules_module.read_rules(args.rules))
    with atomic_text_writer(args.output, newline="\n") as file:
        json.dump(report, file, ensure_ascii=False, indent=2)
        file.write("\n")
    with atomic_text_writer(args.output.with_suffix(".csv"), encoding="utf-8-sig", newline="") as file:
        fields = ["artist", "track_count", "lead_track_count", "dashboard_genre", "dashboard_genre_basis", "lead_genre_votes", "genres", "families", "flags", "review_level", "curated_lead_track_count", "rule_evidence_counts", "genre_review_required", "genre_review_tracks", "identity_review_required", "musicbrainz_namesake_cache_excluded", "rules"]
        writer = csv.DictWriter(file, fieldnames=fields)
        writer.writeheader()
        for record in report["artists"]:
            writer.writerow({field: json.dumps(record[field], ensure_ascii=False) if isinstance(record[field], (list, dict)) else record[field] for field in fields})
    print(f"Audited {report['track_count']} tracks / {report['artist_count']} artists; {report['artists_with_review_flags']} artists have diagnostic flags, {report['artists_requiring_genre_review']} need recording-level genre review. Private report: {args.output}")


if __name__ == "__main__":
    main()

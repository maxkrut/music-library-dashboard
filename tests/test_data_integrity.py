from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import apply_genre_rules as rules
import audit_genres
import build_readme as dashboard
import dashboard_insights as insights
import enrich_genres_musicbrainz as enrichment
import export_spotify as exporter


def options(**values):
    return SimpleNamespace(**({"force": False, "output": exporter.DATA_PATH, "limit": 0,
                             "no_saved": False, "no_playlists": False, "playlist_id": [], "verbose": False} | values))


def test_forbidden_playlist_stops_export_instead_of_accepting_partial_data():
    class Client:
        def paginate(self, *_args):
            raise exporter.SpotifyApiError(403, "forbidden")
            yield
    with pytest.raises(exporter.SpotifyApiError, match="incomplete"):
        exporter.fetch_playlist_tracks_into(Client(), "id", "name", None, {"liked": {}}, options())


@pytest.mark.parametrize("values", [{"no_saved": True}, {"no_playlists": True}, {"playlist_id": ["one"]}, {"limit": 3}])
def test_partial_source_selection_cannot_replace_default_library(values):
    with pytest.raises(SystemExit):
        exporter.guard_default_output(options(**values), {"track": {}})


def test_library_drop_guard_and_explicit_override():
    with pytest.raises(SystemExit, match="shrank"):
        exporter.guard_default_output(options(), {"track": {}}, previous_count=100)
    exporter.guard_default_output(options(force=True), {"track": {}}, previous_count=100)


def test_playlist_addition_does_not_change_like_date_in_either_merge_order():
    track = {"id": "track", "type": "track", "name": "Example", "artists": [{"name": "Artist"}]}
    liked = exporter.normalize_track({"track": track, "added_at": "2020-01-01T00:00:00Z"}, "liked")
    playlist = exporter.normalize_track({"track": track, "added_at": "2026-09-22T00:00:00Z"}, "playlist")
    for first, second in [(liked, playlist), (playlist, liked)]:
        merged = exporter.merge_track(first, second)
        assert dashboard.liked_date(merged) == "2020-01-01T00:00:00Z"
        assert dashboard.added_date(merged) == "2026-09-22T00:00:00Z"


def test_unknown_legacy_like_date_is_not_presented_as_recent():
    row = {"sources": "liked; playlist", "latest_added_at": "2026-09-22"}
    assert dashboard.liked_date(row) == ""
    assert dashboard.recent_liked_items([row]) == []


def test_no_listening_history_never_counts_saved_tracks_as_plays():
    rows = [{"track_id": "one", "primary_genre": "rock"}]
    source, saved, played, rediscovered, _ = dashboard.saved_vs_played_data(rows, {}, {})
    assert source == "No listening history"
    assert saved == [("Rock / Psych / Prog", 1)]
    assert played == [] and rediscovered == 0
    assert dashboard.top_ranges_data(rows, {}) == ("No Spotify top data", {})


def test_repeated_plays_and_outside_library_are_included_in_denominator():
    rows = [{"track_id": "one", "primary_genre": "rock"}]
    cache = {"items": [{"track": {"id": id}} for id in ["one", "one", "outside"]]}
    _, _, played, found, missing = dashboard.saved_vs_played_data(rows, {}, cache)
    assert sum(value for _, value in played) == 3
    assert dict(played)["Outside library"] == 1
    assert found == 1 and missing == 0


def test_chart_uses_all_categories_in_proportions_and_no_invented_plays(tmp_path):
    path = tmp_path / "chart.svg"
    dashboard.write_saved_vs_played_svg(path, "Spotify recently played", [(f"Group {i}", 10) for i in range(10)], [("Group 0", 2)], 1, 99)
    svg = path.read_text(encoding="utf-8")
    assert "100 tracks" in svg and "2 plays" in svg and "Remaining groups" in svg
    assert ">30.0%</text>" in svg and ">100.0%</text>" in svg
    dashboard.write_saved_vs_played_svg(path, "No listening history", [("Metal", 10)], [], 0, 10)
    svg = path.read_text(encoding="utf-8")
    assert "ignored" not in svg and "played 0" not in svg and "No listening sample" in svg


def test_rank_badges_compare_same_range_and_need_baseline(tmp_path):
    path = tmp_path / "rank.svg"
    ranges = {"short_term": [("A", 20)], "medium_term": [("B", 20)], "long_term": [("C", 20)]}
    dashboard.write_top_ranges_svg(path, "Spotify top artists", ranges)
    assert ">new</text>" not in path.read_text(encoding="utf-8")
    previous = {"short_term": [("X", 20), ("A", 19)], "medium_term": [("B", 20)], "long_term": [("C", 20)]}
    dashboard.write_top_ranges_svg(path, "Spotify top artists", ranges, previous)
    svg = path.read_text(encoding="utf-8")
    assert svg.count(">up 1</text>") == 1
    assert svg.count(">same</text>") == 2


def test_atlas_uses_lead_artist_majority_without_losing_track_genres():
    rows = [
        {"artist_names": "Artist; Guest", "artist_ids": "lead;guest", "primary_genre": "ambient"},
        {"artist_names": "Artist", "artist_ids": "lead", "primary_genre": "black metal"},
        {"artist_names": "Artist", "artist_ids": "lead", "primary_genre": "black metal"},
    ]
    artist_summary = dashboard.artist_genre_assignments(rows, [("black metal", 2), ("ambient", 1)])
    assert artist_summary == {"lead": "black metal"}
    assert dashboard.effective_primary_genre(rows[0]) == "ambient"
    assert dashboard.row_assigned_genre(rows[0], artist_summary) == "black metal"
    assert dict(dashboard.assigned_genre_rows(rows, artist_summary)) == {"black metal": 3}
    index = dashboard.build_genre_stat_index(rows, {}, artist_summary)
    assert dict(index["black metal"][0]) == {"Artist": 3}


def test_artist_genre_uses_spotify_identity_and_withholds_unverified_recordings():
    rows = [
        {"artist_names": "Same Name", "artist_ids": "one", "primary_genre": "folk"},
        {"artist_names": "Same Name", "artist_ids": "two", "primary_genre": "metal"},
        {"artist_names": "Same Name", "artist_ids": "one", "primary_genre": "folk", "genre_status": "unverified"},
    ]
    summary = dashboard.artist_genre_assignments(rows, [("folk", 1), ("metal", 1)])
    assert summary == {"one": "folk", "two": "metal"}
    assert [dashboard.row_assigned_genre(row, summary) for row in rows] == ["folk", "metal", ""]


def test_same_group_with_two_spotify_profiles_keeps_its_majority_genre():
    rows = [
        {"artist_names": "Amenra", "artist_ids": "0N1jE1EIrhZjvQSfuLupUu", "primary_genre": "sludge metal"},
        {"artist_names": "Amenra", "artist_ids": "2VsSkHuQ6VE98qPkqybOaG", "primary_genre": "folk"},
        {"artist_names": "Amenra", "artist_ids": "0N1jE1EIrhZjvQSfuLupUu", "primary_genre": "sludge metal"},
    ]
    summary = dashboard.artist_genre_assignments(rows, [("sludge metal", 2), ("folk", 1)])
    assert summary == {"0N1jE1EIrhZjvQSfuLupUu": "sludge metal"}
    assert [dashboard.row_assigned_genre(row, summary) for row in rows] == ["sludge metal"] * 3


def test_source_linked_artist_tie_break_does_not_override_a_majority():
    rows = [
        {"artist_names": "Band", "artist_ids": "band-id", "primary_genre": "black metal"},
        {"artist_names": "Band", "artist_ids": "band-id", "primary_genre": "psychedelic folk rock"},
    ]
    summary = dashboard.artist_genre_assignments(
        rows, [("black metal", 1), ("psychedelic folk rock", 1)],
        {"band-id": ("psychedelic folk rock", "tie")},
    )
    assert summary == {"band-id": "psychedelic folk rock"}
    rows.append({"artist_names": "Band", "artist_ids": "band-id", "primary_genre": "black metal"})
    summary = dashboard.artist_genre_assignments(
        rows, [("black metal", 2), ("psychedelic folk rock", 1)],
        {"band-id": ("psychedelic folk rock", "tie")},
    )
    assert summary == {"band-id": "black metal"}


def test_sourced_artist_profile_can_override_a_one_album_library_sample():
    rows = [
        {"artist_names": "Ministry", "artist_ids": "ministry", "primary_genre": "synth-pop"},
        {"artist_names": "Ministry", "artist_ids": "ministry", "primary_genre": "synth-pop"},
    ]
    summary = dashboard.artist_genre_assignments(
        rows, [("synth-pop", 2)], {"ministry": ("industrial metal", "always")},
    )
    assert summary == {"ministry": "industrial metal"}
    assert [dashboard.effective_primary_genre(row) for row in rows] == ["synth-pop"] * 2
    assert [dashboard.row_assigned_genre(row, summary) for row in rows] == ["industrial metal"] * 2


def test_source_linked_artist_confirmation_never_overrides_library_vote():
    rows = [
        {"artist_names": "Band", "artist_ids": "band-id", "primary_genre": "post-metal"},
        {"artist_names": "Band", "artist_ids": "band-id", "primary_genre": "sludge metal"},
    ]
    profile = {"band-id": ("post-metal", "confirm")}
    assert dashboard.artist_genre_assignments(rows, [("sludge metal", 2), ("post-metal", 1)], profile) == {"band-id": "sludge metal"}
    rows.append({"artist_names": "Band", "artist_ids": "band-id", "primary_genre": "post-metal"})
    assert dashboard.artist_genre_assignments(rows, [("post-metal", 2), ("sludge metal", 1)], profile) == {"band-id": "post-metal"}


def test_artist_profiles_require_sources_and_known_application_modes(tmp_path):
    path = tmp_path / "artist-profiles.csv"
    path.write_text(
        "artist_id,artist_name,primary_genre,apply_when,source_url,notes\n"
        "band,Band,industrial metal,always,https://example.org/band,Artist biography\n",
        encoding="utf-8",
    )
    assert dashboard.read_artist_genre_profiles(path) == {"band": ("industrial metal", "always")}
    path.write_text(path.read_text(encoding="utf-8").replace(",always,", ",confirm,"), encoding="utf-8")
    assert dashboard.read_artist_genre_profiles(path) == {"band": ("industrial metal", "confirm")}
    path.write_text(path.read_text(encoding="utf-8").replace(",confirm,", ",sometimes,"), encoding="utf-8")
    with pytest.raises(ValueError, match="Incomplete artist genre profile"):
        dashboard.read_artist_genre_profiles(path)


def test_private_audit_reports_artist_genre_and_lead_only_votes():
    rows = [
        {"artist_names": "Band; Guest", "artist_ids": "band;guest", "primary_genre": "folk"},
        {"artist_names": "Band", "artist_ids": "band", "primary_genre": "metal"},
        {"artist_names": "Band", "artist_ids": "band", "primary_genre": "metal"},
    ]
    report = audit_genres.audit(rows, {}, [])
    band = next(item for item in report["artists"] if item["artist"] == "Band")
    guest = next(item for item in report["artists"] if item["artist"] == "Guest")
    assert band["dashboard_genre"] == "metal"
    assert band["dashboard_genre_basis"] == "library_vote"
    assert band["lead_genre_votes"] == {"folk": 1, "metal": 2}
    assert guest["dashboard_genre"] == "" and guest["lead_genre_votes"] == {}
    assert guest["dashboard_genre_basis"] == ""


def test_private_audit_marks_sourced_artist_profile_separately_from_track_votes(monkeypatch):
    monkeypatch.setattr(dashboard, "read_artist_genre_profiles", lambda _path: {"band": ("industrial metal", "always")})
    rows = [{"artist_names": "Band", "artist_ids": "band", "primary_genre": "synth-pop"}]
    report = audit_genres.audit(rows, {}, [])
    assert report["artists"][0]["dashboard_genre"] == "industrial metal"
    assert report["artists"][0]["dashboard_genre_basis"] == "source_linked_artist_profile"
    assert report["artists_with_source_linked_profiles"] == 1


def test_private_audit_checks_source_linked_confirmation_against_vote(monkeypatch):
    monkeypatch.setattr(dashboard, "read_artist_genre_profiles", lambda _path: {"band": ("post-metal", "confirm")})
    rows = [{"artist_names": "Band", "artist_ids": "band", "primary_genre": "post-metal"}]
    report = audit_genres.audit(rows, {}, [])
    assert report["artists"][0]["dashboard_genre_basis"] == "source_linked_confirmation"
    assert report["artists_with_source_linked_profiles"] == 1
    rows.append({"artist_names": "Band", "artist_ids": "band", "primary_genre": "sludge metal"})
    rows.append({"artist_names": "Band", "artist_ids": "band", "primary_genre": "sludge metal"})
    report = audit_genres.audit(rows, {}, [])
    assert report["artists"][0]["dashboard_genre"] == "sludge metal"
    assert report["artists"][0]["dashboard_genre_basis"] == "library_vote"
    assert "artist_profile_mismatch" in report["artists"][0]["flags"]
    assert report["artists_with_review_flags"] == 1


@pytest.mark.parametrize(("genre", "family"), [
    ("electropop", "Electronic / Ambient"), ("electro-pop", "Electronic / Ambient"),
    ("disco", "Electronic / Ambient"), ("pop punk", "Punk / Hardcore"),
    ("psychedelic funk", "Soul / Funk / R&B"), ("dub", "Reggae / Ska"),
    ("blackened doom metal", "Metal"),
    ("progressive breaks", "Electronic / Ambient"),
    ("sea shanty", "Folk / World"),
    ("power electronics", "Experimental / Noise"),
])
def test_genre_family_mapping(genre, family):
    assert dashboard.super_genre(genre) == family


def test_musicbrainz_does_not_pick_famous_namesake_or_tag_rich_collision(monkeypatch):
    candidates = [{"id": "wrong", "name": "John Legend", "score": 100, "tags": [{"name": "soul", "count": 10}]}]
    monkeypatch.setattr(enrichment, "search_artist_candidates", lambda *_: candidates)
    assert not enrichment.query_artist(None, "Legend", 90)["matched"]
    candidates[:] = [{"id": "one", "name": "Clouds", "score": 100}, {"id": "two", "name": "Clouds", "score": 100}]
    assert enrichment.query_artist(None, "Clouds", 90)["reason"] == "ambiguous name"


def test_cached_wrong_name_is_not_used_to_enrich_and_negative_votes_are_ignored():
    row = {"artist_names": "I, Captain"}
    cache = {"i, captain": {"matched": True, "name": "I Musici", "tags": [{"name": "classical", "count": 100}]}}
    assert enrichment.row_genres(row, cache, {"classical"}, 5) == []
    assert enrichment.ranked_genres_from_tags([{"name": "black metal", "count": -2}, {"name": "rock", "count": 1}], set(), 5) == ["rock"]


def test_known_same_name_musicbrainz_cache_is_excluded_by_spotify_id(tmp_path, monkeypatch):
    exclusions_csv = tmp_path / "exclusions.csv"
    exclusions_csv.write_text(
        "spotify_artist_id,musicbrainz_artist_id,artist_name,notes\n"
        "wanted,wrong,Century,Same-name artist\n", encoding="utf-8",
    )
    exclusions = enrichment.read_identity_exclusions(exclusions_csv)
    row = {"artist_names": "Century", "artist_ids": "wanted"}
    cache = {"century": {"matched": True, "name": "Century", "artist_id": "wrong", "tags": [{"name": "pop", "count": 5}]}}
    assert enrichment.row_genres(row, cache, {"pop"}, 5, exclusions) == []
    assert enrichment.row_genres({**row, "artist_ids": "another"}, cache, {"pop"}, 5, exclusions) == ["pop"]
    assert enrichment.row_genres(row, {"century": {**cache["century"], "artist_id": "right"}}, {"pop"}, 5, exclusions) == ["pop"]
    monkeypatch.setattr(enrichment, "IDENTITY_EXCLUSIONS_CSV", exclusions_csv)
    report = audit_genres.audit([{**row, "primary_genre": "heavy metal"}], cache, [])
    assert report["artists_with_excluded_namesake_cache"] == 1
    assert report["artists"][0]["musicbrainz_genres"] == []
    assert report["artists"][0]["musicbrainz_namesake_cache_excluded"]


def test_verified_namesakes_keep_their_correct_countries():
    countries = dashboard.read_country_overrides(dashboard.COUNTRY_OVERRIDES_CSV)
    assert countries["century"] == "Sweden"
    assert countries["kino"] == "Russia"
    assert countries["obscure"] == "Norway"


def test_release_fallback_requires_both_artist_and_album():
    class Client:
        def request(self, *_args):
            return {"release-groups": [{"id": "wrong", "score": 100, "title": "Liquid Midnight", "artist-credit": [{"artist": {"name": "Someone else"}}], "tags": [{"name": "soul", "count": 4}]}]}
    assert not enrichment.query_release_group(Client(), "Behrosth", "Liquid Midnight", 90)["matched"]


def test_album_id_rule_does_not_change_a_namesake_album():
    rule = {"match_type": "album_id", "pattern": "right", "primary_genre": "doom metal"}
    right, other = {"album_id": "right"}, {"album_id": "other"}
    assert rules.apply_rules_to_row(right, [rule], True)
    assert not rules.apply_rules_to_row(other, [rule], True)


def test_spotify_id_rules_preserve_case_and_lead_artist_scope():
    rule = {"match_type": "lead_artist_id", "pattern": "LeadID", "primary_genre": "ambient"}
    assert rules.rule_matches({"artist_ids": "LeadID;Guest"}, rule)
    assert not rules.rule_matches({"artist_ids": "leadid;Guest"}, rule)
    assert not rules.rule_matches({"artist_ids": "Guest;LeadID"}, rule)


def test_ambiguous_album_match_does_not_choose_the_most_tagged_namesake():
    class Client:
        def request(self, *_args):
            return {"release-groups": [{"id": id, "score": 100, "title": "Same Album", "artist-credit": [{"artist": {"name": "Same Artist"}}], "tags": [{"name": "rock", "count": votes}]} for id, votes in [("one", 1), ("two", 99)]]}
    result = enrichment.query_release_group(Client(), "Same Artist", "Same Album", 90)
    assert not result["matched"] and result["reason"] == "ambiguous release group"


def test_weekly_baseline_dates_changes_and_same_day_rebuild(tmp_path):
    now = datetime(2026, 9, 22, tzinfo=timezone.utc)
    before = insights.snapshot([{"track_id": "old", "artist_names": "A", "sources": "liked"}], {"A": "UK"}, {"Metal": 1}, now - timedelta(days=7))
    after = insights.snapshot([{"track_id": "new", "artist_names": "B", "sources": "liked"}], {"B": "US"}, {"Rock": 1}, now)
    assert "Collecting a baseline" in "\n".join(insights.weekly_lines(after, []))
    lines = "\n".join(insights.weekly_lines(after, [before]))
    assert "2026-09-15" in lines and "**1** new tracks" in lines and "**1** tracks" in lines
    path = tmp_path / "history.json"
    insights.save_snapshot(path, before)
    insights.save_snapshot(path, after)
    insights.save_snapshot(path, after)
    assert len(insights.history_snapshots(path)) == 2


def test_freshness_uses_fetch_time_not_build_time():
    now = datetime(2026, 9, 22, tzinfo=timezone.utc)
    assert "stale" in insights.freshness("2026-09-01T12:00:00Z", now)
    assert insights.freshness(None, now) == "Unavailable"
    lines = insights.quality_lines([], 0, 0, {"complete_sources": False}, {}, {}, now)
    assert "partial export" in "\n".join(lines)


def test_atlas_failure_restores_previous_output_and_keeps_unrelated_backups(tmp_path, monkeypatch):
    target, source = tmp_path / "atlas", tmp_path / "staging"
    target.mkdir()
    source.mkdir()
    (target / "old.svg").write_text("valid original")
    stranded_backup = tmp_path / ".atlas.backup-previous-failure"
    stranded_backup.mkdir()
    rename = Path.rename
    def fail_install(path, destination):
        if path == source:
            raise OSError("simulated install failure")
        return rename(path, destination)
    monkeypatch.setattr(Path, "rename", fail_install)
    with pytest.raises(OSError, match="simulated"):
        dashboard.replace_directory_after_success(target, source)
    assert (target / "old.svg").read_text() == "valid original"
    assert stranded_backup.exists()


def test_audit_covers_all_artists_and_preserves_commas():
    report = audit_genres.audit([{"artist_names": "I, Captain; Guest", "primary_genre": "", "artist_ids": "1;2"}], {}, [])
    assert report["artist_count"] == 2
    by_artist = {row["artist"]: row for row in report["artists"]}
    assert "missing_genre" in by_artist["I, Captain"]["flags"]
    assert by_artist["Guest"]["flags"] == ["collaborator_only_recordings"]


def test_audit_separates_rejected_cache_identity_from_curated_track_genre():
    row = {"track_id": "one", "artist_names": "Artist; Guest", "artist_ids": "a;g", "primary_genre": "folk"}
    cache = {"artist": {"matched": True, "name": "Unrelated Artist"}}
    rule = {"match_type": "track_id", "pattern": "one", "primary_genre": "folk"}
    report = audit_genres.audit([row], cache, [rule])
    artist, guest = report["artists"]
    assert artist["identity_review_required"] and not artist["genre_review_required"]
    assert not guest["genre_review_required"] and guest["curated_lead_track_count"] == 0
    assert "solo genre not assessed" in guest["review_level"]


def test_audit_rule_for_one_recording_does_not_clear_other_recordings():
    rows = [{"track_id": id, "artist_names": "Artist", "primary_genre": "rock"} for id in ["one", "two"]]
    cache = {"artist": {"matched": True, "name": "Unrelated Artist"}}
    rule = {"match_type": "track_id", "pattern": "one", "primary_genre": "rock"}
    report = audit_genres.audit(rows, cache, [rule])
    assert report["artists_requiring_genre_review"] == 1
    assert report["artists"][0]["genre_review_tracks"][0]["track_id"] == "two"
    assert report["tracks_requiring_genre_review"] == 1


def test_audit_unapplied_rule_does_not_certify_existing_primary_genre():
    row = {"track_id": "one", "artist_names": "Artist", "primary_genre": "pop"}
    rule = {"match_type": "track_id", "pattern": "one", "primary_genre": "black metal"}
    report = audit_genres.audit([row], {}, [rule])
    artist = report["artists"][0]
    assert "curated_primary_not_applied" in artist["flags"]
    assert artist["genre_review_required"] and artist["curated_lead_track_count"] == 0


def test_audit_detects_stale_secondary_tags_even_when_primary_matches():
    row = {"track_id": "one", "artist_names": "Artist", "primary_genre": "synthpop", "genres": "synthpop; black metal"}
    rule = {"match_type": "track_id", "pattern": "one", "primary_genre": "synth-pop", "genres": "synth-pop; electronic"}
    report = audit_genres.audit([row], {}, [rule])
    assert report["tracks_requiring_genre_review"] == 1
    assert "curated_secondary_not_applied" in report["artists"][0]["flags"]
    row["genres"] = "electronic; synthpop"
    assert audit_genres.audit([row], {}, [rule])["tracks_requiring_genre_review"] == 0


def test_audit_distinguishes_unsourced_defaults_and_guest_rule_leakage():
    rows = [
        {"track_id": "one", "artist_names": "Lead; Guest", "artist_ids": "l;g", "primary_genre": "rock"},
        {"track_id": "two", "artist_names": "Lead; Guest", "artist_ids": "l;g", "primary_genre": "folk"},
        {"track_id": "three", "artist_names": "Lead", "primary_genre": "pop"},
    ]
    scoped = {"match_type": "track_id", "pattern": "two", "primary_genre": "folk", "notes": "Release: https://example.com/release"}
    guest = {"match_type": "artist", "pattern": "Guest", "primary_genre": "rock", "notes": "manual fallback"}
    report = audit_genres.audit(rows, {}, [scoped, guest])
    assert report["rule_evidence_counts"] == {"rule_without_source": 1, "source_linked_rule": 1, "no_rule": 1}
    assert [item["track_id"] for item in report["rule_scope_warnings"]] == ["one"]
    assert "some lead recordings match source-linked rules" in report["artists"][1]["review_level"]
    guest.update(match_type="artist_id", pattern="g")
    assert audit_genres.rule_uses_guest(rows[0], guest)
    guest["pattern"] = "l"
    assert not audit_genres.rule_uses_guest(rows[0], guest)


@pytest.mark.parametrize("primary,expected", [("synthpop", "synth-pop"), ("stoner doom", "stoner doom metal"), ("alt-country", "alternative country")])
def test_audit_accepts_equivalent_genre_spellings(primary, expected):
    row = {"track_id": "one", "artist_names": "Artist", "primary_genre": expected}
    rule = {"match_type": "track_id", "pattern": "one", "primary_genre": primary}
    report = audit_genres.audit([row], {}, [rule])
    assert not report["artists"][0]["genre_review_required"]
    assert report["artists"][0]["curated_lead_track_count"] == 1


def test_unverified_rule_preserves_evidence_but_excludes_it_from_statistics(tmp_path):
    row = {"track_id": "one", "artist_names": "Artist", "primary_genre": "reggae", "genres": "reggae; rap", "spotify_genres": "pop"}
    hold = {"match_type": "track_id", "pattern": "one", "genre_status": "unverified"}
    fallback = {"match_type": "artist", "pattern": "Artist", "primary_genre": "pop"}
    before_report = audit_genres.audit([row], {}, [hold, fallback])
    assert "genre_review_hold_not_applied" in before_report["artists"][0]["flags"]
    assert before_report["artists_with_review_flags"] == 1
    assert rules.apply_rules_to_row(row, [hold, fallback], False)
    assert not rules.apply_rules_to_row(row, [hold, fallback], True)
    assert row["primary_genre"] == "reggae" and row["genres"] == "reggae; rap"
    assert dashboard.effective_genres(row) == [] and dashboard.effective_primary_genre(row) == ""
    assert dashboard.assigned_genre_rows([row], {"Artist": "pop"}) == []
    assert dashboard.row_super_genre(row, {"Artist": "pop"}) == "Unclassified"
    _, saved, _, _, _ = dashboard.saved_vs_played_data([row], {}, {})
    assert saved == [("Unclassified", 1)]
    report = audit_genres.audit([row], {}, [hold, fallback])
    assert report["tracks_requiring_genre_review"] == 1
    assert report["artists"][0]["curated_lead_track_count"] == 0
    assert "unverified_genre" in report["artists"][0]["flags"]
    assert "curated_primary_not_applied" not in report["artists"][0]["flags"]
    csv_path = tmp_path / "tracks.csv"
    rules.write_tracks(csv_path, ["track_id", "primary_genre", "genres"], [row])
    assert rules.read_csv(csv_path)[1][0]["genre_status"] == "unverified"
    quality = "\n".join(insights.quality_lines([row], 0, 0, {}, {}, {}, datetime(2026, 9, 22, tzinfo=timezone.utc)))
    assert "Tracks awaiting genre confirmation | 1 |" in quality


def test_reviewed_replacement_can_release_a_genre_hold():
    row = {"track_id": "one", "primary_genre": "reggae", "genres": "reggae", "genre_status": "unverified"}
    reviewed = {"match_type": "track_id", "pattern": "one", "primary_genre": "jazz fusion"}
    hold = {"match_type": "track_id", "pattern": "one", "genre_status": "unverified"}
    assert not rules.apply_rules_to_row(row, [reviewed, hold], False)
    assert row["genre_status"] == "unverified"
    assert rules.apply_rules_to_row(row, [reviewed, hold], True)
    assert row["genre_status"] == "" and dashboard.effective_primary_genre(row) == "jazz fusion"


def test_export_and_enrichment_preserve_unverified_status():
    old = {"one": {"genre_status": "unverified", "primary_genre": "", "genres": ""}}
    tracks = {"one": {"artist_names": "Artist", "spotify_year": "2026", "spotify_genres": "pop"}}
    exporter.apply_manual_fields(tracks, old)
    row = tracks["one"]
    assert row["genre_status"] == "unverified" and row["year"] == "2026"
    assert row["primary_genre"] == "" and row["genres"] == ""
    cache = {"artist": {"name": "Artist", "matched": True, "tags": [{"name": "pop", "count": 10}]}}
    assert enrichment.artist_names_from_rows([row], overwrite=True) == []
    assert enrichment.row_genres(row, cache, {"pop"}, 5) == []


@pytest.mark.parametrize("extra", [{"genre_status": "typo"}, {"genre_status": "unverified", "primary_genre": "pop"}])
def test_invalid_review_rules_fail_before_changing_tracks(extra):
    with pytest.raises(ValueError):
        rules.validate_rule({"match_type": "track_id", "pattern": "one", **extra}, 2)

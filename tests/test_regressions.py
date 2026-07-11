from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest


SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import apply_genre_rules  # noqa: E402
import backfill_countries_musicbrainz  # noqa: E402
import build_readme  # noqa: E402
import enrich_genres_musicbrainz  # noqa: E402
import export_spotify  # noqa: E402
from file_utils import atomic_text_writer  # noqa: E402


def test_atomic_text_writer_replaces_file_only_after_success(tmp_path: Path) -> None:
    target = tmp_path / "cache.json"
    target.write_text("old", encoding="utf-8")

    with pytest.raises(RuntimeError, match="stop"):
        with atomic_text_writer(target) as file:
            file.write("partial")
            raise RuntimeError("stop")

    assert target.read_text(encoding="utf-8") == "old"
    assert not list(tmp_path.glob(".cache.json.*.tmp"))

    with atomic_text_writer(target) as file:
        file.write("new")

    assert target.read_text(encoding="utf-8") == "new"


def test_musicbrainz_artist_split_preserves_commas() -> None:
    artists = enrich_genres_musicbrainz.artist_names_from_rows(
        [
            {
                "artist_names": "Earth, Wind & Fire; I, Captain",
                "primary_genre": "",
                "genres": "",
            }
        ],
        overwrite=False,
    )

    assert artists == ["Earth, Wind & Fire", "I, Captain"]


def test_genre_rule_reports_only_real_changes() -> None:
    rule = {
        "match_type": "artist",
        "pattern": "Example Artist",
        "primary_genre": "rock",
        "genres": "rock; indie rock",
    }
    unchanged = {
        "artist_names": "Example Artist",
        "primary_genre": "rock",
        "genres": "rock; indie rock",
    }
    changed = {
        "artist_names": "Example Artist",
        "primary_genre": "pop",
        "genres": "pop",
    }

    assert not apply_genre_rules.apply_rules_to_row(unchanged, [rule], overwrite=True)
    assert apply_genre_rules.apply_rules_to_row(changed, [rule], overwrite=True)
    assert changed["primary_genre"] == "rock"
    assert changed["genres"] == "rock; indie rock"


def test_top_song_covers_are_unique_per_album() -> None:
    cache = {
        "tracks": {
            "long_term": [
                {
                    "id": "track-1",
                    "album_id": "album-1",
                    "album_name": "First Album",
                    "artist_names": "Artist",
                    "name": "Track One",
                    "image_url": "https://example.com/first.jpg",
                },
                {
                    "id": "track-2",
                    "album_id": "album-1",
                    "album_name": "First Album",
                    "artist_names": "Artist",
                    "name": "Track Two",
                    "image_url": "https://example.com/first.jpg",
                },
                {
                    "id": "track-3",
                    "album_id": "album-2",
                    "album_name": "Second Album",
                    "artist_names": "Artist",
                    "name": "Track Three",
                    "image_url": "https://example.com/second.jpg",
                },
            ]
        }
    }

    tracks = build_readme.cached_spotify_top_tracks(cache)
    covers = build_readme.unique_album_cover_tracks(tracks)

    assert [track["name"] for track in covers] == ["Track One", "Track Three"]


def test_top_songs_layout_is_single_column(tmp_path: Path) -> None:
    tracks = [
        {
            "album_id": "album-1",
            "album_name": "Album",
            "artist": "Artist",
            "name": "Track",
            "image_url": "https://example.com/cover.jpg",
            "url": "https://example.com/track",
        }
    ]

    rendered = "\n".join(
        build_readme.spotify_all_time_top_songs_lines(
            tracks,
            tmp_path / "ranking.svg",
            tmp_path,
        )
    )

    assert rendered.startswith("## All-Time Top Songs")
    assert "<table>" not in rendered
    assert rendered.count('<p align="center">') == 2
    assert 'width="720"' in rendered


def test_genre_atlas_groups_are_collapsed(tmp_path: Path) -> None:
    lines = build_readme.genre_atlas(
        [
            {
                "artist_names": "Artist",
                "primary_genre": "rock",
                "genres": "rock",
                "year": "2020",
            }
        ],
        {"Artist": "United States"},
        [("rock", 1)],
        {"Artist": "rock"},
        tmp_path,
        tmp_path / "assets" / "atlas",
    )
    rendered = "\n".join(lines)

    assert rendered.startswith("## Genre Atlas")
    assert "<details>" in rendered
    assert "<summary><strong>Rock / Psych / Prog</strong>" in rendered
    assert "## Rock / Psych / Prog" not in rendered


def test_artist_country_index_is_reused_without_losing_track_order() -> None:
    artist_cache = {
        "artist one": {"matched": True, "country": "US"},
        "artist two": {"matched": True, "country": "GB"},
    }
    overrides = {"artist two": "Canada"}
    index = build_readme.build_artist_country_index(
        ["Artist One", "Artist Two"],
        artist_cache,
        overrides,
    )

    countries = build_readme.track_countries(
        {"artist_names": "Artist One; Artist Two; Artist One"},
        index,
    )

    assert index == {"Artist One": "United States", "Artist Two": "Canada"}
    assert countries == ["United States", "Canada"]


def test_wikidata_country_takes_priority_over_city_area() -> None:
    artist = {
        "matched": True,
        "country": "",
        "area": {"name": "Leeds"},
        "wikidata_origin": "United Kingdom",
    }

    assert build_readme.country_from_artist_data(artist) == "United Kingdom"
    assert backfill_countries_musicbrainz.raw_country_available(artist)
    assert not backfill_countries_musicbrainz.raw_country_available(
        {**artist, "wikidata_origin": ""}
    )


def test_cache_checkpoints_do_not_duplicate_interval_writes() -> None:
    assert not enrich_genres_musicbrainz.cache_checkpoint_due(24)
    assert enrich_genres_musicbrainz.cache_checkpoint_due(25)
    assert not enrich_genres_musicbrainz.final_cache_checkpoint_due(25)
    assert enrich_genres_musicbrainz.final_cache_checkpoint_due(26)


def test_callback_url_requires_matching_saved_oauth_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    state_cache = tmp_path / "oauth-state.json"
    monkeypatch.setattr(export_spotify, "OAUTH_STATE_CACHE", state_cache)
    export_spotify.save_oauth_state("expected-state")
    monkeypatch.setattr(
        export_spotify,
        "post_form",
        lambda *_args, **_kwargs: {"access_token": "token", "expires_in": 3600},
    )

    with pytest.raises(SystemExit, match="state mismatch"):
        export_spotify.request_user_token(
            "client",
            "secret",
            export_spotify.DEFAULT_REDIRECT_URI,
            export_spotify.DEFAULT_SCOPE,
            manual_oauth=False,
            callback_url="http://127.0.0.1:8888/callback?code=code&state=wrong",
        )

    token = export_spotify.request_user_token(
        "client",
        "secret",
        export_spotify.DEFAULT_REDIRECT_URI,
        export_spotify.DEFAULT_SCOPE,
        manual_oauth=False,
        callback_url=(
            "http://127.0.0.1:8888/callback?code=code&state=expected-state"
        ),
    )

    assert token["access_token"] == "token"
    assert not state_cache.exists()


def test_expired_oauth_state_is_discarded(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    state_cache = tmp_path / "oauth-state.json"
    state_cache.write_text(
        json.dumps({"state": "expired", "created_at": 1}),
        encoding="utf-8",
    )
    monkeypatch.setattr(export_spotify, "OAUTH_STATE_CACHE", state_cache)

    assert export_spotify.load_oauth_state() == ""
    assert not state_cache.exists()

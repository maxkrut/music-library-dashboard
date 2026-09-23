# Data Setup

This public repository publishes the generated dashboard, code, genre rules, artist genre profiles, identity exclusions, and country overrides.
The full Spotify export is kept out of the public repository.

## Repository Layout

- Public repository: README, generated atlas SVG assets, scripts, `data/genre_rules.csv`, `data/artist_genre_profiles.csv`, `data/musicbrainz_identity_exclusions.csv`, `data/country_overrides.csv`.
- Private data repository: `data/tracks.csv` and optional MusicBrainz/Spotify caches under `.cache/`.

The public workflow checks out the private data repository into a temporary `.private-data/` folder, copies `data/tracks.csv` into the workspace, rebuilds public artifacts, commits updated private data back to the private repository, then removes private files before committing public changes.

## Public Repository Secrets

Set these secrets in the public repository:

- `PRIVATE_DATA_REPO`: private repository in `owner/name` form.
- `PRIVATE_DATA_TOKEN`: fine-grained GitHub token with read/write contents access to the private data repository.
- `SPOTIFY_CLIENT_ID`: Spotify app client ID.
- `SPOTIFY_CLIENT_SECRET`: Spotify app client secret.
- `SPOTIFY_REFRESH_TOKEN`: Spotify refresh token for weekly exports.
- `SPOTIFY_REDIRECT_URI`: optional; defaults to `http://127.0.0.1:8888/callback`.

## Spotify Refresh Token Rotation

Spotify user refresh tokens expire after six months. When the weekly workflow logs an `invalid_grant` refresh error, or when adding the newer `user-top-read` / `user-read-recently-played` scopes, reauthorize locally:

```bash
python scripts/export_spotify.py --verbose
```

Then copy the new `refresh_token` value from `.cache/spotify-token.json` into the public repository `SPOTIFY_REFRESH_TOKEN` secret. Do not keep retrying the old token.

## Private Data Repository

The private repository should contain:

```text
data/tracks.csv
.cache/musicbrainz-artists.json
.cache/musicbrainz-genres.json
.cache/musicbrainz-release-groups.json
.cache/spotify-top-items.json
.cache/spotify-recently-played.json
.cache/spotify-export.json
.cache/dashboard-history.json
.cache/genre-audit.json
```

Only `data/tracks.csv` is required. The MusicBrainz caches make weekly runs faster and more reproducible. The Spotify top/recent caches feed the optional Top Items and Saved vs Played dashboard modules.

`spotify-export.json` records the successful export time and source completeness. `dashboard-history.json` holds up to 90 dated library snapshots for weekly comparisons; both stay private. `genre-audit.json` records every artist's checks and unresolved review flags. Local audits also write a CSV next to it.

The genre audit separates `identity_review_required` (for example, a rejected namesake in the old MusicBrainz cache) from `genre_review_required` and `genre_review_tracks` (recordings still needing a genre decision). It checks both the primary and the secondary genres assigned by a rule, accepting equivalent spellings and reordered secondary tags. It does not erase the cache-identity warning or verify an artist's guest-only credits. Confirmation rules may preserve a broad primary classification; their notes state when secondary tags or finer subgenres were not independently checked.

The private per-artist audit also records `dashboard_genre`, `dashboard_genre_basis` and `lead_genre_votes`, so the displayed artist category can be reviewed separately from each recording's own genre. The basis distinguishes a source-linked override or tie break, a source-linked confirmation of the current vote, and an unconfirmed library vote. If a confirmed vote later differs from its profile, `artist_profile_mismatch` flags it for review without freezing the category. Guest-only artists have no lead genre assignment.

`rule_evidence_counts` separates matching rules with source links, matching rules without sources, unapplied rules, unverified recordings and tracks without rules. Source links provide traceability rather than a certification of every tag. `rule_scope_warnings` lists recordings whose winning artist rule matches only a guest; these need a release-level check and are not automatically considered genre errors. The rule matcher still supports guest matches intentionally; use `lead_artist_id` for lead-only defaults and higher-priority `album_id` / `track_id` exceptions for stylistic changes.

`data/musicbrainz_identity_exclusions.csv` blocks specific Spotify/MusicBrainz ID pairs when a cached same-name artist is unrelated. Enrichment ignores that cache entry for the named Spotify artist, and the audit excludes its tags from genre comparisons. Country overrides for such artists must also be corrected separately.

`genre_status=unverified` keeps a recording's original genre values for review but prevents the dashboard from using them, including Spotify fallback tags. These tracks remain in library totals and listening denominators as `Unclassified`, are excluded from the genre atlas, and appear in the quality panel's pending count. The status survives Spotify export; MusicBrainz enrichment skips these recordings even with `--overwrite`. A blank status means the usual classification rules apply, not that the recording was independently verified.

## Export Integrity and Dates

An inaccessible playlist aborts the export before replacing the library CSV. Partial source selection (`--no-saved`, `--no-playlists`, `--playlist-id`, or a debug limit), an empty result, and a drop of more than 20% are rejected for the default output. Use a separate `--output` for experiments. `--force` explicitly permits an intentional partial or reduced default export; it does not suppress API failures.

`liked_at` is the time a track was saved to Liked Songs. `first_added_at` and `latest_added_at` cover all collected sources, including playlists. Legacy rows that combine likes and playlists cannot recover the actual like date from those fields and are excluded from Latest Likes until the next successful Spotify export.

## Dashboard Semantics

- Genre charts and the atlas assign each track to its lead artist's dominant primary genre (the most frequent among that artist's recordings in this library). Source-linked profiles in `data/artist_genre_profiles.csv` resolve reviewed ties or career-wide exceptions when this library contains only an atypical era. Otherwise library-wide frequency and then alphabetical order decide ties. A guest credit does not move the track to the guest's category. Release-specific labels remain on the track for the detailed lists and audit; explicitly unverified tracks stay Unclassified. Spotify artist IDs distinguish namesakes, with a curated alias for the two Amenra profiles. Collaborator names are separated by semicolons; commas remain part of a name.
- Artist profile rows require an exact Spotify `artist_id`, a primary genre, and an evidence URL. `apply_when=tie` applies only when two track genres share the highest count; `apply_when=always` documents a career-wide style that this library's recordings do not represent. `apply_when=confirm` records an externally supported genre already chosen by the library vote and never overrides that vote. Profiles do not change stored track genres.
- Saved vs Played compares percentage shares with separate denominators: library tracks and listening events. Repeated plays count repeatedly; out-of-library plays remain in the denominator. Smaller categories are combined without losing their counts. Missing listening data is displayed as unavailable.
- Top rank movement compares the same Spotify time range with the preceding fetched snapshot. A first snapshot has no movement badges.
- Weekly changes compare with the newest observation at least seven days earlier and show both dates. The first build collects a baseline. Corrections to metadata can change genre shares without new listening.
- Freshness uses source fetch timestamps, not file modification time or dashboard build time. A source older than eight days is marked stale; historical exports without metadata show unavailable freshness. Coverage is completeness, not a claim that every label has been independently verified.

## Public Example

`data/tracks.example.csv` documents the expected CSV shape without publishing the real Spotify export.

## Genre Rules

`data/genre_rules.csv` is applied by `scripts/apply_genre_rules.py` after Spotify export and MusicBrainz enrichment.

| Column | Meaning |
| --- | --- |
| `match_type` | `artist`, `album`, `track`, `playlist`, `source`, `artist_id`, `lead_artist_id`, `album_id`, or `track_id`. |
| `pattern` | Names match case-insensitively and support `*`, `?`, and `[]` wildcards. Spotify IDs require an exact, case-sensitive match. |
| `primary_genre` | Primary genre to fill or replace. |
| `genres` | Semicolon-separated genre list. If blank, `primary_genre` is used. |
| `priority` | Higher integer priority runs first; blank defaults to `0`. |
| `notes` | Free-form note for maintainers. |
| `genre_status` | Optional. Set to `unverified` to hold a recording for review; leave both genre columns empty in that rule. Blank preserves normal genre assignment behavior. |

Without `--overwrite`, rules only fill missing `primary_genre` or `genres` values. With `--overwrite`, matching rules replace existing values.

An explicit `unverified` rule marks the status in either mode and preserves raw genre values. Rule priority still applies. To resolve a hold, replace its ID rule with a source-backed genre assignment and blank `genre_status`, then apply with `--overwrite`; this clears the status. Removing the rule alone does not clear the status already preserved in the private export.

Prefer Spotify IDs for namesakes. `artist_id` matches any credited artist, while `lead_artist_id` matches only the first credit. Use `track_id` for a particular recording or collaboration; album IDs can cover several artists on compilations. The September 2026 review uses priorities 300 for recording exceptions and 200 for lead-artist corrections, with evidence URLs in `notes`.

MusicBrainz enrichment requires an exact normalized artist name and a single qualifying candidate. Album fallback also requires the artist credit to match. Fuzzy legacy cache entries and negative tag votes are not used for new genre enrichment. These checks reduce mistaken identities; exact names can still be ambiguous, so curated ID rules take precedence.

## Local Checks

```bash
python -m pip install -r requirements-dev.txt
python -m pytest tests -q
python scripts/apply_genre_rules.py --overwrite
python scripts/audit_genres.py
python scripts/build_readme.py
python scripts/validate_dashboard.py README.md
```

The public CI also builds `data/tracks.example.csv` with an empty cache directory, validates local SVG references, and runs regression tests without private credentials. The weekly update runs the tests before exporting, retains private history, and serializes runs to avoid concurrent updates.

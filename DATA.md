# Data Setup

This public repository publishes the generated dashboard, code, genre rules, and country overrides.
The full Spotify export is kept out of the public repository.

## Repository Layout

- Public repository: README, generated atlas SVG assets, scripts, `data/genre_rules.csv`, `data/country_overrides.csv`.
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
```

Only `data/tracks.csv` is required. The MusicBrainz caches make weekly runs faster and more reproducible. The Spotify top/recent caches feed the optional Top Items and Saved vs Played dashboard modules.

## Public Example

`data/tracks.example.csv` documents the expected CSV shape without publishing the real Spotify export.

## Genre Rules

`data/genre_rules.csv` is applied by `scripts/apply_genre_rules.py` after Spotify export and MusicBrainz enrichment.

| Column | Meaning |
| --- | --- |
| `match_type` | One of `artist`, `album`, `track`, `playlist`, or `source`. |
| `pattern` | Case-insensitive exact match by default; supports `*`, `?`, and `[]` wildcards. |
| `primary_genre` | Primary genre to fill or replace. |
| `genres` | Semicolon-separated genre list. If blank, `primary_genre` is used. |
| `priority` | Higher integer priority runs first; blank defaults to `0`. |
| `notes` | Free-form note for maintainers. |

Without `--overwrite`, rules only fill missing `primary_genre` or `genres` values. With `--overwrite`, matching rules replace existing values.

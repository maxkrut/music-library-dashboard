# Create your own Spotify README dashboard

This guide turns the template into a dashboard for your own Spotify library. The public repository holds the code and generated charts; a separate private repository holds the full export. GitHub Actions updates both every Monday at 05:17 UTC.

## Before you start

- A GitHub account, Git and Python 3.12 or newer. The scripts use Python's standard library; `requirements-dev.txt` is only needed to run the tests.
- Your own Spotify developer app. Spotify currently requires the app owner to have **Premium** for [Development Mode](https://developer.spotify.com/documentation/web-api/concepts/quota-modes). Each person using this template supplies their own app and credentials.
- Two repositories: one public dashboard and one private data repository.

The dashboard covers saved tracks, owned/collaborative playlists and available top/recent listening snapshots. It does not reconstruct your complete listening history or lifetime play counts.

## 1. Create your dashboard repository

Click [Use this template](https://github.com/maxkrut/spotify-readme-dashboard/generate), choose **Create a new repository**, and make your dashboard repository public. Clone your new repository and open a terminal in its root directory.

The copied README initially shows the template author's music. Your first successful build replaces those charts with your own library.

To preview the renderer without Spotify credentials, run:

```bash
python scripts/build_readme.py --input data/tracks.example.csv --output .codex-tmp/preview/README.md --cache-dir .codex-tmp/preview-cache
python scripts/validate_dashboard.py .codex-tmp/preview/README.md
```

Open `.codex-tmp/preview/README.md` in a Markdown viewer. The preview stays in an ignored local directory.

## 2. Connect your Spotify account

Open the [Spotify Developer Dashboard](https://developer.spotify.com/dashboard) and create an app with Web API access. In its settings, register this exact redirect URI:

```text
http://127.0.0.1:8888/callback
```

Copy `.env.example` to a new file named `.env` in the project root. Fill in `SPOTIFY_CLIENT_ID` and `SPOTIFY_CLIENT_SECRET` from your app's settings. Keep the supplied redirect URI and scope list. Set `MUSICBRAINZ_USER_AGENT` to a descriptive application name with your own contact address.

Run:

```bash
python scripts/export_spotify.py --verbose
```

Sign in and approve the requested read permissions in your browser. If the browser cannot open automatically, follow the terminal's authorization instructions. The exporter writes `data/tracks.csv`, listening snapshots and `.cache/spotify-token.json` locally.

Open `.cache/spotify-token.json` locally and keep its `refresh_token` value ready for step 4. Both `.env` and `.cache/` are ignored by Git; never upload the token file to either repository.

## 3. Build locally and prepare the private data repository

Run these commands from the dashboard repository:

```bash
python scripts/backfill_countries_musicbrainz.py --fetch-missing-artists
python scripts/enrich_genres_musicbrainz.py --offline
python scripts/apply_genre_rules.py --overwrite
python scripts/build_readme.py
python scripts/validate_dashboard.py README.md
```

The first country lookup can take a while for a large library. MusicBrainz and Spotify do not identify every genre or artist; missing entries remain visible in the data quality section. Review the generated README before publishing it: album covers, artist and track names, rankings and summaries will be public.

Create a **private** GitHub repository, for example `my-music-data`. Upload the exported file as `data/tracks.csv` and commit it there. Use the full export, not `data/tracks.example.csv`.

To reuse the local metadata lookups, optionally copy only these files into the private repository's `.cache/` directory when present:

```text
musicbrainz-artists.json
musicbrainz-genres.json
musicbrainz-release-groups.json
spotify-top-items.json
spotify-recently-played.json
spotify-export.json
dashboard-history.json
```

Only `data/tracks.csv` is required. Do not copy the entire local `.cache/` directory: it also contains Spotify authorization files. Keep `.env` and `data/tracks.csv` out of the public dashboard repository.

## 4. Add GitHub Actions secrets

Create a [fine-grained personal access token](https://github.com/settings/personal-access-tokens/new) with access to **only your private data repository** and repository permission **Contents: Read and write**. The workflow needs to read the archive and save refreshed data back to it.

In your **public dashboard repository**, open **Settings → Secrets and variables → Actions → New repository secret**. Add:

| Secret | Value |
| --- | --- |
| `PRIVATE_DATA_REPO` | Your private repository in `owner/name` form, without a URL. |
| `PRIVATE_DATA_TOKEN` | The fine-grained token created above. |
| `SPOTIFY_CLIENT_ID` | Your Spotify app's client ID. |
| `SPOTIFY_CLIENT_SECRET` | Your Spotify app's client secret. |
| `SPOTIFY_REFRESH_TOKEN` | The `refresh_token` from your local `.cache/spotify-token.json`. |
| `SPOTIFY_REDIRECT_URI` | Optional; defaults to `http://127.0.0.1:8888/callback`. |

Template copies need their own secrets. Keep credential values in Actions secrets, not in workflow YAML or committed files. If your organization requires approval for tokens or restricts GitHub Actions, its administrator must allow the private checkout and workflow commits.

## 5. Publish and enable weekly updates

Open **Actions → Update public README → Run workflow** and choose the default branch. Enable GitHub Actions if GitHub prompts you to do so.

The workflow exports Spotify data, applies metadata rules, rebuilds the README, commits the private archive and then commits the public charts. When it succeeds, refresh your repository's main page and check that the library is yours. Run `git pull --ff-only` locally to retrieve the generated commit before making further changes.

Weekly updates use the schedule already included in `.github/workflows/update-readme.yml`. You can also run the workflow manually whenever you want. Weekly comparisons appear after two observations at least seven days apart.

## Make it yours

- The README is generated. Change its title, introduction or sections in `scripts/build_readme.py` so future updates preserve your edits.
- Review the supplied genre rules, artist profiles and country overrides under `data/`. They contain curated corrections from the example library and apply only where their matching rules identify an entry. You can edit or remove individual rules for your collection; see [DATA.md](DATA.md#genre-rules).
- Update your repository's About text and topics. The **Use this template** link points to the original project; keep it as attribution or change it if you publish your own template.
- The code and generated dashboard assets use the [MIT License](LICENSE). Linked artwork and source metadata retain their providers' terms.

## If the first update fails

| Symptom | What to check |
| --- | --- |
| `Missing PRIVATE_DATA_REPO` or `Missing PRIVATE_DATA_TOKEN` | Add the secrets to the public dashboard repository, then rerun the workflow. A run started before setup will fail this check. |
| Private checkout fails or cannot push | Confirm `owner/name`, token expiration and Contents read/write access to that private repository. |
| `Private repo must contain data/tracks.csv` | Commit the real CSV at that exact path on the private repository's default branch. |
| Spotify `invalid_grant` | Run the local export again to reauthorize, then replace the `SPOTIFY_REFRESH_TOKEN` secret. |
| Spotify `403` | Check the app owner's Premium status and app user access in Spotify's dashboard; see [Development Mode access](https://developer.spotify.com/documentation/web-api/concepts/quota-modes). |
| Redirect URI error | The URI in Spotify app settings and `.env` must match exactly, including the port and `/callback`. |
| No movement badges or weekly changes | Let the scheduled workflow collect a second snapshot; no earlier history is invented. |

For file formats, privacy boundaries and calculation details, see [DATA.md](DATA.md).

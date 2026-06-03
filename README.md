![Maks Krutikov Spotify Library](assets/banner.svg)

**Maks Krutikov Spotify Library** / personal metadata dashboard. No audio files, only Spotify track data and local CSV edits.

<img src="assets/genres.svg" width="49%"> <img src="assets/timeline.svg" width="49%">

## Overview

| Tracks | Artists | Albums | Genres | Countries | Playlists | Release years | Total duration |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1972 | 1367 | 1676 | 563 | 52 | 5 | 1958-2026 | 183h 53m |

## Genre Mix

| Genre | Tracks |
| --- | --- |
| black metal | 348 |
| doom metal | 240 |
| progressive metal | 232 |
| heavy metal | 209 |
| progressive rock | 208 |
| hard rock | 196 |
| psychedelic rock | 161 |
| death metal | 161 |
| electronic | 149 |
| alternative rock | 136 |
| post-metal | 103 |
| stoner rock | 102 |
| ambient | 96 |
| post-rock | 95 |
| thrash metal | 90 |
| blues rock | 89 |
| atmospheric black metal | 87 |
| classic rock | 79 |
| stoner metal | 78 |
| viking metal | 75 |
| sludge metal | 69 |
| gothic metal | 69 |
| art rock | 65 |
| folk metal | 63 |
| folk rock | 62 |
| pop rock | 62 |
| post-punk | 61 |
| experimental | 61 |
| shoegaze | 55 |
| indie rock | 50 |
| heavy psych | 45 |
| gothic rock | 44 |
| dark folk | 42 |
| melodic death metal | 42 |
| speed metal | 42 |
| alternative metal | 41 |
| experimental rock | 40 |
| singer-songwriter | 39 |
| blackgaze | 38 |
| dungeon synth | 37 |
| death-doom metal | 36 |
| rock | 36 |
| new wave | 35 |
| crust punk | 33 |
| dark ambient | 33 |
| doom | 33 |
| folk | 33 |
| jazz fusion | 33 |
| aor | 32 |
| grunge | 31 |

## Primary Genres

| Primary genre | Tracks |
| --- | --- |
| black metal | 207 |
| doom metal | 112 |
| progressive rock | 100 |
| progressive metal | 80 |
| heavy metal | 74 |
| hard rock | 72 |
| electronic | 65 |
| alternative rock | 53 |
| death metal | 47 |
| psychedelic rock | 43 |
| atmospheric black metal | 42 |
| post-rock | 40 |
| stoner rock | 38 |
| thrash metal | 38 |
| rock | 27 |

## Countries

| Country | Tracks |
| --- | --- |
| United States | 620 |
| United Kingdom | 291 |
| Norway | 227 |
| Sweden | 165 |
| Germany | 98 |
| Finland | 73 |
| Canada | 54 |
| France | 49 |
| Russia | 47 |
| Denmark | 38 |
| Netherlands | 33 |
| Italy | 33 |
| Australia | 28 |
| Ireland | 22 |
| Poland | 19 |

## Artists

| Artist | Tracks |
| --- | --- |
| Enslaved | 50 |
| Darkthrone | 28 |
| Opeth | 21 |
| Ulver | 17 |
| Shape Of Despair | 12 |
| Wardruna | 12 |
| The Flight of Sleipnir | 10 |
| Clark | 9 |
| Frank Zappa | 9 |
| The Quakes | 9 |
| Lauge | 8 |
| My Dying Bride | 8 |
| Alcest | 7 |
| Biohazard | 7 |
| Carlo Domeniconi | 7 |

## Timeline

| Decade | Tracks |
| --- | --- |
| 2010s | 591 |
| 2020s | 554 |
| 2000s | 362 |
| 1990s | 219 |
| 1980s | 122 |
| 1970s | 105 |
| 1960s | 18 |
| 1950s | 1 |

## Latest

| Track | Artists | Year | Added |
| --- | --- | --- | --- |
| Further in the Making | Nils Frahm | 2021 | 2026-05-26 |
| So I Marched To The Sunken Empire | Darkthrone | 2026 | 2026-05-24 |
| Águas Passadas | Kaatayra | 2026 | 2026-05-15 |
| Let Us Live | Conjurer | 2025 | 2026-05-15 |
| Flammifer | Summoning | 2013 | 2026-05-14 |
| Terrestria III: Wither | Rivers of Nihil | 2018 | 2026-05-14 |
| Protestantisk Fanatiker (London Fields Darkwave) | heks | 2026 | 2026-05-08 |
| You Will Never Hold The Key | Spirit Adrift | 2026 | 2026-05-08 |
| The Great Deceiver | BULLDOZER | 1984 | 2026-04-29 |
| Another Beer (It's What I Need) | BULLDOZER | 1984 | 2026-04-29 |
| Valley of The Wolf | Üga Büga | 2026 | 2026-04-27 |
| Bend Towards The Dark | Immolation | 2026 | 2026-04-27 |

<details>
<summary>Workflow</summary>


- `python scripts/export_spotify.py` updates `data/tracks.csv` from saved tracks and owned/collaborative playlists.
- `python scripts/enrich_genres_musicbrainz.py` fills blank genres from cached MusicBrainz artist tags.
- `python scripts/backfill_countries_musicbrainz.py --fetch-missing-artists` backfills artist countries from MusicBrainz and Wikidata where available.
- `python scripts/apply_genre_rules.py` fills genres from `data/genre_rules.csv`.
- `python scripts/build_readme.py` regenerates this README and SVG charts.
- `python scripts/debug_spotify.py` checks OAuth and first Spotify API pages without writing CSV.
- Manual fields in `data/tracks.csv` are preserved on export: `year`, `primary_genre`, `genres`, `rating`, `status`, `tags`, `notes`.

</details>

<details>
<summary>Repeat this</summary>

Create a Spotify app, run the local OAuth export once, then store the generated refresh token as a GitHub secret. GitHub Actions can refresh the data weekly without using the local `.env` file.

</details>

<details>
<summary>Data</summary>

- Source table: [`data/tracks.csv`](data/tracks.csv)
- Genre rules: [`data/genre_rules.csv`](data/genre_rules.csv)
- Country overrides: [`data/country_overrides.csv`](data/country_overrides.csv)
- README generator: [`scripts/build_readme.py`](scripts/build_readme.py)
- Spotify exporter: [`scripts/export_spotify.py`](scripts/export_spotify.py)
- MusicBrainz country backfill: [`scripts/backfill_countries_musicbrainz.py`](scripts/backfill_countries_musicbrainz.py)
- MusicBrainz genre enricher: [`scripts/enrich_genres_musicbrainz.py`](scripts/enrich_genres_musicbrainz.py)
- Genre rule applier: [`scripts/apply_genre_rules.py`](scripts/apply_genre_rules.py)
- Spotify API debug: [`scripts/debug_spotify.py`](scripts/debug_spotify.py)

</details>

_Generated at 2026-06-03 08:05 UTC._

# Maks Krutikov Spotify Library

Personal Spotify metadata dashboard. No audio files, only generated summaries from a private CSV archive.

| Tracks | Artists | Albums | Tag genres | Assigned genres | Countries | Playlists | Release years | Duration |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1972 | 1367 | 1676 | 563 | 214 | 52 | 5 | 1958-2026 | 183h 53m |

> Each artist is assigned to exactly one dominant genre. Every genre card below shows top 10 artists, years and countries.

## Genre Atlas

## Metal

![Metal genre atlas](assets/atlas/metal.svg)

## Rock / Psych / Prog

![Rock / Psych / Prog genre atlas](assets/atlas/rock-psych-prog.svg)

## Electronic / Ambient

![Electronic / Ambient genre atlas](assets/atlas/electronic-ambient.svg)

## Punk / Hardcore

![Punk / Hardcore genre atlas](assets/atlas/punk-hardcore.svg)

## Folk / World

![Folk / World genre atlas](assets/atlas/folk-world.svg)

## Jazz / Blues

![Jazz / Blues genre atlas](assets/atlas/jazz-blues.svg)

## Soul / Funk / R&B

![Soul / Funk / R&B genre atlas](assets/atlas/soul-funk-r-b.svg)

## Reggae / Ska

![Reggae / Ska genre atlas](assets/atlas/reggae-ska.svg)

## Afrobeat / Latin

![Afrobeat / Latin genre atlas](assets/atlas/afrobeat-latin.svg)

## Classical / Score

![Classical / Score genre atlas](assets/atlas/classical-score.svg)

## Pop / Songwriter

![Pop / Songwriter genre atlas](assets/atlas/pop-songwriter.svg)

## Hip-Hop / Rap

![Hip-Hop / Rap genre atlas](assets/atlas/hip-hop-rap.svg)

## Experimental / Noise

![Experimental / Noise genre atlas](assets/atlas/experimental-noise.svg)

## Other

![Other genre atlas](assets/atlas/other.svg)

## Aggregates

### Top 20 Countries

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
| Poland | 20 |
| Belgium | 16 |
| Greece | 15 |
| Switzerland | 14 |
| Austria | 12 |
| Hungary | 11 |

### Top 20 Genres

| Genre | Tracks |
| --- | --- |
| black metal | 207 |
| doom metal | 112 |
| progressive rock | 100 |
| progressive metal | 80 |
| heavy metal | 74 |
| hard rock | 74 |
| electronic | 67 |
| alternative rock | 53 |
| death metal | 47 |
| psychedelic rock | 44 |
| atmospheric black metal | 42 |
| post-rock | 41 |
| stoner rock | 38 |
| thrash metal | 38 |
| ambient | 28 |
| rock | 27 |
| gothic metal | 26 |
| post-metal | 26 |
| sludge metal | 25 |
| post-punk | 24 |

### Top 20 Groups / Artists

| Group / artist | Tracks |
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
| Chelsea Wolfe | 7 |
| Counting Hours | 7 |
| Dark Suns | 7 |
| Devin Townsend | 7 |
| Rush | 7 |

<details>
<summary>Workflow</summary>


- `python scripts/export_spotify.py` updates `data/tracks.csv` from saved tracks and owned/collaborative playlists.
- `python scripts/enrich_genres_musicbrainz.py` fills blank genres from cached MusicBrainz artist tags.
- `python scripts/backfill_countries_musicbrainz.py --fetch-missing-artists` backfills artist countries from MusicBrainz and Wikidata where available.
- `python scripts/apply_genre_rules.py` fills genres from `data/genre_rules.csv`.
- `python scripts/build_readme.py` regenerates this README.
- `python scripts/debug_spotify.py` checks OAuth and first Spotify API pages without writing CSV.
- Manual fields in `data/tracks.csv` are preserved on export: `year`, `primary_genre`, `genres`, `rating`, `status`, `tags`, `notes`.
- Weekly GitHub Actions use a private data repository for `data/tracks.csv`; this public repository commits only generated summaries and public rules.

</details>

<details>
<summary>Repeat this</summary>

Create a Spotify app, run the local OAuth export once, store the full `data/tracks.csv` in a private data repository, then set public repository secrets described in `DATA.md`. GitHub Actions can refresh the public dashboard weekly without publishing the full CSV.

</details>

<details>
<summary>Data</summary>

- Source table: private `data/tracks.csv` fetched during the weekly workflow and not published in this repository.
- Data setup: [`DATA.md`](DATA.md)
- Track CSV example: [`data/tracks.example.csv`](data/tracks.example.csv)
- Genre rules: [`data/genre_rules.csv`](data/genre_rules.csv)
- Country overrides: [`data/country_overrides.csv`](data/country_overrides.csv)
- README generator: [`scripts/build_readme.py`](scripts/build_readme.py)
- Spotify exporter: [`scripts/export_spotify.py`](scripts/export_spotify.py)
- MusicBrainz country backfill: [`scripts/backfill_countries_musicbrainz.py`](scripts/backfill_countries_musicbrainz.py)
- MusicBrainz genre enricher: [`scripts/enrich_genres_musicbrainz.py`](scripts/enrich_genres_musicbrainz.py)
- Genre rule applier: [`scripts/apply_genre_rules.py`](scripts/apply_genre_rules.py)
- Spotify API debug: [`scripts/debug_spotify.py`](scripts/debug_spotify.py)

</details>

_Generated at 2026-06-03 09:07 UTC._

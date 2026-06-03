#!/usr/bin/env python3
from __future__ import annotations

import html
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from statistics import median

from build_readme import (
    COUNTRY_OVERRIDES_CSV,
    MUSICBRAINZ_ARTIST_CACHE,
    ROOT,
    TRACKS_CSV,
    all_artists,
    country_from_artist_data,
    duration_label,
    date_month,
    effective_genres,
    effective_primary_genre,
    norm,
    effective_year,
    read_country_overrides,
    read_json,
    read_tracks,
    split_values,
    top,
    track_countries,
    year_to_decade,
)


OUTPUT = ROOT / "mockups" / "readme-variants.html"

TrackRow = dict[str, str]
RankedRows = list[tuple[str, int]]

SUPER_GENRE_RULES = [
    (
        "Metal",
        (
            "metal",
            "doom",
            "blackgaze",
            "djent",
            "deathgrind",
            "grindcore",
            "mathcore",
            "sludge",
            "thrash",
        ),
    ),
    (
        "Rock / Psych / Prog",
        (
            "rock",
            "grunge",
            "shoegaze",
            "krautrock",
            "psychobilly",
            "rockabilly",
            "psych",
            "psychedelic",
            "prog",
            "jam band",
        ),
    ),
    (
        "Electronic / Ambient",
        (
            "electronic",
            "electronica",
            "ambient",
            "techno",
            "house",
            "idm",
            "synth",
            "trance",
            "dub",
            "downtempo",
            "drone",
            "dungeon synth",
            "drum and bass",
            "jungle",
            "breakbeat",
            "breakcore",
            "chillstep",
            "vaporwave",
            "dance",
            "electro",
            "dark wave",
            "darkwave",
            "coldwave",
        ),
    ),
    ("Punk / Hardcore", ("punk", "hardcore", "crust", "d-beat", "post-hardcore", "emo")),
    (
        "Folk / World",
        (
            "folk",
            "americana",
            "bluegrass",
            "neofolk",
            "country",
            "world",
            "celtic",
            "flamenco",
            "filmi",
            "junkanoo",
            "liedermacher",
        ),
    ),
    ("Jazz / Blues", ("jazz", "blues", "bossa nova", "post-bop", "swing")),
    ("Soul / Funk / R&B", ("soul", "funk", "r&b", "rhythm and blues")),
    ("Reggae / Ska", ("reggae", "ska")),
    ("Afrobeat / Latin", ("afrobeat", "afro-cuban", "latin")),
    (
        "Classical / Score",
        ("classical", "orchestral", "score", "soundtrack", "chamber", "opera", "choral", "production music"),
    ),
    ("Pop / Songwriter", ("pop", "singer-songwriter", "aor", "new wave")),
    ("Hip-Hop / Rap", ("hip hop", "rap", "trap")),
    ("Experimental / Noise", ("experimental", "noise", "avant-garde", "industrial")),
]


def esc(value: object) -> str:
    return html.escape(str(value if value is not None else ""), quote=True)


def compact_list(rows: RankedRows, limit: int = 8) -> str:
    return "\n".join(
        f'<li><span>{esc(name)}</span><b>{count}</b></li>' for name, count in rows[:limit]
    )


def inline_tags(rows: RankedRows, limit: int = 12) -> str:
    return "\n".join(
        f'<span class="tag">{esc(name)} <b>{count}</b></span>' for name, count in rows[:limit]
    )


def table(rows: RankedRows, label: str, limit: int = 10) -> str:
    body = "\n".join(
        f"<tr><td>{esc(name)}</td><td>{count}</td></tr>" for name, count in rows[:limit]
    )
    return f"""
      <table>
        <caption>{esc(label)}</caption>
        <tbody>
          {body}
        </tbody>
      </table>
    """


def bars(rows: RankedRows, limit: int = 8) -> str:
    if not rows:
        return ""
    max_value = max(value for _, value in rows[:limit]) or 1
    return "\n".join(
        f"""
        <div class="bar-row">
          <span>{esc(name)}</span>
          <div><i style="width:{round(value / max_value * 100, 1)}%"></i></div>
          <b>{value}</b>
        </div>
        """
        for name, value in rows[:limit]
    )


def metrics_grid(metrics: list[tuple[str, object]]) -> str:
    return "\n".join(
        f'<div class="metric"><b>{esc(value)}</b><span>{esc(label)}</span></div>'
        for label, value in metrics
    )


def has_genre(row: TrackRow, genre: str) -> bool:
    genre_key = genre.casefold()
    return any(value.casefold() == genre_key for value in effective_genres(row))


def super_genre(genre: str) -> str:
    genre_key = genre.casefold()
    for label, markers in SUPER_GENRE_RULES:
        if any(marker in genre_key for marker in markers):
            return label
    return "Other"


def dominant_row_genre(row: TrackRow) -> str:
    primary = effective_primary_genre(row).lower()
    fallback = effective_genres(row)
    return primary or (fallback[0].lower() if fallback else "")


def artists_assigned_to_genre(
    row: TrackRow,
    artist_genres: dict[str, str],
    genre: str,
) -> list[str]:
    return [artist for artist in all_artists(row) if artist_genres.get(artist) == genre]


def artist_country(
    artist: str,
    artist_cache: dict[str, object],
    country_overrides: dict[str, str],
) -> str:
    artist_key = norm(artist)
    return country_overrides.get(artist_key, "") or country_from_artist_data(
        artist_cache.get(artist_key)
    )


def artist_genre_assignments(
    tracks: list[TrackRow],
    genre_rows: RankedRows,
) -> dict[str, str]:
    genre_rank = {genre: index for index, (genre, _count) in enumerate(genre_rows)}
    artist_genres: dict[str, Counter[str]] = {}
    for row in tracks:
        genre = dominant_row_genre(row)
        if not genre:
            continue
        for artist in all_artists(row):
            artist_genres.setdefault(artist, Counter())[genre] += 1

    assignments: dict[str, str] = {}
    for artist, genre_counts in artist_genres.items():
        assignments[artist] = min(
            genre_counts,
            key=lambda genre: (-genre_counts[genre], genre_rank.get(genre, len(genre_rank)), genre),
        )
    return assignments


def assigned_genre_rows(
    tracks: list[TrackRow],
    artist_genres: dict[str, str],
) -> RankedRows:
    counts: Counter[str] = Counter()
    for row in tracks:
        row_genres = {
            artist_genres.get(artist)
            for artist in all_artists(row)
            if artist_genres.get(artist)
        }
        for genre in row_genres:
            counts[genre] += 1
    return top(counts, len(counts))


def micro_list(label: str, rows: RankedRows, limit: int = 10) -> str:
    if not rows:
        return f'<div class="micro-list"><h4>{esc(label)}</h4><p class="empty">No data</p></div>'
    items = "\n".join(
        f'<tr><td>{esc(name)}</td><td>{count}</td></tr>' for name, count in rows[:limit]
    )
    return f"""
      <div class="micro-list">
        <h4>{esc(label)}</h4>
        <table>{items}</table>
      </div>
    """


def genre_breakdown(
    tracks: list[TrackRow],
    artist_cache: dict[str, object],
    country_overrides: dict[str, str],
    genre_rows: RankedRows,
    artist_genres: dict[str, str],
    limit: int = 20,
) -> str:
    grouped: dict[str, RankedRows] = {}
    for genre, count in genre_rows[:limit]:
        grouped.setdefault(super_genre(genre), []).append((genre, count))

    group_order = [label for label, _markers in SUPER_GENRE_RULES] + ["Other"]
    sections: list[str] = []
    card_index = 0
    for group in group_order:
        group_rows = grouped.get(group, [])
        if not group_rows:
            continue
        group_tracks = sum(count for _genre, count in group_rows)
        cards: list[str] = []
        for genre, count in group_rows:
            card_index += 1
            rows = [
                row
                for row in tracks
                if artists_assigned_to_genre(row, artist_genres, genre)
            ]
            genre_artists = Counter(
                artist
                for row in rows
                for artist in artists_assigned_to_genre(row, artist_genres, genre)
            )
            genre_years = Counter(effective_year(row) for row in rows if effective_year(row).isdigit())
            genre_countries = Counter(
                country
                for row in rows
                for artist in artists_assigned_to_genre(row, artist_genres, genre)
                for country in [artist_country(artist, artist_cache, country_overrides)]
                if country
            )
            cards.append(
                f"""
                <section class="genre-card">
                  <div class="genre-card-head">
                    <span>{card_index:02d}</span>
                    <h3>{esc(genre)}</h3>
                    <b>{count} total tracks · top 10 rows below</b>
                  </div>
                  <div class="micro-grid">
                    {micro_list("Artists", top(genre_artists, 10))}
                    {micro_list("Years", top(genre_years, 10))}
                    {micro_list("Countries", top(genre_countries, 10))}
                  </div>
                </section>
                """
            )
        sections.append(
            f"""
            <section class="super-genre">
              <div class="super-genre-head">
                <h3>{esc(group)}</h3>
                <b>{len(group_rows)} genres · {group_tracks} tracks</b>
              </div>
              <div class="genre-drilldown">{"".join(cards)}</div>
            </section>
            """
        )
    return "".join(sections)


def aggregate_tables(
    countries: RankedRows,
    genres: RankedRows,
    artists: RankedRows,
) -> str:
    return f"""
      <section class="aggregate-block">
        <div class="aggregate-head">
          <h3>Aggregates</h3>
          <b>top 20 tables</b>
        </div>
        <div class="aggregate-grid">
          {table(countries, "Top 20 countries", 20)}
          {table(genres, "Top 20 genres", 20)}
          {table(artists, "Top 20 groups / artists", 20)}
        </div>
      </section>
    """


def section(title: str, description: str, body: str) -> str:
    return f"""
    <article class="variant">
      <header>
        <p>README variant</p>
        <h2>{esc(title)}</h2>
        <span>{esc(description)}</span>
      </header>
      {body}
    </article>
    """


def build_html() -> str:
    tracks = read_tracks(TRACKS_CSV)
    artist_cache = read_json(MUSICBRAINZ_ARTIST_CACHE)
    country_overrides = read_country_overrides(COUNTRY_OVERRIDES_CSV)

    artists = Counter(artist for row in tracks for artist in all_artists(row))
    genres = Counter(genre.lower() for row in tracks for genre in effective_genres(row))
    primary_genres = Counter(
        effective_primary_genre(row).lower() for row in tracks if effective_primary_genre(row)
    )
    countries = Counter(
        country for row in tracks for country in track_countries(row, artist_cache, country_overrides)
    )
    years = Counter(effective_year(row) for row in tracks if effective_year(row).isdigit())
    decades = Counter(year_to_decade(effective_year(row)) for row in tracks if year_to_decade(effective_year(row)))
    playlists = Counter(
        playlist for row in tracks for playlist in split_values(row.get("playlist_names", "")) if playlist
    )
    sources = Counter(source for row in tracks for source in split_values(row.get("sources", "")) if source)
    albums = {
        row.get("album_id") or f"{row.get('artist_names', '')}|{row.get('album_name', '')}"
        for row in tracks
        if row.get("album_id") or row.get("album_name")
    }
    durations = [
        int(row.get("duration_ms") or 0)
        for row in tracks
        if (row.get("duration_ms") or "").isdigit()
    ]
    known_years = sorted(int(year) for year in years if year.isdigit())
    added_months = Counter(
        month for row in tracks if (month := date_month(row.get("latest_added_at", "")))
    )
    added_years = Counter(
        year for row in tracks if (year := row.get("latest_added_at", "")[:4]) and year.isdigit()
    )
    current_year_label = str(datetime.now(timezone.utc).year)
    added_current_year = added_years.get(current_year_label, 0)
    recent_genres = Counter(
        genre
        for row in tracks
        if row.get("latest_added_at", "")[:4] == current_year_label
        for genre in effective_genres(row)
    )
    latest_added = max((row.get("latest_added_at", "")[:10] for row in tracks), default="")
    explicit_count = sum(1 for row in tracks if row.get("explicit", "").casefold() == "true")
    genre_coverage = round(sum(1 for row in tracks if effective_genres(row)) / max(len(tracks), 1) * 100)
    country_coverage = round(
        sum(1 for row in tracks if track_countries(row, artist_cache, country_overrides))
        / max(len(tracks), 1)
        * 100
    )
    median_year = int(median(known_years)) if known_years else ""
    total_ms = sum(durations)
    avg_ms = int(total_ms / len(durations)) if durations else 0
    peak_year, peak_year_count = top(years, 1)[0] if years else ("", 0)
    year_range = f"{known_years[0]}-{known_years[-1]}" if known_years else ""
    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    core_metrics = [
        ("tracks", len(tracks)),
        ("artists", len(artists)),
        ("albums", len(albums)),
        ("genres", len(genres)),
        ("countries", len(countries)),
        ("duration", duration_label(total_ms)),
    ]
    compact_metrics = [
        ("release years", year_range),
        ("median year", median_year),
        ("avg track", duration_label(avg_ms)),
        ("genre coverage", f"{genre_coverage}%"),
        ("country coverage", f"{country_coverage}%"),
        (f"added in {current_year_label}", added_current_year),
    ]
    source_metrics = [
        ("liked", sources.get("liked", 0)),
        ("playlist", sources.get("playlist", 0)),
        ("playlists", len(playlists)),
        ("explicit", explicit_count),
    ]
    top_genres = top(genres, len(genres))
    top_primary = top(primary_genres, 12)
    top_artists = top(artists, len(artists))
    top_countries = top(countries, len(countries))
    top_decades = top(decades, 8)
    top_years = top(years, 10)
    artist_genres = artist_genre_assignments(tracks, top_genres)
    assigned_genres = assigned_genre_rows(tracks, artist_genres)

    variants = [
        section(
            "01. Dense Ledger",
            "A compact genre atlas: every genre with top artists, years and countries inside each.",
            f"""
            <div class="metrics six">{metrics_grid(core_metrics)}</div>
            <div class="note">Each artist is assigned to exactly one dominant genre. All {len(assigned_genres)} assigned genres are grouped by parent genre; every card shows top 10 artists, release years and countries.</div>
            {genre_breakdown(tracks, artist_cache, country_overrides, assigned_genres, artist_genres, len(assigned_genres))}
            {aggregate_tables(top_countries, assigned_genres, top_artists)}
            """,
        ),
        section(
            "02. Signal Strip",
            "A narrow hero with the strongest numbers and no large artwork.",
            f"""
            <div class="hero-line">
              <strong>Maks Krutikov Spotify Library</strong>
              <span>{len(tracks)} tracks across {year_range}</span>
            </div>
            <div class="metrics three">{metrics_grid(compact_metrics)}</div>
            <div class="tags">{inline_tags(top_genres, 14)}</div>
            """,
        ),
        section(
            "03. Genre Index",
            "Best if the repository is mostly about genre taxonomy.",
            f"""
            <div class="note">Top 50 genres are shown in the real README; preview keeps the first 25 visible.</div>
            <div class="genre-grid">{inline_tags(top_genres, 25)}</div>
            """,
        ),
        section(
            "04. Atlas",
            "Uses countries as the differentiating feature.",
            f"""
            <div class="metrics three">{metrics_grid([("countries", len(countries)), ("coverage", f"{country_coverage}%"), ("top country", top_countries[0][0] if top_countries else "")])}</div>
            <div class="split">
              <div class="bars">{bars(top_countries, 10)}</div>
              {table(top_decades, "Decades", 8)}
            </div>
            """,
        ),
        section(
            "05. Timeline First",
            "Good when the library's historical range is the hook.",
            f"""
            <div class="metrics four">{metrics_grid([("range", year_range), ("median", median_year), ("peak year", f"{peak_year} ({peak_year_count})"), ("duration", duration_label(total_ms))])}</div>
            <div class="bars">{bars(top_decades, 8)}</div>
            """,
        ),
        section(
            "06. Recent Shelf",
            "Makes the README feel alive by emphasizing newest additions.",
            f"""
            <div class="metrics three">{metrics_grid([("latest added", latest_added), (f"added in {current_year_label}", added_current_year), ("playlists", len(playlists))])}</div>
            <div class="aggregate-grid">
              {table(top(added_months, 10), "Added months", 10)}
              {table(top(added_years, 10), "Added years", 10)}
              {table(top(recent_genres, 10), f"{current_year_label} genres", 10)}
            </div>
            """,
        ),
        section(
            "07. Metadata Audit",
            "A compact public-repo angle: this is a data quality dashboard.",
            f"""
            <div class="metrics four">{metrics_grid(compact_metrics[:4])}</div>
            <div class="split">
              {table(source_metrics, "Sources", 4)}
              {table(top_primary, "Primary genres", 8)}
            </div>
            """,
        ),
        section(
            "08. Artist Spine",
            "Lead with artists, keep genres secondary.",
            f"""
            <div class="split">
              <ul class="rank large">{compact_list(top_artists, 12)}</ul>
              <div>
                <div class="metrics two">{metrics_grid([("artists", len(artists)), ("albums", len(albums))])}</div>
                <div class="tags">{inline_tags(top_primary, 10)}</div>
              </div>
            </div>
            """,
        ),
        section(
            "09. Minimal README",
            "The shortest version that still has personality.",
            f"""
            <p class="lede">Personal Spotify metadata archive: no audio files, only track metadata, local edits, genre rules, and generated summaries.</p>
            <div class="metrics six">{metrics_grid(core_metrics)}</div>
            <div class="mini-columns">
              <div><h3>Top genres</h3><p>{", ".join(esc(name) for name, _ in top_genres[:8])}</p></div>
              <div><h3>Top countries</h3><p>{", ".join(esc(name) for name, _ in top_countries[:8])}</p></div>
            </div>
            """,
        ),
        section(
            "10. Public Repo",
            "Adds context for visitors who do not know the workflow.",
            f"""
            <div class="metrics three">{metrics_grid([("data rows", len(tracks)), ("manual fields", "7"), ("generated", generated_at)])}</div>
            <div class="workflow">
              <span>Spotify export</span>
              <span>MusicBrainz tags</span>
              <span>Local genre rules</span>
              <span>README + SVG</span>
            </div>
            <div class="split">
              {table(top_genres, "Genre preview", 8)}
              {table(top_countries, "Country preview", 8)}
            </div>
            """,
        ),
    ]

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>README mockups - myfavmusic</title>
  <style>
    :root {{
      color-scheme: light;
      --paper: #f7f6f0;
      --ink: #202722;
      --muted: #677169;
      --line: #cfd6ce;
      --panel: #fffefa;
      --green: #557e64;
      --blue: #526f92;
      --rust: #a96855;
      --gold: #9a7a34;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      background: var(--paper);
      color: var(--ink);
      font: 13px/1.35 Inter, ui-sans-serif, system-ui, -apple-system, "Segoe UI", Arial, sans-serif;
    }}
    main {{
      width: min(1180px, calc(100% - 32px));
      margin: 28px auto 48px;
    }}
    .page-head {{
      display: grid;
      grid-template-columns: 1fr auto;
      gap: 16px;
      align-items: end;
      border-bottom: 1px solid var(--line);
      padding-bottom: 18px;
      margin-bottom: 18px;
    }}
    h1, h2, h3, p {{ margin: 0; }}
    h1 {{ font-size: 28px; line-height: 1.1; letter-spacing: 0; }}
    .page-head p, .variant header span, .note, caption, .lede {{ color: var(--muted); }}
    .page-head code {{
      border: 1px solid var(--line);
      border-radius: 6px;
      padding: 6px 8px;
      background: #ffffffa8;
      font-size: 12px;
    }}
    .variant {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      margin-top: 14px;
      padding: 18px;
    }}
    .variant:first-of-type {{
      padding: 12px;
    }}
    .variant:first-of-type header {{
      margin-bottom: 9px;
    }}
    .variant:first-of-type .metrics {{
      gap: 5px;
      margin-bottom: 8px;
    }}
    .variant:first-of-type .metric {{
      padding: 6px 7px;
      border-top-width: 2px;
    }}
    .variant:first-of-type .metric b {{
      font-size: 17px;
    }}
    .variant:first-of-type .metric span {{
      font-size: 10px;
    }}
    .variant:first-of-type .note {{
      margin-bottom: 8px;
      font-size: 12px;
    }}
    .variant header {{
      display: grid;
      grid-template-columns: 128px 1fr;
      gap: 8px 18px;
      align-items: baseline;
      margin-bottom: 14px;
    }}
    .variant header p {{
      color: var(--green);
      font-weight: 800;
      text-transform: uppercase;
      font-size: 11px;
      letter-spacing: .06em;
    }}
    .variant header h2 {{
      font-size: 20px;
      line-height: 1.15;
    }}
    .variant header span {{
      grid-column: 2;
    }}
    .metrics {{
      display: grid;
      gap: 8px;
      margin-bottom: 14px;
    }}
    .metrics.two {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }}
    .metrics.three {{ grid-template-columns: repeat(3, minmax(0, 1fr)); }}
    .metrics.four {{ grid-template-columns: repeat(4, minmax(0, 1fr)); }}
    .metrics.six {{ grid-template-columns: repeat(6, minmax(0, 1fr)); }}
    .metric {{
      border-top: 3px solid var(--green);
      background: #f4f1e8;
      padding: 9px 10px;
      min-width: 0;
    }}
    .metric:nth-child(2n) {{ border-color: var(--blue); }}
    .metric:nth-child(3n) {{ border-color: var(--rust); }}
    .metric b {{
      display: block;
      font-size: 20px;
      line-height: 1.05;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }}
    .metric span {{
      color: var(--muted);
      font-size: 12px;
      text-transform: uppercase;
      letter-spacing: .04em;
    }}
    .split {{
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 16px;
      align-items: start;
    }}
    .rank {{
      list-style: none;
      padding: 0;
      margin: 0;
      border-top: 1px solid var(--line);
    }}
    .rank li {{
      display: grid;
      grid-template-columns: 1fr auto;
      gap: 12px;
      padding: 7px 0;
      border-bottom: 1px solid var(--line);
    }}
    .rank span {{
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }}
    .rank b, td:last-child {{ color: var(--green); }}
    .rank.muted b {{ color: var(--blue); }}
    .rank.large li {{ padding: 8px 0; }}
    .hero-line {{
      display: flex;
      justify-content: space-between;
      gap: 16px;
      align-items: center;
      border: 1px solid var(--line);
      border-left: 6px solid var(--green);
      padding: 14px;
      margin-bottom: 12px;
      background: #f8f4e9;
    }}
    .hero-line strong {{ font-size: 22px; }}
    .hero-line span {{ color: var(--muted); }}
    .tags, .genre-grid {{
      display: flex;
      flex-wrap: wrap;
      gap: 7px;
    }}
    .tag {{
      border: 1px solid var(--line);
      background: #fbfaf6;
      border-radius: 999px;
      padding: 5px 9px;
      white-space: nowrap;
    }}
    .tag b {{ color: var(--rust); }}
    .note {{
      border-left: 4px solid var(--gold);
      padding-left: 10px;
      margin-bottom: 12px;
    }}
    table {{
      width: 100%;
      border-collapse: collapse;
      font-size: 13px;
    }}
    caption {{
      text-align: left;
      font-weight: 800;
      margin-bottom: 7px;
      color: var(--ink);
    }}
    th, td {{
      text-align: left;
      padding: 7px 0;
      border-bottom: 1px solid var(--line);
      vertical-align: top;
    }}
    th {{ color: var(--muted); font-size: 12px; }}
    td:not(:first-child), th:not(:first-child) {{ padding-left: 12px; }}
    .bar-row {{
      display: grid;
      grid-template-columns: minmax(110px, 1fr) 2fr 42px;
      gap: 10px;
      align-items: center;
      margin: 8px 0;
    }}
    .bar-row span {{
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }}
    .bar-row div {{
      height: 10px;
      background: #e5e7de;
      border-radius: 99px;
      overflow: hidden;
    }}
    .bar-row i {{
      display: block;
      height: 100%;
      background: linear-gradient(90deg, var(--green), var(--blue));
    }}
    .bar-row b {{
      color: var(--green);
      text-align: right;
    }}
    .mini-columns {{
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 16px;
      margin-top: 12px;
    }}
    .mini-columns h3 {{
      font-size: 13px;
      color: var(--muted);
      text-transform: uppercase;
      letter-spacing: .04em;
      margin-bottom: 5px;
    }}
    .workflow {{
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: 8px;
      margin-bottom: 14px;
    }}
    .workflow span {{
      border-bottom: 3px solid var(--blue);
      background: #eef1ee;
      padding: 9px;
      text-align: center;
      font-weight: 700;
    }}
    .super-genre {{
      margin-top: 18px;
      padding-top: 5px;
      border-top: 3px solid #9aa99b;
    }}
    .super-genre:first-of-type {{
      margin-top: 9px;
    }}
    .super-genre-head {{
      position: sticky;
      top: 0;
      z-index: 2;
      display: flex;
      align-items: baseline;
      justify-content: space-between;
      gap: 12px;
      border: 1px solid #26372f;
      border-left: 10px solid var(--rust);
      background: #26372f;
      color: #fbfaf6;
      padding: 8px 10px;
      margin: 0 0 7px;
      box-shadow: 0 2px 0 #d7d8ce;
    }}
    .super-genre:nth-of-type(3n + 1) .super-genre-head {{
      border-left-color: var(--green);
    }}
    .super-genre:nth-of-type(3n + 2) .super-genre-head {{
      border-left-color: var(--blue);
    }}
    .super-genre-head h3 {{
      font-size: 17px;
      line-height: 1.1;
      font-weight: 900;
    }}
    .super-genre-head b {{
      color: #dce4dc;
      font-size: 11px;
      white-space: nowrap;
    }}
    .aggregate-block {{
      margin-top: 18px;
      padding-top: 5px;
      border-top: 3px solid #9aa99b;
    }}
    .aggregate-head {{
      display: flex;
      align-items: baseline;
      justify-content: space-between;
      gap: 12px;
      border: 1px solid #26372f;
      border-left: 10px solid var(--blue);
      background: #26372f;
      color: #fbfaf6;
      padding: 8px 10px;
      margin: 0 0 7px;
      box-shadow: 0 2px 0 #d7d8ce;
    }}
    .aggregate-head h3 {{
      font-size: 17px;
      line-height: 1.1;
      font-weight: 900;
    }}
    .aggregate-head b {{
      color: #dce4dc;
      font-size: 11px;
      white-space: nowrap;
    }}
    .aggregate-grid {{
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 8px;
    }}
    .aggregate-grid table {{
      background: #fbfaf6;
      border: 1px solid #bec8bd;
      border-collapse: collapse;
      font-size: 12px;
    }}
    .aggregate-grid caption {{
      background: #eef1e9;
      border-bottom: 1px solid #c5cec3;
      padding: 5px 7px;
      margin: 0;
    }}
    .aggregate-grid td {{
      padding: 3px 7px;
    }}
    .aggregate-grid td:first-child {{
      max-width: 0;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }}
    .genre-drilldown {{
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 6px;
    }}
    .genre-card {{
      border: 1px solid #bec8bd;
      border-left: 4px solid var(--green);
      background: linear-gradient(90deg, #f5f2e9 0, #f5f2e9 7px, #fbfaf6 7px);
      padding: 7px;
      min-width: 0;
      box-shadow: inset 0 1px 0 #ffffff, 0 1px 0 #e7e2d7;
    }}
    .genre-card:nth-child(3n + 2) {{
      border-left-color: var(--blue);
    }}
    .genre-card:nth-child(3n) {{
      border-left-color: var(--rust);
    }}
    .genre-card-head {{
      display: grid;
      grid-template-columns: 26px 1fr auto;
      gap: 7px;
      align-items: baseline;
      border-bottom: 1px solid #c5cec3;
      padding: 4px 5px 5px;
      margin: -2px -1px 5px;
      background: #eef1e9;
    }}
    .genre-card-head span {{
      color: var(--rust);
      font-weight: 800;
      font-size: 10px;
    }}
    .genre-card-head h3 {{
      min-width: 0;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
      font-size: 14px;
      font-weight: 850;
      line-height: 1.15;
    }}
    .genre-card-head b {{
      color: var(--green);
      font-size: 11px;
      white-space: nowrap;
    }}
    .micro-grid {{
      display: grid;
      grid-template-columns: minmax(0, 1.25fr) 66px minmax(0, 1.05fr);
      gap: 5px;
    }}
    .micro-list {{
      min-width: 0;
    }}
    .micro-list + .micro-list {{
      border-left: 1px solid var(--line);
      padding-left: 5px;
    }}
    .micro-list h4 {{
      margin: 0 0 2px;
      color: var(--muted);
      font-size: 10px;
      text-transform: uppercase;
      letter-spacing: .04em;
    }}
    .micro-list table {{
      width: 100%;
      border-collapse: collapse;
      margin: 0;
      font-size: 11px;
      line-height: 1.2;
    }}
    .micro-list td {{
      padding: 1px 0;
      border-bottom: 1px solid #e5e1d5;
      vertical-align: top;
    }}
    .micro-list td:first-child {{
      max-width: 0;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }}
    .micro-list td:last-child {{
      color: var(--blue);
      font-weight: 800;
      text-align: right;
      padding-left: 4px;
      width: 1%;
      white-space: nowrap;
    }}
    .empty {{
      color: var(--muted);
      font-size: 11px;
    }}
    @media (max-width: 820px) {{
      main {{ width: min(100% - 20px, 620px); margin-top: 18px; }}
      .page-head, .variant header, .split, .mini-columns {{
        grid-template-columns: 1fr;
      }}
      .variant header span {{ grid-column: auto; }}
      .metrics.two, .metrics.three, .metrics.four, .metrics.six {{
        grid-template-columns: repeat(2, minmax(0, 1fr));
      }}
      .workflow {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }}
      .genre-drilldown {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }}
      .aggregate-grid {{ grid-template-columns: 1fr; }}
      .hero-line {{ align-items: flex-start; flex-direction: column; }}
    }}
    @media (max-width: 460px) {{
      .metrics.two, .metrics.three, .metrics.four, .metrics.six {{
        grid-template-columns: 1fr;
      }}
      .workflow {{ grid-template-columns: 1fr; }}
      .variant {{ padding: 14px; }}
      .bar-row {{ grid-template-columns: 1fr 42px; }}
      .bar-row div {{ grid-column: 1 / -1; grid-row: 2; }}
      .genre-drilldown {{ grid-template-columns: 1fr; }}
      .genre-card-head {{ grid-template-columns: 30px 1fr; }}
      .genre-card-head b {{ grid-column: 2; }}
      .micro-grid {{ grid-template-columns: 1fr; }}
      .micro-list + .micro-list {{
        border-left: 0;
        border-top: 1px solid var(--line);
        padding-left: 0;
        padding-top: 8px;
      }}
    }}
  </style>
</head>
<body>
  <main>
    <header class="page-head">
      <div>
        <h1>README mockups for myfavmusic</h1>
        <p>Ten compact directions built from the current CSV snapshot. Same visual language, different information hierarchy.</p>
      </div>
      <code>generated {esc(generated_at)}</code>
    </header>
    {"".join(variants)}
  </main>
</body>
</html>
"""


def main() -> None:
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    html_output = "\n".join(line.rstrip() for line in build_html().splitlines()) + "\n"
    OUTPUT.write_text(html_output, encoding="utf-8")
    print(f"Wrote {OUTPUT}")


if __name__ == "__main__":
    main()

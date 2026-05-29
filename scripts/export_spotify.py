#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
import csv
import hashlib
import http.server
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
import socket
from pathlib import Path
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[1]
DATA_PATH = ROOT / "data" / "tracks.csv"
CACHE_DIR = ROOT / ".cache"
TOKEN_CACHE = CACHE_DIR / "spotify-token.json"
ARTIST_CACHE = CACHE_DIR / "spotify-artists.json"

API_BASE = "https://api.spotify.com/v1"
AUTH_URL = "https://accounts.spotify.com/authorize"
TOKEN_URL = "https://accounts.spotify.com/api/token"
DEFAULT_REDIRECT_URI = "http://127.0.0.1:8888/callback"
DEFAULT_SCOPE = "user-library-read playlist-read-private playlist-read-collaborative"
MAX_RETRY_AFTER_SECONDS = max(1, int(os.getenv("SPOTIFY_MAX_RETRY_AFTER_SECONDS", "300")))
MAX_RATE_LIMIT_RETRIES = max(1, int(os.getenv("SPOTIFY_MAX_RATE_LIMIT_RETRIES", "20")))
ARTIST_BATCH_SIZE = max(1, int(os.getenv("SPOTIFY_ARTIST_BATCH_SIZE", "1")))

MANUAL_FIELDS = ["year", "primary_genre", "genres", "rating", "status", "tags", "notes"]
FIELDNAMES = [
    "track_id",
    "track_name",
    "artist_names",
    "album_name",
    "spotify_year",
    "year",
    "spotify_genres",
    "primary_genre",
    "genres",
    "release_date",
    "duration_ms",
    "explicit",
    "popularity",
    "spotify_url",
    "album_id",
    "artist_ids",
    "track_number",
    "disc_number",
    "sources",
    "playlist_names",
    "first_added_at",
    "latest_added_at",
    "rating",
    "status",
    "tags",
    "notes",
]


class SpotifyApiError(RuntimeError):
    def __init__(self, status: int, message: str) -> None:
        super().__init__(f"Spotify API returned {status}: {message}")
        self.status = status
        self.message = message


def parse_args() -> argparse.Namespace:
    load_dotenv(ROOT / ".env")
    parser = argparse.ArgumentParser(
        description="Export Spotify track metadata to data/tracks.csv."
    )
    parser.add_argument("--output", type=Path, default=DATA_PATH)
    parser.add_argument("--client-id", default=os.getenv("SPOTIFY_CLIENT_ID"))
    parser.add_argument("--client-secret", default=os.getenv("SPOTIFY_CLIENT_SECRET"))
    parser.add_argument(
        "--redirect-uri",
        default=os.getenv("SPOTIFY_REDIRECT_URI", DEFAULT_REDIRECT_URI),
    )
    parser.add_argument("--market", default=os.getenv("SPOTIFY_MARKET"))
    parser.add_argument("--scope", default=os.getenv("SPOTIFY_SCOPE", DEFAULT_SCOPE))
    parser.add_argument(
        "--playlist-id",
        action="append",
        default=[],
        help="Specific playlist ID to include. Can be used more than once.",
    )
    parser.add_argument(
        "--no-saved",
        action="store_true",
        help="Skip saved tracks from Your Music.",
    )
    parser.add_argument(
        "--no-playlists",
        action="store_true",
        help="Skip owned/collaborative playlists.",
    )
    parser.add_argument(
        "--no-interactive",
        action="store_true",
        help="Fail instead of asking for a pasted OAuth callback URL.",
    )
    parser.add_argument(
        "--manual-oauth",
        action="store_true",
        help="Print the OAuth URL and ask for the redirected URL instead of opening a local callback server.",
    )
    parser.add_argument(
        "--skip-genres",
        action="store_true",
        help="Skip artist genre enrichment. Useful for debugging the track export quickly.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Stop after collecting this many unique tracks. Useful for local debugging.",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print progress while exporting.",
    )
    parser.add_argument(
        "--log-file",
        type=Path,
        default=CACHE_DIR / "export.log",
        help="Write progress logs to this file.",
    )
    return parser.parse_args()


def load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as file:
        json.dump(data, file, indent=2, sort_keys=True)
        file.write("\n")


def log_progress(args: argparse.Namespace, message: str) -> None:
    if not getattr(args, "verbose", False):
        return
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{timestamp}] {message}"
    print(line, flush=True)
    log_file = resolve_path(getattr(args, "log_file", CACHE_DIR / "export.log"))
    log_file.parent.mkdir(parents=True, exist_ok=True)
    with log_file.open("a", encoding="utf-8") as file:
        file.write(line + "\n")


def resolve_path(path: Path) -> Path:
    return path if path.is_absolute() else ROOT / path


def post_form(url: str, data: dict[str, str], client_id: str, client_secret: str) -> dict[str, Any]:
    encoded = urllib.parse.urlencode(data).encode("utf-8")
    basic = base64.b64encode(f"{client_id}:{client_secret}".encode("utf-8")).decode("ascii")
    request = urllib.request.Request(
        url,
        data=encoded,
        method="POST",
        headers={
            "Authorization": f"Basic {basic}",
            "Content-Type": "application/x-www-form-urlencoded",
        },
    )
    last_network_error: Exception | None = None
    for attempt in range(MAX_RATE_LIMIT_RETRIES):
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as error:
            body = error.read().decode("utf-8", errors="replace")
            if error.code == 429:
                retry_after = int(error.headers.get("Retry-After", "5"))
                if retry_after > MAX_RETRY_AFTER_SECONDS:
                    raise SpotifyApiError(error.code, f"rate limited for {retry_after} seconds") from error
                time.sleep(max(retry_after, 1) + 1)
                continue
            raise SpotifyApiError(error.code, body) from error
        except (ConnectionError, TimeoutError, socket.timeout, urllib.error.URLError) as error:
            last_network_error = error
            time.sleep(min(2 + attempt * 2, 30))
            continue
    if last_network_error:
        reason = getattr(last_network_error, "reason", last_network_error)
        raise SpotifyApiError(0, str(reason)) from last_network_error
    raise SpotifyApiError(429, "form retry budget exhausted")


def with_expiry(token: dict[str, Any]) -> dict[str, Any]:
    if "expires_in" in token:
        token["expires_at"] = int(time.time()) + int(token["expires_in"])
    return token


def token_valid(token: dict[str, Any]) -> bool:
    return bool(token.get("access_token")) and int(token.get("expires_at", 0)) > int(time.time()) + 60


def refresh_access_token(
    token: dict[str, Any],
    client_id: str,
    client_secret: str,
) -> dict[str, Any]:
    refresh_token = token.get("refresh_token") or os.getenv("SPOTIFY_REFRESH_TOKEN")
    if not refresh_token:
        raise SpotifyApiError(401, "missing refresh token")
    refreshed = post_form(
        TOKEN_URL,
        {"grant_type": "refresh_token", "refresh_token": refresh_token},
        client_id,
        client_secret,
    )
    if "refresh_token" not in refreshed:
        refreshed["refresh_token"] = refresh_token
    return with_expiry(refreshed)


def request_client_credentials_token(client_id: str, client_secret: str) -> dict[str, Any]:
    token = post_form(
        TOKEN_URL,
        {"grant_type": "client_credentials"},
        client_id,
        client_secret,
    )
    token["grant_type"] = "client_credentials"
    return with_expiry(token)


def request_user_token(
    client_id: str,
    client_secret: str,
    redirect_uri: str,
    scope: str,
    manual_oauth: bool,
) -> dict[str, Any]:
    state = hashlib.sha256(os.urandom(16)).hexdigest()[:16]
    params = {
        "response_type": "code",
        "client_id": client_id,
        "scope": scope,
        "redirect_uri": redirect_uri,
        "state": state,
    }
    auth_url = f"{AUTH_URL}?{urllib.parse.urlencode(params)}"
    query = None if manual_oauth else receive_local_callback(auth_url, redirect_uri, timeout_seconds=300)
    if query is None:
        print("Open this URL in your browser and approve access:")
        print(auth_url)
        callback_url = input("Paste the full redirected URL here: ").strip()
        parsed = urllib.parse.urlparse(callback_url)
        query = urllib.parse.parse_qs(parsed.query)

    if query.get("state", [""])[0] != state:
        raise SystemExit("OAuth state mismatch. Try again.")
    if "error" in query:
        raise SystemExit(f"Spotify authorization failed: {query['error'][0]}")
    code = query.get("code", [""])[0]
    if not code:
        raise SystemExit("No OAuth code found in pasted URL.")
    token = post_form(
        TOKEN_URL,
        {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_uri,
        },
        client_id,
        client_secret,
    )
    return with_expiry(token)


class OAuthCallbackHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        expected_path = getattr(self.server, "expected_path", "/callback")
        if parsed.path != expected_path:
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b"Unknown OAuth callback path.")
            return

        query = urllib.parse.parse_qs(parsed.query)
        setattr(self.server, "oauth_query", query)
        error = query.get("error", [""])[0]
        message = "Spotify authorization failed. You can close this tab." if error else "Spotify authorization complete. You can close this tab."
        body = f"""<!doctype html>
<html lang="en">
<head><meta charset="utf-8"><title>Spotify authorization</title></head>
<body style="font-family: system-ui, sans-serif; margin: 3rem;">
<h1>{message}</h1>
<p>Return to the terminal to continue.</p>
</body>
</html>
"""
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body.encode("utf-8"))))
        self.end_headers()
        self.wfile.write(body.encode("utf-8"))

    def log_message(self, _format: str, *_args: Any) -> None:
        return


def receive_local_callback(
    auth_url: str,
    redirect_uri: str,
    timeout_seconds: int,
) -> dict[str, list[str]] | None:
    parsed = urllib.parse.urlparse(redirect_uri)
    if parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "localhost"}:
        return None

    host = parsed.hostname
    port = parsed.port or 80
    path = parsed.path or "/"
    try:
        server = http.server.HTTPServer((host, port), OAuthCallbackHandler)
    except OSError as error:
        print(f"Could not start local OAuth callback server: {error}", file=sys.stderr)
        return None

    setattr(server, "expected_path", path)
    setattr(server, "oauth_query", None)
    server.timeout = 1

    print("Opening Spotify authorization in your browser.")
    print(f"If the browser does not open, use this URL:\n{auth_url}")
    webbrowser.open(auth_url)

    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        server.handle_request()
        query = getattr(server, "oauth_query", None)
        if query is not None:
            server.server_close()
            return query

    server.server_close()
    print("Timed out waiting for Spotify OAuth callback.", file=sys.stderr)
    return None


def load_token(args: argparse.Namespace) -> dict[str, Any]:
    if not args.client_id or not args.client_secret:
        raise SystemExit(
            "Set SPOTIFY_CLIENT_ID and SPOTIFY_CLIENT_SECRET, or pass --client-id and --client-secret."
        )

    token = read_json(TOKEN_CACHE, {})
    if os.getenv("SPOTIFY_REFRESH_TOKEN") and not token.get("refresh_token"):
        token["refresh_token"] = os.getenv("SPOTIFY_REFRESH_TOKEN")

    if token_valid(token):
        return token

    if token.get("refresh_token"):
        token = refresh_access_token(token, args.client_id, args.client_secret)
        write_json(TOKEN_CACHE, token)
        return token

    if args.no_interactive:
        raise SystemExit(
            "No cached token or SPOTIFY_REFRESH_TOKEN available, and --no-interactive was set."
        )

    token = request_user_token(
        args.client_id,
        args.client_secret,
        args.redirect_uri,
        args.scope,
        args.manual_oauth,
    )
    write_json(TOKEN_CACHE, token)
    return token


class SpotifyClient:
    def __init__(
        self,
        token: dict[str, Any],
        client_id: str,
        client_secret: str,
        cache_token: bool = True,
    ) -> None:
        self.token = token
        self.client_id = client_id
        self.client_secret = client_secret
        self.cache_token = cache_token

    def ensure_token(self) -> None:
        if token_valid(self.token):
            return
        if self.token.get("grant_type") == "client_credentials":
            self.token = request_client_credentials_token(self.client_id, self.client_secret)
            return
        self.token = refresh_access_token(self.token, self.client_id, self.client_secret)
        if self.cache_token:
            write_json(TOKEN_CACHE, self.token)

    def request(
        self,
        method: str,
        path_or_url: str,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        last_network_error: urllib.error.URLError | None = None
        for attempt in range(MAX_RATE_LIMIT_RETRIES):
            self.ensure_token()
            url = path_or_url if path_or_url.startswith("http") else f"{API_BASE}{path_or_url}"
            if params:
                query = urllib.parse.urlencode({k: v for k, v in params.items() if v is not None})
                url = f"{url}?{query}"
            request = urllib.request.Request(
                url,
                method=method,
                headers={"Authorization": f"Bearer {self.token['access_token']}"},
            )
            try:
                with urllib.request.urlopen(request, timeout=60) as response:
                    payload = response.read().decode("utf-8")
                    return json.loads(payload) if payload else {}
            except urllib.error.HTTPError as error:
                body = error.read().decode("utf-8", errors="replace")
                if error.code == 401 and self.token.get("refresh_token"):
                    self.token = refresh_access_token(self.token, self.client_id, self.client_secret)
                    if self.cache_token:
                        write_json(TOKEN_CACHE, self.token)
                    continue
                if error.code == 429:
                    retry_after = int(error.headers.get("Retry-After", "5"))
                    if retry_after > MAX_RETRY_AFTER_SECONDS:
                        raise SpotifyApiError(error.code, f"rate limited for {retry_after} seconds") from error
                    time.sleep(max(retry_after, 1) + 1)
                    continue
                raise SpotifyApiError(error.code, body) from error
            except (ConnectionError, TimeoutError, socket.timeout, urllib.error.URLError) as error:
                last_network_error = error
                time.sleep(min(2 + attempt * 2, 30))
                continue
        if last_network_error:
            reason = getattr(last_network_error, "reason", last_network_error)
            raise SpotifyApiError(0, str(reason)) from last_network_error
        raise SpotifyApiError(429, "rate limit retry budget exhausted")

    def paginate(
        self,
        path_or_url: str,
        params: dict[str, Any] | None = None,
    ) -> Iterable[dict[str, Any]]:
        next_url: str | None = path_or_url
        current_params = params
        while next_url:
            page = self.request("GET", next_url, current_params)
            yield from page.get("items", [])
            next_url = page.get("next")
            current_params = None


def split_semicolon(value: str) -> list[str]:
    return [part.strip() for part in value.split(";") if part.strip()]


def join_unique(values: Iterable[str]) -> str:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        cleaned = value.strip()
        key = cleaned.lower()
        if cleaned and key not in seen:
            seen.add(key)
            result.append(cleaned)
    return "; ".join(result)


def unique_values(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        cleaned = value.strip()
        if cleaned and cleaned not in seen:
            seen.add(cleaned)
            result.append(cleaned)
    return result


def chunked(values: list[str], size: int) -> Iterable[list[str]]:
    for index in range(0, len(values), size):
        yield values[index : index + size]


def read_manual_fields(path: Path) -> dict[str, dict[str, str]]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)
        rows: dict[str, dict[str, str]] = {}
        for row in reader:
            track_id = row.get("track_id", "").strip()
            if not track_id:
                continue
            rows[track_id] = {field: row.get(field, "") for field in MANUAL_FIELDS}
        return rows


def release_year(release_date: str) -> str:
    return release_date[:4] if len(release_date) >= 4 and release_date[:4].isdigit() else ""


def stable_local_id(track: dict[str, Any]) -> str:
    artists = ";".join(artist.get("name", "") for artist in track.get("artists", []))
    album = (track.get("album") or {}).get("name", "")
    raw = f"{artists}|{track.get('name', '')}|{album}"
    digest = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]
    return f"local:{digest}"


def normalize_track(
    item: dict[str, Any],
    source: str,
    playlist_name: str = "",
) -> dict[str, str] | None:
    track = item.get("track") or item.get("item") or item
    if not track or track.get("type") != "track":
        return None

    album = track.get("album") or {}
    artists = track.get("artists") or []
    release_date = album.get("release_date", "")
    artist_ids = [artist.get("id", "") for artist in artists if artist.get("id")]
    artist_names = [artist.get("name", "") for artist in artists if artist.get("name")]
    added_at = item.get("added_at", "")
    track_id = track.get("id") or stable_local_id(track)

    return {
        "track_id": track_id,
        "track_name": track.get("name", ""),
        "artist_names": join_unique(artist_names),
        "album_name": album.get("name", ""),
        "spotify_year": release_year(release_date),
        "year": "",
        "spotify_genres": "",
        "primary_genre": "",
        "genres": "",
        "release_date": release_date,
        "duration_ms": str(track.get("duration_ms") or ""),
        "explicit": str(track.get("explicit", "")),
        "popularity": str(track.get("popularity", "")),
        "spotify_url": (track.get("external_urls") or {}).get("spotify", ""),
        "album_id": album.get("id", ""),
        "artist_ids": join_unique(artist_ids),
        "track_number": str(track.get("track_number") or ""),
        "disc_number": str(track.get("disc_number") or ""),
        "sources": source,
        "playlist_names": playlist_name,
        "first_added_at": added_at,
        "latest_added_at": added_at,
        "rating": "",
        "status": "",
        "tags": "",
        "notes": "",
    }


def merge_track(existing: dict[str, str], incoming: dict[str, str]) -> dict[str, str]:
    merged = dict(existing)
    merged["sources"] = join_unique(split_semicolon(existing.get("sources", "")) + split_semicolon(incoming.get("sources", "")))
    merged["playlist_names"] = join_unique(
        split_semicolon(existing.get("playlist_names", "")) + split_semicolon(incoming.get("playlist_names", ""))
    )
    added_dates = [
        value
        for value in [existing.get("first_added_at", ""), incoming.get("first_added_at", "")]
        if value
    ]
    latest_dates = [
        value
        for value in [existing.get("latest_added_at", ""), incoming.get("latest_added_at", "")]
        if value
    ]
    merged["first_added_at"] = min(added_dates) if added_dates else ""
    merged["latest_added_at"] = max(latest_dates) if latest_dates else ""
    return merged


def fetch_saved_tracks(client: SpotifyClient, market: str | None) -> list[dict[str, str]]:
    tracks: list[dict[str, str]] = []
    params = {"limit": 50, "market": market}
    for item in client.paginate("/me/tracks", params):
        normalized = normalize_track(item, "liked")
        if normalized:
            tracks.append(normalized)
    return tracks


def fetch_saved_tracks_into(
    client: SpotifyClient,
    market: str | None,
    collected: dict[str, dict[str, str]],
    args: argparse.Namespace,
) -> None:
    params = {"limit": 50, "market": market}
    page = 0
    for item in client.paginate("/me/tracks", params):
        normalized = normalize_track(item, "liked")
        if normalized:
            collected[normalized["track_id"]] = normalized
        if len(collected) and len(collected) % 100 == 0:
            log_progress(args, f"Collected {len(collected)} unique tracks so far.")
        if args.limit and len(collected) >= args.limit:
            log_progress(args, f"Reached debug limit of {args.limit} tracks.")
            return
        page += 1
        if page == 1:
            log_progress(args, "Reading liked tracks.")


def fetch_current_user_playlists(client: SpotifyClient) -> list[dict[str, Any]]:
    return list(client.paginate("/me/playlists", {"limit": 50}))


def fetch_playlist_tracks(
    client: SpotifyClient,
    playlist_id: str,
    playlist_name: str,
    market: str | None,
) -> list[dict[str, str]]:
    tracks: list[dict[str, str]] = []
    params = {"limit": 50, "market": market, "additional_types": "track"}
    try:
        for item in client.paginate(f"/playlists/{playlist_id}/items", params):
            normalized = normalize_track(item, "playlist", playlist_name)
            if normalized:
                tracks.append(normalized)
    except SpotifyApiError as error:
        if error.status == 403:
            print(f"Skipping playlist {playlist_name or playlist_id}: Spotify returned 403.", file=sys.stderr)
            return []
        raise
    return tracks


def fetch_playlist_tracks_into(
    client: SpotifyClient,
    playlist_id: str,
    playlist_name: str,
    market: str | None,
    collected: dict[str, dict[str, str]],
    args: argparse.Namespace,
) -> None:
    params = {"limit": 50, "market": market, "additional_types": "track"}
    try:
        for item in client.paginate(f"/playlists/{playlist_id}/items", params):
            normalized = normalize_track(item, "playlist", playlist_name)
            if not normalized:
                continue
            existing = collected.get(normalized["track_id"])
            collected[normalized["track_id"]] = merge_track(existing, normalized) if existing else normalized
            if len(collected) and len(collected) % 100 == 0:
                log_progress(args, f"Collected {len(collected)} unique tracks so far.")
            if args.limit and len(collected) >= args.limit:
                log_progress(args, f"Reached debug limit of {args.limit} tracks.")
                return
    except SpotifyApiError as error:
        if error.status == 403:
            print(f"Skipping playlist {playlist_name or playlist_id}: Spotify returned 403.", file=sys.stderr)
            return
        raise


def cache_artist_response(
    artist_id: str,
    artist: dict[str, Any] | None,
    cache: dict[str, Any],
    source: str,
    fetched_at: int,
) -> None:
    if not artist:
        cache[artist_id] = {
            "genres": [],
            "genres_available": True,
            "fetched_at": fetched_at,
            "source": source,
        }
        return
    cache[artist_id] = {
        "genres": artist.get("genres", []) or [],
        "genres_available": "genres" in artist,
        "fetched_at": fetched_at,
        "source": source,
    }


def cache_missing_genres_field(
    artist_ids: Iterable[str],
    cache: dict[str, Any],
) -> None:
    fetched_at = int(time.time())
    for artist_id in artist_ids:
        cached = cache.get(artist_id) or {}
        cache[artist_id] = {
            **cached,
            "genres": cached.get("genres", []),
            "genres_available": False,
            "fetched_at": fetched_at,
            "source": "spotify_artist_unavailable",
        }


def fetch_artist_genres(client: SpotifyClient, artist_id: str, cache: dict[str, Any]) -> list[str]:
    if not artist_id:
        return []
    cached = cache.get(artist_id)
    if cached is not None and not artist_needs_fetch(artist_id, cache):
        return cached.get("genres", [])
    try:
        artist = client.request("GET", f"/artists/{artist_id}")
    except SpotifyApiError as error:
        if error.status == 404:
            artist = None
        else:
            raise
    cache_artist_response(artist_id, artist, cache, "spotify_artist", int(time.time()))
    return (cache.get(artist_id) or {}).get("genres", [])


def artist_needs_fetch(artist_id: str, cache: dict[str, Any]) -> bool:
    cached = cache.get(artist_id)
    if cached is None:
        return True
    if cached.get("genres"):
        return False
    if "genres_available" not in cached:
        return True
    if cached.get("genres_available") is False:
        return os.getenv("SPOTIFY_RETRY_MISSING_GENRES", "").strip() == "1"
    # Older exports could cache an empty genre list after a temporary 429 or 403.
    return cached.get("source") not in {"spotify_artist", "spotify_artists_batch"}


def fetch_artist_genre_batch(
    client: SpotifyClient,
    artist_ids: list[str],
    cache: dict[str, Any],
) -> None:
    if not artist_ids:
        return
    if len(artist_ids) == 1:
        fetch_artist_genres(client, artist_ids[0], cache)
        return
    try:
        response = client.request("GET", "/artists", {"ids": ",".join(artist_ids)})
    except SpotifyApiError as error:
        if error.status == 403 and len(artist_ids) > 1:
            for artist_id in artist_ids:
                fetch_artist_genres(client, artist_id, cache)
            return
        if error.status == 404:
            fetched_at = int(time.time())
            for artist_id in artist_ids:
                cache_artist_response(artist_id, None, cache, "spotify_artists_batch", fetched_at)
            return
        raise

    fetched_at = int(time.time())
    returned_ids: set[str] = set()
    for artist in response.get("artists", []) or []:
        if not artist:
            continue
        artist_id = artist.get("id", "")
        if not artist_id:
            continue
        returned_ids.add(artist_id)
        cache_artist_response(artist_id, artist, cache, "spotify_artists_batch", fetched_at)
    for artist_id in artist_ids:
        if artist_id not in returned_ids:
            cache_artist_response(artist_id, None, cache, "spotify_artists_batch", fetched_at)


def enrich_genres(
    client: SpotifyClient,
    tracks: dict[str, dict[str, str]],
    args: argparse.Namespace | None = None,
) -> None:
    cache = read_json(ARTIST_CACHE, {})
    total = len(tracks)
    artist_ids = unique_values(
        artist_id
        for row in tracks.values()
        for artist_id in split_semicolon(row.get("artist_ids", ""))
    )
    missing_artist_ids = [artist_id for artist_id in artist_ids if artist_needs_fetch(artist_id, cache)]
    total_missing = len(missing_artist_ids)
    if args:
        log_progress(
            args,
            f"Fetching Spotify genres for {total_missing}/{len(artist_ids)} artists.",
        )
    changed = bool(missing_artist_ids)
    fetched_count = 0
    genres_field_available: bool | None = None
    for batch in chunked(missing_artist_ids, ARTIST_BATCH_SIZE):
        fetch_artist_genre_batch(client, batch, cache)
        fetched_count += len(batch)
        if genres_field_available is None:
            checked = [cache.get(artist_id) or {} for artist_id in batch]
            if checked:
                genres_field_available = any("genres_available" not in item or item.get("genres_available") for item in checked)
                if not genres_field_available:
                    remaining_ids = missing_artist_ids[fetched_count:]
                    cache_missing_genres_field(remaining_ids, cache)
                    fetched_count = total_missing
                    if args:
                        log_progress(
                            args,
                            "Spotify artist responses do not include a genres field; skipping remaining artist genre requests.",
                        )
                    break
        if args:
            log_progress(args, f"Fetched Spotify genres for {fetched_count}/{total_missing} artists.")
        if fetched_count % (ARTIST_BATCH_SIZE * 10) == 0:
            write_json(ARTIST_CACHE, cache)

    for index, row in enumerate(tracks.values(), start=1):
        genres: list[str] = []
        for artist_id in split_semicolon(row.get("artist_ids", "")):
            genres.extend((cache.get(artist_id) or {}).get("genres", []))
        row["spotify_genres"] = join_unique(genres)
        if args and (index == 1 or index % 100 == 0 or index == total):
            log_progress(args, f"Enriched genres for {index}/{total} tracks.")
    unavailable = sum(1 for artist_id in artist_ids if (cache.get(artist_id) or {}).get("genres_available") is False)
    if args and unavailable:
        log_progress(
            args,
            f"Spotify artist responses did not include a genres field for {unavailable} artists.",
        )
    if changed:
        write_json(ARTIST_CACHE, cache)


def apply_manual_fields(
    tracks: dict[str, dict[str, str]],
    manual_rows: dict[str, dict[str, str]],
) -> None:
    for track_id, row in tracks.items():
        manual = manual_rows.get(track_id)
        if manual is None:
            row["year"] = row.get("spotify_year", "")
            row["genres"] = row.get("spotify_genres", "")
            row["primary_genre"] = split_semicolon(row.get("spotify_genres", ""))[0] if row.get("spotify_genres") else ""
            continue
        for field in MANUAL_FIELDS:
            row[field] = manual.get(field, "")


def write_tracks(path: Path, tracks: dict[str, dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = sorted(
        tracks.values(),
        key=lambda row: (
            row.get("artist_names", "").lower(),
            row.get("album_name", "").lower(),
            int(row.get("disc_number") or 0),
            int(row.get("track_number") or 0),
            row.get("track_name", "").lower(),
        ),
    )
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=FIELDNAMES)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in FIELDNAMES})


def main() -> None:
    args = parse_args()
    if args.verbose:
        log_file = resolve_path(args.log_file)
        log_file.parent.mkdir(parents=True, exist_ok=True)
        log_file.write_text("", encoding="utf-8")
        log_progress(args, "Starting Spotify export.")
    token = load_token(args)
    client = SpotifyClient(token, args.client_id, args.client_secret)
    manual_rows = read_manual_fields(args.output)

    collected: dict[str, dict[str, str]] = {}

    if not args.no_saved:
        log_progress(args, "Fetching liked tracks.")
        fetch_saved_tracks_into(client, args.market, collected, args)

    playlist_specs: list[tuple[str, str]] = []
    if args.limit and len(collected) >= args.limit:
        log_progress(args, "Skipping playlists because debug limit was reached.")
    elif args.playlist_id:
        playlist_specs.extend((playlist_id, playlist_id) for playlist_id in args.playlist_id)
    elif not args.no_playlists:
        log_progress(args, "Fetching current user profile and playlists.")
        profile = client.request("GET", "/me")
        current_user_id = profile.get("id", "")
        for playlist in fetch_current_user_playlists(client):
            owner_id = (playlist.get("owner") or {}).get("id", "")
            is_owned = bool(current_user_id and owner_id == current_user_id)
            is_collaborative = bool(playlist.get("collaborative"))
            if is_owned or is_collaborative:
                playlist_specs.append((playlist.get("id", ""), playlist.get("name", "")))
        log_progress(args, f"Found {len(playlist_specs)} owned/collaborative playlists.")

    for playlist_id, playlist_name in playlist_specs:
        if not playlist_id or (args.limit and len(collected) >= args.limit):
            continue
        log_progress(args, f"Fetching playlist: {playlist_name or playlist_id}.")
        fetch_playlist_tracks_into(client, playlist_id, playlist_name, args.market, collected, args)

    if args.skip_genres:
        log_progress(args, "Skipping genre enrichment.")
    else:
        log_progress(args, f"Enriching genres for {len(collected)} tracks.")
        genre_token = request_client_credentials_token(args.client_id, args.client_secret)
        genre_client = SpotifyClient(
            genre_token,
            args.client_id,
            args.client_secret,
            cache_token=False,
        )
        enrich_genres(genre_client, collected, args)
    apply_manual_fields(collected, manual_rows)
    log_progress(args, f"Writing {len(collected)} tracks to CSV.")
    write_tracks(args.output, collected)
    print(f"Wrote {len(collected)} tracks to {args.output}")


if __name__ == "__main__":
    main()

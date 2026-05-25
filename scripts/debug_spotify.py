#!/usr/bin/env python3
from __future__ import annotations

from export_spotify import (
    SpotifyClient,
    fetch_artist_genres,
    load_token,
    normalize_track,
    parse_args,
    read_json,
)


def main() -> None:
    args = parse_args()
    token = load_token(args)
    client = SpotifyClient(token, args.client_id, args.client_secret)

    profile = client.request("GET", "/me")
    print(f"user_id={profile.get('id', '')}", flush=True)
    print(f"display_name={profile.get('display_name', '')}", flush=True)

    saved_page = client.request("GET", "/me/tracks", {"limit": 5, "market": args.market})
    saved_items = saved_page.get("items", [])
    print(f"saved_tracks_first_page={len(saved_items)} total={saved_page.get('total', 'unknown')}", flush=True)

    first_track = None
    for item in saved_items:
        first_track = normalize_track(item, "liked")
        if first_track:
            break

    if first_track:
        print(f"first_track={first_track.get('track_name', '')} - {first_track.get('artist_names', '')}", flush=True)
        artist_id = (first_track.get("artist_ids", "").split(";") + [""])[0].strip()
        cache = read_json(args.log_file.parent / "debug-artists.json", {})
        genres = fetch_artist_genres(client, artist_id, cache) if artist_id else []
        print(f"first_artist_genres={'; '.join(genres) if genres else 'none'}", flush=True)

    playlist_page = client.request("GET", "/me/playlists", {"limit": 5})
    playlist_items = playlist_page.get("items", [])
    print(f"playlists_first_page={len(playlist_items)} total={playlist_page.get('total', 'unknown')}", flush=True)
    for playlist in playlist_items:
        owner = playlist.get("owner") or {}
        print(f"playlist={playlist.get('name', '')} owner={owner.get('id', '')}", flush=True)


if __name__ == "__main__":
    main()

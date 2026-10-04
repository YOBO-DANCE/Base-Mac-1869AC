import os
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

stderr_fd = sys.stderr.fileno()
devnull = os.open(os.devnull, os.O_WRONLY)
os.dup2(devnull, stderr_fd)
os.close(devnull)

import time
import vlc
import widgets
import songs_path
from import_system import append_folder_to_songs_path, get_playlists


def _is_playable(songs):
    return bool(songs) and any(os.path.isfile(s) for s in songs)


def _first_run_import():
    print(
        "It seems like there are no songs added. Please paste a folder path down below where all your music is located:")
    print("Folder path: ", end="", flush=True)
    user_directory = input().strip()
    print("Please provide a name for the playlist:")
    print("Playlist name: ", end="", flush=True)
    user_directory_name = input().strip()

    answer = append_folder_to_songs_path(user_directory, user_directory_name)
    if answer:
        print("Playlist saved! Please rerun the script to load your music.")
    else:
        print("Playlist not saved! Please rerun the script to retry")
    sys.exit()


playlists = get_playlists()
if not playlists:
    _first_run_import()

names = list(playlists)

print(" ")
print("         SELECT A PLAYLIST          ")
print(" ")

for index, name in enumerate(names):
    tag = "" if _is_playable(playlists[name]) else "  [missing]"
    print(f"{index}. {name} ({len(playlists[name])} songs){tag}")

print("Please enter the number of the playlist you want to play: ", flush=True)
choice = input().strip()

if not choice.isdigit() or int(choice) >= len(names):
    print("Invalid selection. Please rerun and pick a valid playlist number.")
    exit()

name_for_playlist = names[int(choice)]
playlist = playlists[name_for_playlist]

if not _is_playable(playlist):
    print(f"Playlist '{name_for_playlist}' has no files on this computer.")
    print("Import a folder on this PC instead.")
    sys.exit(1)


def _load_first_playable(songs):
    """(player, song_time, index) for the first loadable song, else (None, 0, -1)."""
    for index, path in enumerate(songs):
        player = vlc.MediaPlayer(path)
        player.play()
        for _ in range(100):
            if player.get_length() > 0:
                break
            if player.get_state() in (vlc.State.Error, vlc.State.Ended):
                break
            time.sleep(0.1)
        if player.get_length() > 0:
            return player, player.get_length() / 1000.0, index
        try:
            player.stop()
        except Exception:
            pass
    return None, 0, -1


player, length_of_song, current_song_index = _load_first_playable(playlist)
if player is None:
    print(f"Could not load any song from playlist '{name_for_playlist}'.")
    print("Import a folder on this PC instead.")
    sys.exit(1)
current_song = playlist[current_song_index]

current_song_name = os.path.basename(str(current_song).replace("\\", "/"))
widget = widgets.UiWidgets(current_song_name, player)

print("\033[3J\033[H\033[2J", end="", flush=True)

widget.loop_for_song(player, length_of_song, playlist, current_song_index)
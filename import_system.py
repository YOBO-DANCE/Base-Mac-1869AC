from pathlib import Path
import importlib
import songs_path


def get_playlists():
    """name -> song list, from dict storage plus any legacy bare lists."""
    found = {}
    data = getattr(songs_path, "playlists", None)
    if isinstance(data, dict):
        found.update({k: v for k, v in data.items() if isinstance(v, list)})
    for name, value in vars(songs_path).items():
        if not name.startswith("_") and isinstance(value, list) and name not in found:
            found[name] = value
    return found


def append_folder_to_songs_path(folder_path, playlist_name):

    importlib.reload(songs_path)
    if playlist_name in get_playlists():
        print("this name is already taken please and try something other")

        return False

    else:
        path = Path(folder_path).expanduser().resolve()
        if not path.is_dir():
            print(f"Error: Directory '{folder_path}' not found.")
            return False

        valid_exts = {'.mp3', '.wav', '.flac', '.m4a', '.ogg'}
        audio_files = [str(f) for f in path.rglob('*') if f.suffix.lower() in valid_exts]
        if not audio_files:
            print(f"No audio files found in '{folder_path}'.")
            return False

        python_code = f"\n# Auto-imported playlist from: {path}\nplaylists[{playlist_name!r}] = [\n"
        python_code += "".join(f"    {repr(audio)},\n" for audio in audio_files)
        python_code += "]\n"
        with open("songs_path.py", "a", encoding="utf-8") as f:
            f.write(python_code)
        print(f"Added {len(audio_files)} songs to songs_path.py as playlist '{playlist_name}'.")
        return True

import datetime
import importlib
import os
import random
import sys
import time
try:
    import select
except ImportError:
    select = None
try:
    import termios
    import tty
except ImportError:
    termios = None
    tty = None
if os.name == "nt":
    try:
        import msvcrt
    except ImportError:
        msvcrt = None
else:
    msvcrt = None

import vlc
from pygame import mixer

from import_system import append_folder_to_songs_path, get_playlists
from search_helper import search_help
import songs_path

IS_WIN = os.name == "nt"

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CLICK_SOUND_PATH = os.path.join(BASE_DIR, "turning_pages-ui-toggle-off-confirmation-608627.mp3")
BOX_INNER_WIDTH = 60
DIM = "\033[2m"
REV = "\033[7m"
RESET = "\033[0m"
LIST_BOX_WIDTH = 80

def _enable_vt():
    # ponytail: Win10+ only, turns on ANSI handling; no-op elsewhere
    if IS_WIN:
        os.system("")


def _song_name(path):
    # ponytail: normalize sep so basename works for mac (/) and win (\) paths
    return os.path.basename(str(path).replace("\\", "/"))


def truncate(text, max_width):
    return text if len(text) <= max_width else text[:max_width - 3] + "..."


def box_row(left, right=""):
    gap = BOX_INNER_WIDTH - len(left) - len(right)
    return "|" + left + " " * max(gap, 1) + right + "|"


class UiWidgets:

    def __init__(self, name_of_song, player):
        mixer.init()
        self.click_sound = mixer.Sound(CLICK_SOUND_PATH)
        self.song = name_of_song
        self.current_sec = 0
        self.current_min = 0
        self.new_timeline = "-" * 25

        # Spinning vinyl (original symbols)
        self.vinyl = ["◐", "◓", "◑", "◒"]
        self.current_vinyl = "◐"
        self.current_vinyl_frame = 0
        self.last_vinyl_time = time.monotonic()

        # Volume (original symbols)
        self.volume_level = 10
        self.volume_list = [" "] + ["■"] * 10 + [" "]
        player.audio_set_volume(100)

        # Modes (original symbols)
        self.play_pause = "⏸"
        self.line_list = ["-"] * 25
        self.shuffle = False
        self.shuffle_symbol = "⇉"
        self.shuffled_song_list = []
        self.loop_type = "auto"
        self.loop_type_symbol = "↬"

        self.previous_vol_lvl = 0
        self.mute_on_off = False
        self.old_settings = None

    def check_key_presses(self):
        if IS_WIN:
            if msvcrt is None or not msvcrt.kbhit():
                return None
            ch = msvcrt.getwch()
            if ch == '\x1b':
                for _ in range(15):
                    if msvcrt.kbhit():
                        break
                    time.sleep(0.002)
                if msvcrt.kbhit():
                    ch2 = msvcrt.getwch()
                    if ch2 == '[':
                        for _ in range(15):
                            if msvcrt.kbhit():
                                break
                            time.sleep(0.002)
                        if msvcrt.kbhit():
                            ch3 = msvcrt.getwch()
                            arrow = {"A": "UP", "B": "DOWN", "C": "RIGHT", "D": "LEFT",
                                     "a": "UP", "b": "DOWN", "c": "RIGHT", "d": "LEFT"}.get(ch3)
                            if arrow:
                                return arrow
                        return None

                    if ch2 in ("O", "o"):
                        for _ in range(15):
                            if msvcrt.kbhit():
                                break
                            time.sleep(0.002)
                        if msvcrt.kbhit():
                            ch3 = msvcrt.getwch()
                            arrow = {"A": "UP", "B": "DOWN", "C": "RIGHT", "D": "LEFT",
                                     "a": "UP", "b": "DOWN", "c": "RIGHT", "d": "LEFT"}.get(ch3)
                            if arrow:
                                return arrow
                        return None
                    arrow = {"A": "UP", "B": "DOWN", "C": "RIGHT", "D": "LEFT"}.get(ch2)
                    if arrow:
                        return arrow
                return "ESC"
            if ch in ("\x00", "\xe0"):
                ch2 = msvcrt.getwch()
                got = {'M': 'RIGHT', 'K': 'LEFT', 'H': 'UP', 'P': 'DOWN',
                       'm': 'RIGHT', 'k': 'LEFT', 'h': 'UP', 'p': 'DOWN'}.get(ch2)
                if got:
                    return got
                return None
            return ch.lower() if ch else None

        fd = sys.stdin.fileno()
        if not select.select([fd], [], [], 0)[0]:
            return None

        key = os.read(fd, 1).decode(errors="ignore")
        if key == "\x1b":
            seq = ""
            for _ in range(15):
                if select.select([fd], [], [], 0.002)[0]:
                    seq += os.read(fd, 1).decode(errors="ignore")
                    if len(seq) >= 2:
                        break

                    elif seq:
                        break
            if not seq:
                return "ESC"
                    
            got = {'[C': 'RIGHT', '[D': 'LEFT', 'OC': 'RIGHT', 'OD': 'LEFT',
                    '[A': 'UP', '[B': 'DOWN', 'OA': 'UP', 'OB': 'DOWN',
                    '[c': 'RIGHT', '[d': 'LEFT', 'oc': 'RIGHT', 'od': 'LEFT',
                    '[a': 'UP', '[b': 'DOWN', 'oa': 'UP', 'ob': 'DOWN'}.get(seq)
            if got:
                return got
            return None
        return key.lower() if key else None

    def loop_for_song(self, player, song_time, playlist, current_index):
        if IS_WIN:
            self.old_settings = None
            _enable_vt()
        else:
            self.old_settings = termios.tcgetattr(sys.stdin)
            tty.setcbreak(sys.stdin.fileno())
            termios.tcflush(sys.stdin, termios.TCIFLUSH)
        print("\033[?25l", end="")
        self.clear_screen()

        consecutive_errors = 0

        try:
            while True:
                self.now_real_time = datetime.datetime.now().strftime("%d %b %Y %I:%M %p")
                key = self.check_key_presses()

                if key:
                    if key in (' ', 'k'):
                        self.click_sound.play()
                        state = player.get_state()
                        if state == vlc.State.Paused:
                            player.set_pause(0)
                        elif state == vlc.State.Playing:
                            player.set_pause(1)
                        else:
                            player.play()

                    elif key in ('d', 'l', 'RIGHT'):
                        self.click_sound.play()
                        new_ms = min(max(player.get_time(), 0) + 10000, int(song_time * 1000))
                        player.set_time(new_ms)
                        self.sync_timeline(song_time, new_ms)

                    elif key in ('a', 'j', 'LEFT'):
                        self.click_sound.play()
                        new_ms = max(player.get_time() - 10000, 0)
                        player.set_time(new_ms)
                        self.sync_timeline(song_time, new_ms)

                    elif key == 'p':
                        if self.volume_level < 10:
                            self.click_sound.play()
                            self.set_volume(player, self.volume_level + 1)

                    elif key == 'o':
                        if self.volume_level > 0:
                            self.click_sound.play()
                            self.set_volume(player, self.volume_level - 1)

                    elif key == 's':
                        self.click_sound.play()
                        self.shuffle = not self.shuffle
                        self.shuffle_symbol = "⤭" if self.shuffle else "⇉"

                    elif key == 'e':
                        self.click_sound.play()
                        self.loop_type = "one" if self.loop_type == "auto" else "auto"
                        self.loop_type_symbol = "⥁" if self.loop_type == "one" else "↬"

                    elif key == 'm':
                        player, song_time, current_index = self.next_song(
                            player, playlist, current_index, self.shuffle)

                    elif key == 'n':
                        player, song_time, current_index = self.previous_song(
                            player, playlist, current_index, self.shuffle)

                    elif key == 'q':
                        self.click_sound.play()
                        self.play_pause = "▶"
                        self.render(song_time)
                        break

                    elif key == '0':
                        self.click_sound.play()
                        if self.mute_on_off:
                            self.set_volume(player, self.previous_vol_lvl)
                        elif self.volume_level > 0:
                            self.previous_vol_lvl = self.volume_level
                            self.set_volume(player, 0)
                            self.mute_on_off = True

                    elif key == 'c':
                        was_paused = player.get_state() == vlc.State.Paused
                        player.set_pause(1)
                        self.click_sound.play()
                        self.import_songs_prompt()
                        if not was_paused:
                            player.set_pause(0)

                    elif key == 'x':
                        was_paused = player.get_state() == vlc.State.Paused
                        player.set_pause(1)
                        self.click_sound.play()
                        old_player = player
                        player, song_time, playlist, current_index = self.select_playlist(
                            player, playlist, song_time, current_index)
                        if player is old_player and not was_paused:
                            player.set_pause(0)

                    elif key == 'z':
                        was_paused = player.get_state() == vlc.State.Paused
                        player.set_pause(1)
                        self.click_sound.play()
                        old_player = player
                        player, song_time, playlist, current_index = self.select_songs(
                            player, playlist, song_time, current_index)
                        if player is old_player and not was_paused:
                            player.set_pause(0)

                if song_time <= 1:
                    length = player.get_length()
                    if length > 0:
                        song_time = length / 1000

                state = player.get_state()
                self.play_pause = "▶" if state == vlc.State.Paused else "⏸"

                if player.is_playing():
                    consecutive_errors = 0
                    self.sync_timeline(song_time, max(0, player.get_time()))

                    now = time.monotonic()
                    if now - self.last_vinyl_time >= 0.3:
                        self.change_vinyl()
                        self.last_vinyl_time = now

                self.render(song_time)

                state = player.get_state()
                if state == vlc.State.Error:
                    consecutive_errors += 1
                    if consecutive_errors >= len(playlist):
                        self.clear_screen()
                        print("None of the songs in this playlist could be played.")
                        break
                    player, song_time, current_index = self.next_song(
                        player, playlist, current_index, self.shuffle)
                elif state == vlc.State.Ended:
                    if self.loop_type == "one":
                        player, song_time, current_index = self.loop(player, playlist, current_index)
                    else:
                        player, song_time, current_index = self.next_song(
                            player, playlist, current_index, self.shuffle)

                time.sleep(0.1)

        finally:
            try:
                player.stop()
            except Exception:
                pass
            if not IS_WIN and self.old_settings is not None:
                termios.tcsetattr(sys.stdin, termios.TCSANOW, self.old_settings)
            print("\033[?25h\n")

    def clear_screen(self):
        # ponytail: native cls on win (VT-independent); ANSI + scrollback wipe elsewhere
        if IS_WIN:
            os.system("cls")
        else:
            print("\033[3J\033[H\033[2J", end="", flush=True)

    def set_volume(self, player, level):
        self.volume_level = level
        self.mute_on_off = False
        self.update_volume_bar()
        player.audio_set_volume(level * 10)

    def sync_timeline(self, song_time, current_ms):
        current_sec = max(0, min(current_ms / 1000, song_time))
        self.current_min = int(current_sec // 60)
        self.current_sec = int(current_sec % 60)

        progress_ratio = current_sec / song_time if song_time > 0 else 0
        filled_units = int(progress_ratio * len(self.line_list))
        self.line_list = ["="] * filled_units + ["-"] * (len(self.line_list) - filled_units)
        self.new_timeline = "".join(self.line_list)

    def change_vinyl(self):
        self.current_vinyl_frame = (self.current_vinyl_frame + 1) % len(self.vinyl)
        self.current_vinyl = self.vinyl[self.current_vinyl_frame]

    def update_volume_bar(self):
        # ponytail: 12-slot field, left-aligned fills, padded space on both sides at any level
        self.volume_list = [" "] + ["■"] * self.volume_level + [" "] * (11 - self.volume_level)

    def _start_player(self, path):
        new_player = vlc.MediaPlayer(path)
        new_player.audio_set_volume(self.volume_level * 10)
        new_player.play()

        retries = 0
        while new_player.get_length() <= 0 and retries < 100:
            if new_player.get_state() in (vlc.State.Error, vlc.State.Ended):
                break
            time.sleep(0.1)
            retries += 1

        new_player.audio_set_volume(self.volume_level * 10)
        return new_player, max(new_player.get_length() / 1000, 1)

    def _dispose(self, player):
        try:
            player.stop()
            player.release()
        except Exception:
            pass

    def import_songs_prompt(self):
        self.disable_cbreak(self.old_settings)
        self.clear_screen()
        print("--- IMPORT PLAYLIST ---", flush=True)

        print("Please paste folder path where music is located: ")
        user_directory = input().strip()
        print("Please provide a name for the playlist: ")
        user_playlist_name = input().strip()

        if user_directory and user_playlist_name:
            append_folder_to_songs_path(user_directory, user_playlist_name)
        time.sleep(1.5)
        self.clear_screen()
        self.enable_cbreak()

    def select_playlist(self, player, playlist, song_time, current_index):
        self.disable_cbreak(self.old_settings)
        self.clear_screen()

        try:
            importlib.reload(songs_path)
        except Exception as e:
            print(f"Could not read songs_path.py: {e}")
            time.sleep(1.5)
            self.clear_screen()
            self.enable_cbreak()
            return player, song_time, playlist, current_index

        playlists = get_playlists()

        if not playlists:
            print("No playlists found. Press C to import one.")
            time.sleep(1.5)
            self.clear_screen()
            self.enable_cbreak()
            return player, song_time, playlist, current_index

        names = list(playlists)

        print("\n         SELECT A PLAYLIST          \n")
        for index, name in enumerate(names):
            tag = "" if any(os.path.isfile(s) for s in playlists[name]) else "  [missing]"
            print(f"{index}. {name}{tag}")

        print("Enter number: ", end="", flush=True)
        playlist_index = input().strip()

        if not playlist_index.isdigit() or int(playlist_index) >= len(names):
            print("Invalid selection. Returning to player...")
            time.sleep(1)
            self.clear_screen()
            self.enable_cbreak()
            return player, song_time, playlist, current_index

        new_playlist = playlists[names[int(playlist_index)]]
        if not new_playlist or not any(os.path.isfile(s) for s in new_playlist):
            print(f"Playlist '{names[int(playlist_index)]}' has no files on this computer.")
            time.sleep(1.5)
            self.clear_screen()
            self.enable_cbreak()
            return player, song_time, playlist, current_index

        self._dispose(player)
        self.shuffled_song_list.clear()

        current_song = new_playlist[0]

        new_player, new_song_time = self._start_player(current_song)
        self.reset(_song_name(current_song))

        self.clear_screen()
        self.enable_cbreak()

        return new_player, new_song_time, new_playlist, 0

    def select_songs(self, player, playlist, song_time, current_index):
        self.clear_screen()

        start = 0
        end = 10
        select_index = 0
        temp_select_list = [_song_name(s) for s in playlist]
        all_songs = list(enumerate(temp_select_list))
        query = ""
        searching = False
        filtered = all_songs
        select_index = 0
        start = 0
        end = min(10, len(filtered))
        needs_redraw = True
        caret_on = True
        last_blink = time.monotonic()

        def refilter():
            nonlocal filtered, select_index, start, end, needs_redraw, caret_on, last_blink
            filtered = search_help(query, all_songs)
            caret_on = True
            last_blink = time.monotonic()
            select_index = 0
            start = 0
            end = min(10, len(filtered))
            needs_redraw = True

        while True:
            total = len(filtered)
            start = max(0, min(start, max(0, total - 10)))
            end = min(start + 10, total)

            if searching and time.monotonic() - last_blink >= 0.5:
                caret_on = not caret_on
                last_blink = time.monotonic()
                needs_redraw = True

            if needs_redraw:
                out = "\033[H"
                border = "+" + "-" * LIST_BOX_WIDTH + "+"
                out += f"\033[2K\r{border}\n"
                if searching:
                    caret = "▌" if caret_on else " "
                    left = f" {query[-66:]}{caret}"
                    right = f"{total}/{len(all_songs)}"
                    max_left = LIST_BOX_WIDTH - len(right) - 1

                    if len(left) > max_left:
                        left = left[-max_left:]
                    gap = LIST_BOX_WIDTH - len(left) - len(right)
                    out += f"\033[2K\r {left}{" " * max(gap, 1)}{DIM}{right}{RESET} \n"

                else:
                    out += f"\033[2K\r {" Search: [press /]".ljust(LIST_BOX_WIDTH)[:LIST_BOX_WIDTH]} \n"

                if total == 0:
                    inner = f" No match found!".ljust(LIST_BOX_WIDTH)[:LIST_BOX_WIDTH]
                    out += f"\033[2K\r {inner} \n"

                for pos in range(start, end):
                    _i, name = filtered[pos]
                    inner = f"{pos + 1:>2}. {truncate(name, 68)}".ljust(LIST_BOX_WIDTH)[:LIST_BOX_WIDTH]

                    if pos == select_index:
                        out += f"\033[2K\r {REV}{inner}{RESET} \n"

                    else:
                        out += f"\033[2K\r {inner} \n"
                marks = ("▲" if start > 0 else "") + ("▼" if end < total else "")
                if searching:
                    ctl = "[Type] filter | [⌫] del | [Up/Down] move | [↩] select | [ESC] exit"
                else:
                    ctl = "[/] Search | [Up/N] Up | [Down/M] Down | [↩] Play | [Q] Back"
                if marks:
                    ctl = f"{ctl} {marks}"
                inner = (" " + truncate(ctl, LIST_BOX_WIDTH - 1)).ljust(LIST_BOX_WIDTH)[:LIST_BOX_WIDTH]
                out += f"\033[2K\r {DIM}{inner}{RESET} \n"
                out += f"\033[2K\r{border}\n"
                out += "\033[J"
                sys.stdout.write(out)
                sys.stdout.flush()
                needs_redraw = False

            keys = []
            for _ in range(5):
                k = self.check_key_presses()
                if k is None:
                    break
                keys.append(k)

            if not keys:
                time.sleep(0.01)
                continue

            quit_list = False
            for key in keys:
                total = len(filtered)
                if searching:

                    if key == "ESC":
                        self.click_sound.play()
                        searching = False
                        query = ""
                        filtered = all_songs
                        select_index, start = 0, 0
                        end = min(10, len(filtered))
                        needs_redraw = True
                        continue

                    if len(key) == 1 and ord(key) in (10, 13):
                        if filtered and select_index < len(filtered):
                            orig, name = filtered[select_index]
                            self._dispose(player)
                            self.click_sound.play()
                            new_player, new_song_time = self._start_player(playlist[orig])
                            self.reset(name)
                            self.clear_screen()
                            return new_player, new_song_time, playlist, orig
                        continue

                    if key in ("\x08", "\x7f"):
                        self.click_sound.play()
                        query = query[:-1]
                        refilter()
                        total = len(filtered)
                        continue

                    if key in ("UP", "DOWN"):
                        total = len(filtered)
                        if key == "DOWN" and select_index < total - 1:
                            select_index += 1
                            if select_index >= end:
                                start += 1
                                end += 1

                            needs_redraw = True
                            last_blink = time.monotonic()

                        elif key == "UP" and select_index > 0:
                            select_index -= 1
                            if select_index < start:
                                start -= 1
                                end -= 1

                            needs_redraw = True
                            last_blink = time.monotonic()
                        continue

                    if len(key) == 1 and 32 <= ord(key) <= 126:
                        self.click_sound.play()
                        query += key
                        refilter()
                        continue
                    continue

                if key == "q":
                    quit_list = True
                    break

                if key == "/":
                    self.click_sound.play()
                    searching = True
                    query = ""
                    caret_on = True
                    last_blink = time.monotonic()
                    filtered = all_songs
                    select_index, start = 0, 0
                    end = min(10, len(filtered))
                    needs_redraw = True
                    continue

                if key in ("m", "DOWN"):
                    total = len(filtered)
                    if select_index < total - 1:
                        select_index += 1
                        needs_redraw = True

                        if start < total - 10 and select_index > start:
                            start += 1
                            end += 1

                    continue

                if key in ("n", "UP"):
                    if select_index > 0:
                        select_index -= 1
                        needs_redraw = True
                        if select_index < start:
                            start -= 1
                            end -= 1
                
                    continue

                if len(key) == 1 and ord(key) in (10, 13):
                    if filtered and select_index < len(filtered):
                        orig, name = filtered[select_index]
                        self._dispose(player)
                        self.click_sound.play()
                        new_player, new_song_time = self._start_player(playlist[orig])
                        self.reset(name)
                        self.clear_screen()

                        return new_player, new_song_time, playlist, orig

                    continue

            if quit_list:
                break

        self.clear_screen()
        return player, song_time, playlist, current_index

    def render(self, song_time):
        total_min = int(song_time // 60)
        total_sec = int(song_time % 60)
        total_time_str = f"{total_min:02d}:{total_sec:02d}"
        curr_time_str = f"{self.current_min:02d}:{self.current_sec:02d}"

        display_name = truncate(self.song, 28)
        border = "+" + "-" * BOX_INNER_WIDTH + "+"

        lines = [
            border,
            box_row("  AUDIO DECK", f"{self.now_real_time}  "),
            box_row(f"  Track: {display_name}", f"Vinyl: [{self.current_vinyl}]  "),
            box_row(f"  [{self.new_timeline}]", f"{curr_time_str} / {total_time_str}  "),
            box_row(f"  Vol:   [{''.join(self.volume_list)}]  {self.volume_level * 10:>3}%",
                    f"Mode: [ {self.loop_type_symbol} {self.play_pause} {self.shuffle_symbol} ]  "),
            border,
            "   [Space] Play/Pause | [M] Next | [N] Prev | [X] List | [Q] Quit",
            "   [A/D] Seek | [O/P] Volume | [0] Mute | [S] Shuffle | [E] Repeat | [C] Import | [Z] Songs",
        ]

        out = "\033[H" + "".join(f"\033[2K\r{line}\n" for line in lines) + "\033[J"
        sys.stdout.write(out)
        sys.stdout.flush()

    def reset(self, song_name):
        self.clear_screen()
        self.song = song_name
        self.current_sec = 0
        self.current_min = 0
        self.new_timeline = "-" * 25
        self.line_list = ["-"] * 25
        self.play_pause = "⏸"
        self.last_vinyl_time = time.monotonic()

    def disable_cbreak(self, old_settings):
        if IS_WIN:
            print("\033[?25h", end="", flush=True)
            return
        termios.tcflush(sys.stdin, termios.TCIFLUSH)
        termios.tcsetattr(sys.stdin, termios.TCSANOW, old_settings)
        print("\033[?25h", end="", flush=True)

    def enable_cbreak(self):
        if IS_WIN:
            print("\033[?25l", end="", flush=True)
            return
        tty.setcbreak(sys.stdin.fileno())
        print("\033[?25l", end="", flush=True)
        termios.tcflush(sys.stdin, termios.TCIFLUSH)

    def next_song(self, player, playlist, current_index, shuffle):
        if shuffle:
            self.shuffled_song_list.append(current_index)
            del self.shuffled_song_list[:-200]
            next_index = random.randrange(len(playlist))
            while len(playlist) > 1 and next_index == current_index:
                next_index = random.randrange(len(playlist))
        else:
            next_index = (current_index + 1) % len(playlist)

        self._dispose(player)
        self.click_sound.play()

        next_song_path = playlist[next_index]
        new_player, new_song_time = self._start_player(next_song_path)
        self.reset(_song_name(next_song_path))
        return new_player, new_song_time, next_index

    def previous_song(self, player, playlist, current_index, shuffle):
        if shuffle and self.shuffled_song_list:
            previous_index = self.shuffled_song_list.pop() % len(playlist)
        else:
            previous_index = (current_index - 1) % len(playlist)

        self._dispose(player)
        self.click_sound.play()

        previous_song_path = playlist[previous_index]
        new_player, new_song_time = self._start_player(previous_song_path)
        self.reset(_song_name(previous_song_path))
        return new_player, new_song_time, previous_index

    def loop(self, player, playlist, current_index):
        self._dispose(player)
        self.click_sound.play()

        current_song_path = playlist[current_index]
        new_player, new_song_time = self._start_player(current_song_path)
        self.reset(_song_name(current_song_path))
        return new_player, new_song_time, current_index

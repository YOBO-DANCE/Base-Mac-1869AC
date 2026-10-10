"""Standalone select_songs + / live search lab. No music.

Run: python test.py
Box is 80 wide: Search bar top, 10 numbered rows, dim footer.
Out of search: [/] search, [Up/N] [Down/M] move, [Enter] play, [Q] back.
In search: type narrows live, [Backspace] widens, [UP/DOWN] move,
[Enter] select (plays original locker), [ESC] exit. All else dead.
Filter brain lives in search_helper.search_help.
"""
import os
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

from search_helper import search_help

IS_WIN = os.name == "nt"

BOX_INNER_WIDTH = 80
DIM = "\033[2m"
REV = "\033[7m"
RESET = "\033[0m"


def _enable_vt():
    # ponytail: Win10+ only, turns on ANSI handling; no-op elsewhere
    if IS_WIN:
        os.system("")


def truncate(text, max_width):
    return text if len(text) <= max_width else text[:max_width - 3] + "..."


def _song_name(path):
    return os.path.basename(str(path).replace("\\", "/"))


def check_key_presses():
    if IS_WIN:
        if msvcrt is None or not msvcrt.kbhit():
            return None
        ch = msvcrt.getwch()
        if ch == '\x1b':
            # ponytail: VT arrows (ESC [ A-D) share the ESC prefix; peek before calling it ESC
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
                        arrow = {'A': 'UP', 'B': 'DOWN', 'C': 'RIGHT', 'D': 'LEFT',
                                 'a': 'UP', 'b': 'DOWN', 'c': 'RIGHT', 'd': 'LEFT'}.get(ch3)
                        if arrow:
                            return arrow
                    return None
                if ch2 in ('O', 'o'):
                    for _ in range(15):
                        if msvcrt.kbhit():
                            break
                        time.sleep(0.002)
                    if msvcrt.kbhit():
                        ch3 = msvcrt.getwch()
                        arrow = {'A': 'UP', 'B': 'DOWN', 'C': 'RIGHT', 'D': 'LEFT',
                                 'a': 'UP', 'b': 'DOWN', 'c': 'RIGHT', 'd': 'LEFT'}.get(ch3)
                        if arrow:
                            return arrow
                    return None
                arrow = {'A': 'UP', 'B': 'DOWN', 'C': 'RIGHT', 'D': 'LEFT'}.get(ch2)
                if arrow:
                    return arrow
            return 'ESC'
        if ch in ('\x00', '\xe0'):
            # ponytail: byte-2 rides the same key event; blocking read can't split or wait
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
    if key == '\x1b':
        # ponytail: bytes can arrive split; accumulate with early break, never orphan a byte
        seq = ""
        for _ in range(15):
            if select.select([fd], [], [], 0.002)[0]:
                seq += os.read(fd, 1).decode(errors="ignore")
                if len(seq) >= 2:
                    break
            elif seq:
                break
        if not seq:
            return 'ESC'
        got = {'[C': 'RIGHT', '[D': 'LEFT', 'OC': 'RIGHT', 'OD': 'LEFT',
               '[A': 'UP', '[B': 'DOWN', 'OA': 'UP', 'OB': 'DOWN',
               '[c': 'RIGHT', '[d': 'LEFT', 'oc': 'RIGHT', 'od': 'LEFT',
               '[a': 'UP', '[b': 'DOWN', 'oa': 'UP', 'ob': 'DOWN'}.get(seq)
        if got:
            return got
        return None
    return key.lower() if key else None


def clear_screen():
    if IS_WIN:
        os.system("cls")
    else:
        print("\033[3J\033[H\033[2J", end="", flush=True)


def test_select_songs(playlist):
    old_settings = None
    if not IS_WIN:
        old_settings = termios.tcgetattr(sys.stdin)
        tty.setcbreak(sys.stdin.fileno())
    _enable_vt()
    print("\033[?25l", end="", flush=True)
    clear_screen()

    temp_select_list = [_song_name(s) for s in playlist]
    # [(index, "song_name"), ...]
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
        needs_redraw = True #end

    try:
        while True:
            total = len(filtered)
            start = max(0, min(start, max(0, total - 10)))
            end = min(start + 10, total)

            # ponytail: fake blink, redraw bar only while searching
            if searching and time.monotonic() - last_blink >= 0.5:
                caret_on = not caret_on
                last_blink = time.monotonic()
                needs_redraw = True

            if needs_redraw:
                out = "\033[H"
                border = "+" + "-" * BOX_INNER_WIDTH + "+"
                out += f"\033[2K\r{border}\n"
                if searching:
                    caret = "▌" if caret_on else " "
                    left = f" {query[-66:]}{caret}"
                    right = f"{total}/{len(all_songs)}"
                    max_left = BOX_INNER_WIDTH - len(right) - 1
                    if len(left) > max_left:
                        left = left[-max_left:]
                    gap = BOX_INNER_WIDTH - len(left) - len(right)
                    out += f"\033[2K\r {left}{' ' * max(gap, 1)}{DIM}{right}{RESET} \n"
                else:
                    out += f"\033[2K\r {' Search: [press /]'.ljust(BOX_INNER_WIDTH)[:BOX_INNER_WIDTH]} \n"
                if total == 0:
                    inner = "  No match".ljust(BOX_INNER_WIDTH)[:BOX_INNER_WIDTH]
                    out += f"\033[2K\r {inner} \n"
                for pos in range(start, end):
                    _i, name = filtered[pos]
                    inner = f"{pos + 1:>2}. {truncate(name, 68)}".ljust(BOX_INNER_WIDTH)[:BOX_INNER_WIDTH]
                    if pos == select_index:
                        out += f"\033[2K\r {REV}{inner}{RESET} \n"
                    else:
                        out += f"\033[2K\r {inner} \n"
                marks = ("▲" if start > 0 else "") + ("▼" if end < total else "")
                if searching:
                    ctl = "[Type] filter | [Bksp] del | [Up/Down] move | [Enter] select | [ESC] exit"
                else:
                    ctl = "[/] Search | [Up/N] Up | [Down/M] Down | [Enter] Play | [Q] Back"
                if marks:
                    ctl = f"{ctl} {marks}"
                inner = (" " + truncate(ctl, BOX_INNER_WIDTH - 1)).ljust(BOX_INNER_WIDTH)[:BOX_INNER_WIDTH]
                out += f"\033[2K\r {DIM}{inner}{RESET} \n"
                out += f"\033[2K\r{border}\n"
                out += "\033[J"
                sys.stdout.write(out)
                sys.stdout.flush()
                needs_redraw = False # end

            # ponytail: drain queued keys so hold-to-repeat glides; one redraw per frame
            keys = []
            for _ in range(5):
                k = check_key_presses()
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
                    # ponytail: only arrows/enter/esc act; other control keys dead so typing stays clean
                    if key == 'ESC':
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
                            clear_screen()
                            print(f"would play locker {orig}: {name}")
                            return orig
                        continue
                    if key in ('\x08', '\x7f'):
                        query = query[:-1]
                        refilter()
                        total = len(filtered)
                        continue
                    if key in ('UP', 'DOWN'):
                        total = len(filtered)
                        if key == 'DOWN' and select_index < total - 1:
                            select_index += 1
                            if select_index >= end:
                                start += 1
                                end += 1
                            needs_redraw = True
                            last_blink = time.monotonic()
                        elif key == 'UP' and select_index > 0:
                            select_index -= 1
                            if select_index < start:
                                start -= 1
                                end -= 1
                            needs_redraw = True
                            last_blink = time.monotonic()
                        continue
                    if key in ('LEFT', 'RIGHT'):
                        continue
                    if len(key) == 1 and 32 <= ord(key) <= 126:
                        query += key
                        refilter()
                        continue
                    continue

                if key == 'q':
                    quit_list = True
                    break
                if key == '/':
                    searching = True
                    query = ""
                    caret_on = True
                    last_blink = time.monotonic()
                    filtered = all_songs
                    select_index, start = 0, 0
                    end = min(10, len(filtered))
                    needs_redraw = True
                    continue
                if key in ('m', 'DOWN'):
                    total = len(filtered)
                    if select_index < total - 1:
                        select_index += 1
                        needs_redraw = True
                        if start < total - 10 and select_index > start:
                            start += 1
                            end += 1
                    continue
                if key in ('n', 'UP'):
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
                        clear_screen()
                        print(f"would play locker {orig}: {name}")
                        return orig
                    continue
            if quit_list:
                break

        clear_screen()
        return None
    finally:
        if not IS_WIN and old_settings is not None:
            termios.tcsetattr(sys.stdin, termios.TCSANOW, old_settings)
        print("\033[?25h\n", end="", flush=True)


if __name__ == "__main__":
    mock_playlist = ["Babydoll", "Hozier", "Love Me", "Summer Lovin'", "Nightcall",
                     "Bohemian Rhapsody", "Stairway to Heaven", "Hotel California",
                     "Sweet Child O Mine", "Smells Like Teen Spirit",
                     "Wonderwall", "Mr Brightside", "Take On Me", "Africa"]
    print(f"picked locker: {test_select_songs(mock_playlist)}")

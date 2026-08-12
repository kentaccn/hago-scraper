"""Sweep every eHealth 化驗紀錄 report for one year into the iCloud pipe folder.

Resumable: keeps a JSON ledger of (name, date) pairs already exported, so a
crashed or interrupted run can just be re-invoked. Set YEAR in the environment.
"""
import json
import os
import re
from pathlib import Path

from phone_harness.helpers import screen_info, tap, scroll_screen

YEAR = os.environ.get("YEAR", "2026")
LEDGER = Path.home() / "lab_done.json"
FAST = 0.35        # scroll settle; the 2.5s default makes a sweep take hours
MAX_DEPTH = 8
DATE = re.compile(r"\d{4}年\d{2}月\d{2}日")
# OCR picks up chrome and the account name as if they were rows.
# The signed-in account name appears in the header and OCRs as if it were a
# row. Supply it via the environment rather than hard-coding it -- this file is
# public, the patient's name is not.
ACCOUNT = os.environ.get("HA_ACCOUNT_NAME", "")
NOISE = tuple(x for x in ("主頁", "oHcalth", "eHealth", ACCOUNT, "選擇年份", "化驗紀錄",
         "Health", "醫健通") if x)

done = set(json.loads(LEDGER.read_text())) if LEDGER.exists() else set()
FAILS = Path.home() / "lab_fails.json"
fails = json.loads(FAILS.read_text()) if FAILS.exists() else {}


def save_fails():
    FAILS.write_text(json.dumps(fails, ensure_ascii=False))


def save_ledger():
    LEDGER.write_text(json.dumps(sorted(done), ensure_ascii=False))


def back():
    w = screen_info()["window"]
    tap(w["x"] + 31, w["y"] + 0.14 * w["h"])
    wait_stable()
    wait(1.2)


def confirm():
    if find_zh("確認", exact=True):
        tap_zh("確認", exact=True)
        wait_stable()
        wait(2)


def to_list():
    for _ in range(5):
        if find_zh("選擇年份", exact=True):
            return True
        back()
    return bool(find_zh("選擇年份", exact=True))


def rows():
    """[(y, name, date)] — a record is <name> directly above <hospital>/<date>."""
    obs = sorted(ocr_zh(), key=lambda o: o["y"])
    out = []
    for i, o in enumerate(obs):
        # Vision garbles 醫 constantly (盤院 / 馨院 / 髷院 / 齧院), and a row the
        # parser cannot see makes the sweeper declare the year finished. 院
        # survives; the date check below is what really validates the row.
        if "院" not in o["text"] or i == 0 or i + 1 >= len(obs):
            continue
        name = obs[i - 1]["text"].strip().lstrip("◎•· ").strip()
        date = obs[i + 1]["text"].strip()
        if not DATE.fullmatch(date):
            continue
        if not name or any(n in name for n in NOISE):
            continue
        out.append((obs[i - 1]["y"], name, date))
    return sorted(out)


def hard_reset():
    """Home -> relaunch eHealth. The only recovery that always works when the
    app ends up somewhere the back button can't climb out of."""
    home()
    wait(2)
    open_app("eHealth")
    wait(7)


def _reveal(label, tries=8):
    """The 常用功能 grid scrolls — 檢查 is often below the fold."""
    for _ in range(tries):
        if find_zh(label, exact=True):
            return True
        if not scroll_screen("up", settle=FAST)["moved"]:
            break
    for _ in range(tries):                  # try upward too
        if find_zh(label, exact=True):
            return True
        scroll_screen("down", settle=FAST)
    return bool(find_zh(label, exact=True))


def _walk_to_lab():
    confirm()
    for step in ("常用功能", "檢查", "化驗紀錄"):
        for _ in range(2):
            if find_zh("選擇年份", exact=True):
                return True
            if _reveal(step):
                wait_stable()
                tap_zh(step, exact=True)
                wait_stable()
                wait(2.5)
    return bool(find_zh("選擇年份", exact=True))


def goto_lab():
    """Get to 化驗紀錄 from wherever the app happens to be."""
    # A pending 確認 privacy modal swallows every back-tap, so clear it first
    # or navigation can never recover from a half-opened record.
    confirm()
    if find_zh("選擇年份", exact=True):
        return True
    for _ in range(6):                     # climb out of any detail view
        if find_zh("常用功能", exact=True) or find_zh("檢查", exact=True):
            break
        back()
    if _walk_to_lab():
        return True
    hard_reset()                            # last resort, always works
    return _walk_to_lab()


def pick_year(y):
    if not goto_lab():
        return False
    if not to_list():
        return False
    tap_zh("選擇年份", exact=True)
    wait_stable()
    wait(1.5)
    h = find_zh(y, exact=True)
    if not h:
        back()
        return False
    tap(h[-1]["x"], h[-1]["y"])
    wait_stable()
    wait(2.5)
    return True


def export(y_pos):
    """Open the row at y_pos, drill to its PDF, save it, come back to the list."""
    tap(screen_info()["window"]["x"] + 120, y_pos)
    wait_stable()
    wait(1.5)
    confirm()
    if not find_zh("報告", exact=True):
        goto_lab()
        return "no 報告"
    tap_zh("報告", exact=True)
    wait_stable()
    wait(2)
    confirm()
    tap_header_right()
    wait(2.5)
    if not find_zh("Save to Files", exact=True):
        goto_lab()
        return "no share"
    files_save_to("HAGO")
    goto_lab()
    return "ok"


if not pick_year(YEAR):
    print(f"{YEAR}: cannot select year")
    raise SystemExit

MAX_DEPTH = 8
FAST = 0.35        # scrolling settle; the default 2.5s makes a sweep take hours


def rewind():
    # Fixed count, not moved-based: rows repeat the same test names across
    # dates, so the overlap heuristic reports "didn't move" when it did.
    for _ in range(MAX_DEPTH + 2):
        scroll_screen("down", settle=FAST)


def undone_at(depth):
    """Rewind, scroll `depth` steps, return the first not-yet-exported row."""
    rewind()
    for _ in range(depth):
        scroll_screen("up", settle=FAST)
    for y_pos, name, date in rows():
        key = f"{date}|{name}"
        if key not in done:
            return (y_pos, key), False
    return None, False


saved = skipped = 0
progressed = True
while progressed:
    progressed = False
    if not pick_year(YEAR):
        print(f"{YEAR}: lost the list, stopping")
        break
    # Navigating away resets the list to the top, so depth is re-walked each
    # time rather than carried — O(n^2) scrolling, but it never loses its place.
    for depth in range(0, MAX_DEPTH):
        hit, at_end = undone_at(depth)
        if at_end:
            break
        if not hit:
            continue
        y_pos, key = hit
        try:
            r = export(y_pos)
        except Exception as e:
            print(f"  FAIL {key}: {str(e)[:60]}")
            goto_lab()
            r = "error"
        # Only a real export earns a ledger entry -- marking a failed record
        # done retires it forever and it silently never gets exported. But a
        # record that fails every time would loop, so give up after 3 tries.
        if r == "ok":
            done.add(key)
        else:
            fails[key] = fails.get(key, 0) + 1
            if fails[key] >= 3:
                print(f"  GIVING UP on {key} after {fails[key]} tries")
                done.add(key)
            save_fails()
        save_ledger()
        saved += 1 if r == "ok" else 0
        skipped += 0 if r == "ok" else 1
        print(f"  {r:9} {key}")
        progressed = True
        break

print(f"{YEAR}: saved {saved}, skipped {skipped}, ledger {len(done)}")

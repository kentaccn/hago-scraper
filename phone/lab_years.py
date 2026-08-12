"""Probe: reach 化驗紀錄 and list the years the filter offers."""
from phone_harness.helpers import screen_info, tap, scroll_screen
FAST = 0.35

def back():
    w = screen_info()["window"]
    tap(w["x"] + 31, w["y"] + 0.14 * w["h"]); wait_stable(); wait(1.2)

def confirm():
    if find_zh("確認", exact=True):
        tap_zh("確認", exact=True); wait_stable(); wait(2)

def _reveal(label, tries=8):
    for _ in range(tries):
        if find_zh(label, exact=True):
            return True
        scroll_screen("up", settle=FAST)
    for _ in range(tries):
        if find_zh(label, exact=True):
            return True
        scroll_screen("down", settle=FAST)
    return bool(find_zh(label, exact=True))

def walk():
    confirm()
    for step in ("常用功能", "檢查", "化驗紀錄"):
        for _ in range(3):
            if find_zh("選擇年份", exact=True):
                return True
            if _reveal(step):
                wait_stable(); tap_zh(step, exact=True); wait_stable(); wait(2.5)
    return bool(find_zh("選擇年份", exact=True))

confirm()
if not walk():
    home(); wait(2); open_app("eHealth"); wait(8)
    walk()
print("at list:", bool(find_zh("選擇年份", exact=True)))
if find_zh("選擇年份", exact=True):
    tap_zh("選擇年份", exact=True); wait_stable(); wait(2)
    print("YEARS:", sorted({o["text"] for o in ocr_zh() if o["text"].strip().isdigit() and len(o["text"].strip()) == 4}))
    print("screen:", [o["text"] for o in ocr_zh()][:25])

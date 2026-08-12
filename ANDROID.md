# Android — notes for a port

**Short version: Android should be easier than iOS, and probably more reliable.
Nobody has built it yet.** This is a design note, not working code. It is
written down because the hard part of the iOS path — reading the screen — mostly
disappears on Android.

Both apps exist on Android: HA Go is `hk.org.ha.hago` (Android 7+), and 醫健通
eHealth ships an Android build too.

## Why it should be better

The iOS path works by screenshotting the iPhone Mirroring window and running
Vision OCR over it. That is where nearly every bug in this project came from —
`醫` garbling into 盤 / 馨 / 髷 / 齧 made whole rows invisible and silently cost
37 records.

Android hands you the actual view hierarchy:

```bash
adb shell uiautomator dump /sdcard/ui.xml
adb pull /sdcard/ui.xml
```

That XML contains every visible node with its `text`, `resource-id`,
`content-desc` and exact `bounds`. **No OCR, no garbling, no fuzzy matching, no
「院」 workaround.** Row detection becomes an XPath query instead of a heuristic,
and the "did the list actually scroll" problem becomes checking whether the node
set changed.

The rest of the toolkit:

| Need | iOS today | Android |
|---|---|---|
| See the screen | screenshot + Vision OCR | `uiautomator dump` — real text and bounds |
| Tap | synthesised CGEvent at a point | `adb shell input tap X Y` |
| Scroll | wheel events into the mirror window | `adb shell input swipe X1 Y1 X2 Y2 300` |
| Type | keycode injection, **cannot type CJK** | `adb shell input text` (still ASCII-only), or ADBKeyBoard for Unicode |
| Get files off | iCloud Drive as a pipe, then delete the cloud copy | `adb pull /sdcard/Download/...` — direct, no cloud involved |
| Host OS | macOS only | Linux, Windows or macOS |

Getting the PDFs off is the other big win. The iOS route has to launder every
file through iCloud because AirDrop fails; on Android the file lands in
`Download/` and `adb pull` takes it straight to disk. **No third-party cloud
ever touches the records.**

## Check these two things before writing any code

Everything above is worthless if either of these fails. Both take ten minutes.

**1. Does the app set `FLAG_SECURE`?** Apps handling financial or medical data
often block screen capture, and Android enforces it at the window level. If it
is set, `screencap` returns black and `uiautomator dump` may refuse.

```bash
adb shell am start -n hk.org.ha.hago/.MainActivity   # or just open it by hand
adb exec-out screencap -p > test.png                 # black image => FLAG_SECURE
adb shell uiautomator dump /sdcard/ui.xml && adb pull /sdcard/ui.xml
adb shell dumpsys window | grep -i "FLAG_SECURE"
```

Behaviour varies by device and Android version — some return black, some
scramble, some allow it. Test on the actual handset.

**2. Does the Android app expose the same export?** The iOS flow depends on a
share button inside each report that offers "Save to Files". If the Android
build only renders reports inline, or only offers "share to app", the export
step needs a different approach — and that, not the automation, is the real
blocker.

If `FLAG_SECURE` blocks capture, `uiautomator dump` may still work (it reads the
accessibility tree, not pixels). That would be enough: this tool never needs to
*see* the screen, only to find and tap rows.

## What can be reused unchanged

Only `phone/` is iOS-specific. Everything downstream is plain Python over PDFs:

- `parse/organise_hago.py`, `parse/extract_labs.py`
- all of `analyse/`

So a port means writing `phone/android/` with the same shape as the existing
sweepers — a resumable ledger, one record at a time, two dry runs to call a year
finished — and nothing else changes.

## Suggested shape

Keep the proven structure and swap only the eyes and hands:

```
phone/android/
  adb.py           dump() -> parsed nodes, tap(node), swipe(), pull()
  lab_sweep.py     same ledger + dry-run logic as the iOS version
  sweep_year.sh    same driver
```

Two lessons from the iOS build that still apply:

- **Only a successful export earns a ledger entry.** Marking a failure done
  retires that record forever.
- **One sweep at a time.** Concurrency broke the iOS version repeatedly, and adb
  will serialise no better.

Two that stop applying:

- No OCR noise filtering, so `HA_ACCOUNT_NAME` becomes unnecessary.
- No iCloud pipe, so no cloud cleanup step.

## Contributions

If you try this, the single most useful thing you can report back is the answer
to the two checks above — whether `FLAG_SECURE` is set, and whether the Android
app still offers a per-report export. Everything else follows from that.

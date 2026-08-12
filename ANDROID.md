# Android port notes

There is no Android implementation. These are notes for someone who wants to
write one.

Both apps exist on Android: HA Go is `hk.org.ha.hago` (Android 7+), and 醫健通
eHealth ships an Android build.

## Why it may be easier than iOS

The iOS path screenshots the iPhone Mirroring window and runs Vision OCR over
it. Most of the bugs in this project came from that. `醫` garbling into 盤, 馨,
髷 or 齧 made whole rows invisible and cost 37 records before anyone noticed.

Android can return the view hierarchy instead:

```bash
adb shell uiautomator dump /sdcard/ui.xml
adb pull /sdcard/ui.xml
```

The XML gives each visible node with its `text`, `resource-id`, `content-desc`
and `bounds`, so row detection becomes a query rather than a heuristic. Whether
every element this tool needs is actually exposed has not been tested.

| Need | iOS today | Android |
|---|---|---|
| Read the screen | screenshot plus Vision OCR | `uiautomator dump` |
| Tap | synthesised CGEvent | `adb shell input tap X Y` |
| Scroll | wheel events into the mirror window | `adb shell input swipe` |
| Type | keycode injection, no CJK | `adb shell input text`, or ADBKeyBoard for Unicode |
| Get files off | iCloud Drive, then delete the copy | `adb pull` if the app writes to `Download/` |
| Host OS | macOS only | Linux, Windows or macOS |

## Check these two things first

Run `uiautomator dump` with a report list open. Confirm the rows carry usable
text or resource IDs, and check whether `FLAG_SECURE` blocks the dump or
screenshots. Apps handling medical or financial data often set it, and the
behaviour varies by device and Android version: some return black, some
scramble, some allow it.

```bash
adb exec-out screencap -p > test.png          # black image means FLAG_SECURE
adb shell uiautomator dump /sdcard/ui.xml
adb shell dumpsys window | grep -i FLAG_SECURE
```

If `FLAG_SECURE` blocks pixels, `uiautomator dump` may still work, since it
reads the accessibility tree. That would be enough. This tool never needs to see
the screen, only to find and tap rows.

Then open a report and check how it can be exported. If it saves a PDF to
`Download/`, `adb pull` takes it straight to disk. If the app only renders the
report internally, that is the real blocker and needs a different approach.

## What carries over

Only `phone/` is iOS-specific. `parse/` and `analyse/` are plain Python over
PDFs and need no changes.

A port means writing `phone/android/` with the same shape as the existing
sweepers: a resumable ledger, one record at a time, two dry runs before calling
a year finished.

```
phone/android/
  adb.py           dump() -> parsed nodes, tap(node), swipe(), pull()
  lab_sweep.py     same ledger and dry-run logic
  sweep_year.sh    same driver
```

Porting notes: only a successful export earns a ledger entry, and run one sweep
at a time. `HA_ACCOUNT_NAME` becomes unnecessary without OCR, and there is no
iCloud cleanup step if files come off with `adb pull`.

If you try this, report back whether `FLAG_SECURE` is set and whether the
Android app still offers a per-report export.

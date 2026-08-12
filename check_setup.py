"""Preflight check — run this before anything else.

Reports what is present, what is missing, and what is only needed for part of
the pipeline, so a missing optional dependency does not look like a failure.

    python3 check_setup.py
"""
import importlib
import os
import platform
import shutil
import stat
import subprocess
import sys
import urllib.request
from pathlib import Path

# Load ~/.hago-scraper.env so every stage sees the same paths. Without this
# only the shell wrappers read it, and one stage writes where the next never
# looks.
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import config                              # noqa: E402
config.load()

OK, WARN, BAD = "  ok  ", " note ", " MISS "
problems = 0
notes = 0


def line(state, what, detail=""):
    global problems, notes
    if state is BAD:
        problems += 1
    if state is WARN:
        notes += 1
    print(f"[{state}] {what}" + (f" — {detail}" if detail else ""))


def have(cmd):
    return shutil.which(cmd) is not None


print("\n== core ==")
v = sys.version_info
line(OK if v >= (3, 9) else BAD, f"python {v.major}.{v.minor}.{v.micro}",
     "" if v >= (3, 9) else "3.9+ required")
line(OK if have("pdftotext") else BAD, "pdftotext (poppler)",
     "" if have("pdftotext") else "brew install poppler")

for mod, why, hard in (("numpy", "vector search, statistics", True),
                       ("scipy", "trend tests in stats_tests.py", False),
                       ("matplotlib", "charts in analyse.py", False)):
    try:
        m = importlib.import_module(mod)
        line(OK, f"{mod} {getattr(m, '__version__', '')}", why)
    except ImportError:
        line(BAD if hard else WARN, mod, f"{why} — pip3 install {mod}")

try:
    import sqlite3
    con = sqlite3.connect(":memory:")
    con.execute("CREATE VIRTUAL TABLE t USING fts5(a)")
    line(OK, f"sqlite {sqlite3.sqlite_version}", "FTS5 available")
except Exception as e:                                           # noqa: BLE001
    line(BAD, "sqlite FTS5", f"keyword search will not work: {e}")

print("\n== phone control (only needed to export from the phone) ==")
if platform.system() != "Darwin":
    line(WARN, "macOS", "phone export needs macOS; parsing and analysis work anywhere")
else:
    mac_ok = have("phone-harness") or (Path.home() / ".phone-harness").exists()
    line(OK if mac_ok else WARN, "phone-harness",
         "" if mac_ok else "github.com/ShawnPana/phone-harness")
    mirroring = Path("/System/Applications/iPhone Mirroring.app").exists()
    line(OK if mirroring else WARN, "iPhone Mirroring app",
         "" if mirroring else "macOS Sequoia or later")
    if os.environ.get("TMUX"):
        line(WARN, "running under tmux",
             "a tmux server started from ssh loses Screen Recording; "
             "screen capture will fail")

print("\n== configuration ==")
env = Path.home() / ".hago-scraper.env"
if env.exists():
    mode = stat.S_IMODE(env.stat().st_mode)
    line(OK if mode == 0o600 else WARN, str(env),
         "" if mode == 0o600 else f"mode {oct(mode)} — chmod 600 it")
else:
    line(WARN, str(env), "copy .env.example there and fill it in")

for var, why, hard in (("HAGO_DIR", "where renamed PDFs live", True),
                       ("MEDICAL_DB", "where the database is written", True),
                       ("HA_ACCOUNT_NAME", "filtered out of OCR rows", False),
                       ("DOB_YEAR", "so a DOB is never read as a collect date",
                        False)):
    val = os.environ.get(var)
    line(OK if val else (BAD if hard else WARN), var,
         val or f"unset — {why}")

for var in ("HAGO_DIR", "MEDICAL_DB"):
    val = os.environ.get(var)
    if not val:
        continue
    p = Path(val).expanduser()
    target = p if p.is_dir() else p.parent
    if target.exists():
        mode = stat.S_IMODE(target.stat().st_mode)
        # test the group/other bits, not the numeric value: 0o677 is NOT safer
        # than 0o700 even though it compares smaller
        leaky = mode & 0o077
        line(OK if not leaky else WARN, f"permissions on {target}",
             "" if not leaky else
             f"mode {oct(mode)} is readable by others — chmod 700 {target}")

out = os.environ.get("MEDICAL_OUT")
repo = Path(__file__).resolve().parent
target = Path(out).expanduser() if out else None
if target is None and os.environ.get("MEDICAL_DB"):
    target = Path(os.environ["MEDICAL_DB"]).expanduser().parent
if target:
    inside = repo == target or repo in target.parents
    line(WARN if inside else OK, "generated reports go outside the checkout",
         f"{target} is inside the repo — set MEDICAL_OUT" if inside else str(target))

print("\n== optional: local embeddings ==")
host = os.environ.get("OLLAMA", "http://localhost:11434")
model = os.environ.get("EMBED_MODEL", "nomic-embed-text")
try:
    with urllib.request.urlopen(f"{host}/api/tags", timeout=5) as r:
        import json
        names = [m["name"] for m in json.load(r).get("models", [])]
    if any(model in n for n in names):
        line(OK, f"ollama at {host}", f"{model} present")
    else:
        line(WARN, f"ollama at {host}", f"pull it: ollama pull {model}")
except Exception:                                                # noqa: BLE001
    line(WARN, f"ollama at {host}",
         "unreachable — semantic search is optional; everything else works")

print("\n== serving ==")
mode = os.environ.get("BIND_MODE", "tailscale")
line(OK, f"BIND_MODE={mode}",
     {"tailscale": "tailnet only — private by construction",
      "localhost": "loopback only — put a tunnel or proxy in front",
      "lan": "reachable by everyone on your network",
      "any": "every interface — set AUTH_TOKEN"}.get(mode, "custom"))
if mode in ("lan", "any") and not os.environ.get("AUTH_TOKEN"):
    line(WARN, "AUTH_TOKEN unset",
         "strongly recommended when listening beyond loopback/tailnet")

print()
if problems:
    print(f"{problems} blocking problem(s), {notes} note(s).")
    sys.exit(1)
print(f"Ready. {notes} note(s) — optional pieces only." if notes else "Ready.")

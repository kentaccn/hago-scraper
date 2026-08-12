"""Load ~/.hago-scraper.env so every entry point sees the same configuration.

The README tells you to put your settings in one file. Without this, only the
shell wrappers ever read it and the Python stages silently fall back to
defaults — which is how one stage ends up writing where the next never looks.

Import this first, before reading os.environ:

    import config; config.load()
"""
import os
import re
import shlex
from pathlib import Path

ENV_FILE = Path(os.environ.get("HAGO_ENV",
                               Path.home() / ".hago-scraper.env"))
_LINE = re.compile(r"^\s*(?:export\s+)?([A-Z_][A-Z0-9_]*)\s*=\s*(.*)$")
_loaded = False


def load(path=None):
    """Read the env file into os.environ. Real environment variables win, so
    `FOO=bar python3 x.py` still overrides the file."""
    global _loaded
    p = Path(path) if path else ENV_FILE
    if _loaded and path is None:
        return
    _loaded = True
    if not p.exists():
        return
    for raw in p.read_text().splitlines():
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        m = _LINE.match(raw)
        if not m:
            continue
        key, val = m.group(1), m.group(2).strip()
        if key in os.environ:            # explicit environment beats the file
            continue
        try:
            parts = shlex.split(val, comments=True)
        except ValueError:
            parts = [val]
        val = parts[0] if parts else ""
        os.environ[key] = os.path.expandvars(os.path.expanduser(val))


def records_dir():
    """Where the renamed PDFs live."""
    return Path(os.environ.get("HAGO_DIR", Path.home() / "records")).expanduser()


def database():
    """Where the SQLite file lives."""
    return Path(os.environ.get("MEDICAL_DB",
                               records_dir() / "medical.db")).expanduser()


def output_dir():
    """Where generated reports and charts go.

    Defaults beside the database, deliberately NOT inside the checkout: a
    report and its charts are medical data, and generating them into a git
    working tree is how they end up in a commit.
    """
    d = Path(os.environ.get("MEDICAL_OUT", database().parent)).expanduser()
    d.mkdir(parents=True, exist_ok=True)
    try:
        d.chmod(0o700)
    except OSError:
        pass
    return d


def secure(path):
    """chmod 600 a generated file, ignoring platforms that cannot."""
    try:
        Path(path).chmod(0o600)
    except OSError:
        pass
    return path

"""Rename HA GO exports to <YYYY-MM-DD>_<type>_<site>.pdf using each PDF's own text."""
import re, sys, os, hashlib, subprocess
from pathlib import Path

# Load ~/.hago-scraper.env so every stage sees the same paths. Without this
# only the shell wrappers read it, and one stage writes where the next never
# looks.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import config                              # noqa: E402
config.load()

# Default source is the iCloud pipe folder; pass a directory to take exports
# from somewhere else (e.g. copied straight off the Mini over Tailscale).
SRC = Path(next((a for a in sys.argv[1:] if not a.startswith("-")),
                os.environ.get("INCOMING_DIR",
                               Path.home() / "Library/Mobile Documents/"
                                             "com~apple~CloudDocs/HAGO")))
DST = Path(os.environ.get("HAGO_DIR",
                          Path.home() / "repo/personal/medical/HAGO"))

TYPES = ["應診證明書", "醫生證明書", "轉介信", "檢驗備忘表",
         "門診後資訊摘要", "醫療程序資訊單張", "出院摘要", "入院紀錄"]

SITES = {
    "Princess Margaret": "PMH",
    "Caritas Medical": "CMC",
    "Pamela Youde": "PYNEH",
    "Queen Elizabeth": "QEH",
}

# Visit dates before this are treated as misreads rather than real dates.
# Override with EARLIEST_RECORD if your records go back further.
EARLIEST = os.environ.get("EARLIEST_RECORD", "2015-01-01")

MONTHS = "Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split()
DATE_RE = re.compile(r"(\d{1,2})\s*-?\s*(" + "|".join(MONTHS) + r")\s*-?\s*(\d{4})")


def text_of(p):
    # pdftotext rather than PDFKit: pyobjc is only installed inside the
    # phone-harness venv on the Mini, so the Quartz version would not run on
    # the laptop, which is where the records actually live.
    return subprocess.run(["pdftotext", "-layout", str(p), "-"],
                          capture_output=True, text=True).stdout


# --- lab reports (eHealth 化驗紀錄) ----------------------------------------
# These are cumulative: one sheet carries several collect dates side by side,
# so they get named by the LATEST collect date they contain.
LAB_SECTIONS = ["Chemical Pathology", "Haematology", "Microbiology",
                "Immunology", "Anatomical Pathology", "Molecular Pathology"]
# Cumulative sheets head their columns dd/mm/yy; single-date sheets write the
# collect date out in full (dd/mm/yyyy). Missing the second form left three
# Haematology reports named "undated".
SHORT_DATE = re.compile(r"\b(\d{2})/(\d{2})/(\d{2}(?:\d{2})?)\b")


def is_lab(t):
    return "Laboratory" in t and any(s in t for s in LAB_SECTIONS)


def lab_section(t):
    for s in LAB_SECTIONS:
        if s in t:
            return s.replace(" ", "")
    return "Lab"


# Same date + same lab section can be several different panels, so tag the
# headline analyte — this is what makes CRP/ESR trends findable by filename.
ANALYTES = [
    ("C-Reactive Protein", "CRP"),
    ("Erythrocyte sedimentation", "ESR"),
    ("Fecal calprotectin", "Calprotectin"),
    ("Complement", "Complement"),
    ("Rheumatoid", "RA"),
    ("Anti-dsDNA", "DNA"),      # after RA: the dual dsDNA+RF sheets stay "RA"
    ("Anti-Nuclear", "ANA"),
    ("Thyroid", "TFT"),
    ("Thyroid Stimulating", "TFT"),
    ("HbA1c", "A1c"),           # before CBC: "Haemoglobin A1c" is not a CBC
    ("Haemoglobin", "CBC"),
    ("White Cell Count", "CBC"),
    ("Creatinine", "RFT"),
    ("Alanine", "LFT"),
    ("Calcium", "Calcium"),
    ("Glucose", "Glucose"),
]


def lab_panel(t):
    for needle, tag in ANALYTES:
        if needle.lower() in t.lower():
            return tag
    return ""


def lab_date(t):
    """Latest dd/mm/yy collect date in the sheet, ignoring the DOB line."""
    best = None
    for m in SHORT_DATE.finditer(t):
        d, mo, y = m.groups()
        if not (1 <= int(mo) <= 12):
            continue
        if "DOB" in t[max(0, m.start() - 30):m.start()]:
            continue
        iso = f"{y}-{mo}-{d}" if len(y) == 4 else f"20{y}-{mo}-{d}"
        # the authorisation / print stamps sit after the results and are always
        # later than the collect date, so they must not win the "latest" test
        if "Report Date" in t[max(0, m.start() - 40):m.start()] or \
           "Generated on" in t[max(0, m.start() - 40):m.start()] or \
           "Authorized" in t[max(0, m.start() - 60):m.start()]:
            continue
        if iso > (best or ""):
            best = iso
    return best or "undated"


def classify(t):
    hits = [(t.find(k), k) for k in TYPES if k in t]
    hits = [h for h in hits if h[0] >= 0]
    return sorted(hits)[0][1] if hits else "未知"


NUM_RE = re.compile(r"(\d{1,2})/(\d{1,2})/(\d{4})")
# Dates we must never use as the document's date.
BAD_CONTEXT = ("DOB", "出生", "Printed Time", "列印")
# Dates that identify the visit, in order of preference.
GOOD_CONTEXT = ("Request Date", "Appointment date", "Appointment Date",
                "門診日期", "日期及時間為", "Date of Attendance",
                "Admission Date", "入院日期", "Discharge", "出院日期")


def _candidates(t):
    """(iso_date, position) for every plausible visit date in the text."""
    out = []
    for m in DATE_RE.finditer(t):
        d, mon, y = m.groups()
        out.append((f"{y}-{MONTHS.index(mon)+1:02d}-{int(d):02d}", m.start()))
    for m in NUM_RE.finditer(t):
        d, mo, y = m.groups()
        if 1 <= int(mo) <= 12:
            out.append((f"{y}-{int(mo):02d}-{int(d):02d}", m.start()))
    keep = []
    for iso, pos in out:
        window = t[max(0, pos - 40):pos]
        if any(b in window for b in BAD_CONTEXT):
            continue          # DOB / print timestamp, not the visit
        if iso < EARLIEST:
            continue          # implausibly old for a visit date; configurable
        keep.append((iso, pos))
    return keep


def date_of(t):
    cands = _candidates(t)
    if not cands:
        return "undated"
    for label in GOOD_CONTEXT:            # prefer an explicitly labelled date
        i = t.find(label)
        if i >= 0:
            after = [c for c in cands if 0 <= c[1] - i <= 80]
            if after:
                return min(after, key=lambda c: c[1])[0]
    return min(cands, key=lambda c: c[1])[0]


def site_of(t):
    for k, v in SITES.items():
        if k.lower() in t.lower():
            return v
    return "HA"


rows = []
for p in sorted(SRC.glob("*.pdf")):
    t = text_of(p)
    if is_lab(t):
        tag = lab_panel(t)
        kind = "lab-" + lab_section(t) + (f"-{tag}" if tag else "")
        rows.append((p, lab_date(t), kind, site_of(t),
                     hashlib.sha1(p.read_bytes()).hexdigest()))
        continue
    kind = classify(t)
    if kind == "未知":                     # info leaflets carry no title line
        kind = re.sub(r"\s*\d+$", "", p.stem)
    rows.append((p, date_of(t), kind, site_of(t),
                 hashlib.sha1(p.read_bytes()).hexdigest()))

# collapse exact duplicates (same bytes) and disambiguate name clashes.
# Seed from the destination as well: a cumulative sheet re-exported on a later
# sweep is byte-identical to one already filed, and comparing only within this
# run filed it again as "<name>_2".
seen_hash, plan, used = {}, [], set()

# Refuse to run against the archive itself. Seeding from the destination means
# every file there is already a known hash, so each source file would match
# ITSELF, be planned as a duplicate, and be unlinked -- i.e. --apply on the
# archive would delete the entire archive.
if SRC.resolve() == DST.resolve():
    sys.exit(f"refusing to run on the archive itself ({DST}) -- SRC must be an "
             "incoming directory, not the destination")

for q in DST.glob("*.pdf"):
    seen_hash[hashlib.sha1(q.read_bytes()).hexdigest()] = q
for p, d, kind, site, h in sorted(rows, key=lambda r: (r[1], r[2])):
    twin = seen_hash.get(h)
    # A hash match is only acted on after comparing the bytes: deleting a
    # distinct record because two files shared a digest prefix is unacceptable,
    # and the consequence here is an unlink.
    if twin is not None and twin.read_bytes() == p.read_bytes():
        plan.append((p, None, f"duplicate of {twin.name}"))
        continue
    seen_hash[h] = p
    base = f"{d}_{kind}_{site}"
    name, n = base + ".pdf", 2
    # Must check the destination too, not just this run: a same-day panel
    # exported on a later sweep would otherwise rename onto an existing record
    # and destroy it.
    while name in used or (DST / name).exists():
        name, n = f"{base}_{n}.pdf", n + 1
    used.add(name)
    plan.append((p, name, ""))

for p, name, note in plan:
    print(f"{p.name:32} -> {name or '(skip)':44} {note}")

if "--apply" in sys.argv:
    DST.mkdir(parents=True, exist_ok=True)
    for p, name, note in plan:
        if not name:
            p.unlink()
            continue
        # os.rename would silently replace a file that appeared since planning.
        # Re-resolve the name at move time and never overwrite: losing a record
        # to a race is not recoverable.
        target, n = DST / name, 2
        while target.exists():
            target = DST / f"{Path(name).stem}_{n}.pdf"
            n += 1
        os.rename(p, target)
        if target.name != name:
            print(f"  (collision at move time: filed as {target.name})")
    print(f"\nmoved to {DST}")

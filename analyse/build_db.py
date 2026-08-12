"""Build medical.db -- one private, local SQLite file holding every record.

Three layers, deliberately separated:

  documents    one row per PDF, with its full text (the thing you search)
  lab_results  one row per (collect date, analyte) -- the quantified layer
  chunks       document text split for embedding (vectors live in embeddings)

The lab parsing is imported from extract_labs.py rather than duplicated, so the
column-matching fixes that took a day to find are not re-litigated here.

Everything stays on this machine. Nothing is uploaded.
"""
import hashlib
import os
import re
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path

# The parser lives in ../parse in this repository and alongside this file in
# a flat install; support both rather than forcing one layout.
sys.path.insert(0, str(Path(__file__).parent.parent / "parse"))
sys.path.insert(0, str(Path(__file__).parent))
import extract_labs as ex               # noqa: E402

HERE = Path(__file__).parent
# Where the renamed PDFs live, and where to write the database. Both are
# configurable so the code carries no assumption about one person's setup.
SRC = Path(os.environ.get("HAGO_DIR", HERE / "HAGO"))
DB = Path(os.environ.get("MEDICAL_DB", HERE / "medical.db"))

# --- canonical analyte names ------------------------------------------------
# The same test is printed several ways across labs and years; analysis needs
# one key per test, but the raw string is kept for auditing.
CANON = {
    "ESR, automated": "ESR",
    "ESR,automated": "ESR",
    "C-Reactive Protein": "CRP",
    "Faecal calprotectin": "Calprotectin",
    "Fecal calprotectin": "Calprotectin",
    "Anti-dsDNA Antibody": "Anti-dsDNA",
    "Rheumatoid Factor": "RF",
    "eGFR (CKD-EPI)": "eGFR",
    "eGFR （CKD-EPI）": "eGFR",
    "Total Protein": "Total Protein",
    "Total Bilirubin": "Bilirubin",
    "HbA1c (IFCC)": "HbA1c-IFCC",
}

# Which panel a test belongs to -- lets the analysis group sensibly.
CATEGORY = {
    "inflammation": {"ESR", "CRP", "Calprotectin"},
    "haematology": {"HGB", "HCT", "RBC", "WBC", "PLT", "MCV", "MCH", "MCHC",
                    "RDW", "MPV", "Neutrophil", "Lymphocyte", "Monocyte",
                    "Eosinophil", "Basophil", "NEU %", "LYM %", "MON %",
                    "EOS %", "BAS %", "MPV", "MPV (Calculated)"},
    "renal": {"Creatinine", "Urea", "eGFR", "Sodium", "Potassium", "Phosphate"},
    "liver": {"ALT", "ALP", "Albumin", "Globulin", "Bilirubin", "Total Protein"},
    "immunology": {"Complement 3", "Complement 4", "Anti-dsDNA", "RF", "ANA"},
    "iron": {"Ferritin", "Iron", "TIBC", "Iron Saturation"},
    "metabolic": {"HbA1c", "HbA1c-IFCC", "Glucose, spot", "Cholesterol",
                  "Triglyceride", "HDL-Cholesterol", "LDL-Cholesterol",
                  "Non-HDL-Cholesterol", "Calcium", "Magnesium", "TSH"},
}
OF_CATEGORY = {a: c for c, s in CATEGORY.items() for a in s}

# Words that only ever appear as reference-legend labels ("Borderline : 35 - 46
# IU/mL" under anti-dsDNA). No real test is named these, so they are always a
# misparse of the legend rather than a result.
NOT_AN_ANALYTE = {"Borderline", "Negative", "Positive", "Normal", "Elevated",
                  "Desirable", "Optimal"}

VALUE_NUM = re.compile(r"^([<>]=?)?\s*([\d,]+\.?\d*)$")
# "13.4 - 17.1 g/dL" / "< 24 mm/hr" / "0.90 - 1.80 # g/L" / "See Below"
REF_RANGE = re.compile(r"([\d.]+)\s*-\s*([\d.]+)")
REF_UPPER = re.compile(r"<\s*=?\s*([\d.]+)")
REF_LOWER = re.compile(r">\s*=?\s*([\d.]+)")
# section titles bleed into the right-hand column on some templates
REF_NOISE = re.compile(r"\b(HAEMATOLOGY|CHEMICAL|PATHOLOGY|REPORT|MICROBIOLOGY)\b.*",
                       re.I)

SITES = {"Princess Margaret": "PMH", "Caritas Medical": "CMC",
         "Pamela Youde": "PYNEH", "Queen Elizabeth": "QEH"}


def parse_value(raw):
    """'<0.6' -> ('<', 0.6) ; '12.3' -> (None, 12.3) ; 'Negative' -> (None, None)"""
    m = VALUE_NUM.match(raw.strip())
    if not m:
        return None, None
    return m.group(1), float(m.group(2).replace(",", ""))


def parse_ref(raw):
    """-> (low, high, unit). The lab prints the range; never hard-code one."""
    if not raw:
        return None, None, None
    txt = REF_NOISE.sub("", raw).replace("#", " ").strip()
    low = high = None
    m = REF_RANGE.search(txt)
    if m:
        low, high = float(m.group(1)), float(m.group(2))
    elif REF_UPPER.search(txt):
        high = float(REF_UPPER.search(txt).group(1))
    elif REF_LOWER.search(txt):
        low = float(REF_LOWER.search(txt).group(1))
    # unit is whatever trails the numbers
    tail = txt[m.end():] if m else re.sub(r"^[<>=\s\d.]+", "", txt)
    unit = tail.strip(" .") or None
    if unit and (unit.lower().startswith("see") or len(unit) > 18):
        unit = None
    return low, high, unit


# Some tests print an interpretation legend instead of a numeric range
# ("Negative : < 35 IU/mL", "< 80 ug/g Normal"). Those rows end up with no
# ref_low/ref_high, and an analysis that only sees the number cannot say whether
# 11 or 328 is normal. Capture the legend so the threshold is never lost.
# not anchored to line start: the first legend line usually shares a line with
# the result itself ("Anti-dsDNA Antibody  11  Negative : < 35 IU/mL")
LEGEND = re.compile(
    r"\b(Negative|Positive|Borderline|Normal|Elevated|Equivocal|Indeterminate)"
    r"\s*:\s*([<>=]\s*[\d.]+[^\n]*?)(?=\s{2,}|\n|$)", re.I)


def legend_for(analyte, text):
    """The interpretation block printed near `analyte`, if there is one."""
    i = text.find(analyte)
    if i < 0:
        return None
    window = text[i:i + 600]
    hits = [f"{m.group(1)} {m.group(2).strip()}" for m in LEGEND.finditer(window)]
    if not hits:
        # the calprotectin style: a table of thresholds under a heading
        rows = re.findall(r"([<>]\s*\d[\d.]*\s*\S*)\s+(Normal|Borderline|Elevated)",
                          window, re.I)
        hits = [f"{b} {a}" for a, b in rows]
    return "; ".join(dict.fromkeys(hits))[:300] or None


def chunks_of(text, size=1100, overlap=150):
    """Paragraph-ish chunks. Lab sheets are tabular, so split on blank lines
    first and only fall back to hard slicing for very long blocks."""
    blocks, buf = [], []
    for para in re.split(r"\n\s*\n", text):
        para = para.rstrip()
        if not para.strip():
            continue
        if sum(len(b) for b in buf) + len(para) > size and buf:
            blocks.append("\n\n".join(buf))
            buf = buf[-1:] if overlap else []
        buf.append(para)
    if buf:
        blocks.append("\n\n".join(buf))
    out = []
    for b in blocks:
        while len(b) > size * 2:
            out.append(b[:size])
            b = b[size - overlap:]
        out.append(b)
    return [c for c in out if c.strip()]


SCHEMA = """
PRAGMA journal_mode=WAL;

CREATE TABLE IF NOT EXISTS documents (
    id         INTEGER PRIMARY KEY,
    filename   TEXT UNIQUE NOT NULL,
    sha1       TEXT NOT NULL,
    doc_date   TEXT,                 -- ISO, or NULL for the undated leaflet
    doc_type   TEXT,                 -- 轉介信 / lab-Haematology-CRP / ...
    site       TEXT,                 -- PMH / CMC / PYNEH / HA
    is_lab     INTEGER NOT NULL,
    n_chars    INTEGER,
    text       TEXT
);

CREATE TABLE IF NOT EXISTS lab_results (
    id           INTEGER PRIMARY KEY,
    collect_date TEXT NOT NULL,      -- ISO date the specimen was taken
    analyte      TEXT NOT NULL,      -- canonical
    analyte_raw  TEXT NOT NULL,      -- exactly as printed
    category     TEXT,
    value_raw    TEXT NOT NULL,
    value_num    REAL,               -- NULL for Negative/Positive results
    comparator   TEXT,               -- '<' or '>' when the lab censored it
    unit         TEXT,
    flag         TEXT,               -- the lab's own H / L
    ref_low      REAL,
    ref_high     REAL,
    ref_raw      TEXT,
    abnormal     INTEGER,            -- 1 if the lab flagged it
    n_sheets     INTEGER,            -- how many reports agreed on this value
    interpretation TEXT,              -- legend for tests with no numeric range
    sources      TEXT,
    UNIQUE (collect_date, analyte)
);

CREATE TABLE IF NOT EXISTS chunks (
    id      INTEGER PRIMARY KEY,
    doc_id  INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    ord     INTEGER NOT NULL,
    text    TEXT NOT NULL,
    UNIQUE (doc_id, ord)
);

CREATE TABLE IF NOT EXISTS embeddings (
    chunk_id INTEGER PRIMARY KEY REFERENCES chunks(id) ON DELETE CASCADE,
    model    TEXT NOT NULL,
    dim      INTEGER NOT NULL,
    vec      BLOB NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_lab_analyte ON lab_results(analyte, collect_date);
CREATE INDEX IF NOT EXISTS ix_lab_date    ON lab_results(collect_date);
CREATE INDEX IF NOT EXISTS ix_doc_date    ON documents(doc_date);

-- full-text search over the documents themselves
CREATE VIRTUAL TABLE IF NOT EXISTS docs_fts USING fts5(
    filename, text, content='documents', content_rowid='id'
);

CREATE VIEW IF NOT EXISTS v_abnormal AS
    SELECT collect_date, analyte, value_raw, flag, ref_low, ref_high, unit
    FROM lab_results WHERE abnormal = 1 ORDER BY collect_date DESC;

CREATE VIEW IF NOT EXISTS v_latest AS
    SELECT analyte, collect_date, value_raw, flag, unit, ref_low, ref_high
    FROM lab_results r
    WHERE collect_date = (SELECT MAX(collect_date) FROM lab_results r2
                          WHERE r2.analyte = r.analyte);
"""


def main():
    if not SRC.is_dir():
        sys.exit(f"{SRC} not found")
    files = sorted(SRC.glob("*.pdf"))
    if not files:
        sys.exit(f"no PDFs in {SRC} -- refusing to build an empty database")
    # Build into a temporary file and swap only once the result validates, so a
    # failed or partial run can never replace a known-good database.
    tmp = DB.with_suffix(".building")
    for stale in (tmp, Path(str(tmp) + "-wal"), Path(str(tmp) + "-shm")):
        stale.unlink(missing_ok=True)
    con = sqlite3.connect(tmp)
    con.execute("PRAGMA foreign_keys=ON")     # the schema declares cascades
    con.executescript(SCHEMA)
    doc_sha = {}
    doc_ids = {}
    for p in files:
        text = pdftext(p)
        stem = p.stem
        date = stem.split("_")[0] if re.match(r"\d{4}-\d{2}-\d{2}", stem) else None
        parts = stem.split("_")
        doc_type = parts[1] if len(parts) > 1 else stem
        site = parts[2] if len(parts) > 2 else "HA"
        sha = hashlib.sha1(p.read_bytes()).hexdigest()
        doc_sha[p.name] = sha
        cur = con.execute(
            "INSERT INTO documents (filename, sha1, doc_date, doc_type, site,"
            " is_lab, n_chars, text) VALUES (?,?,?,?,?,?,?,?)",
            (p.name, sha, date, doc_type,
             site, int(doc_type.startswith("lab-")), len(text), text))
        doc_ids[p.name] = cur.lastrowid
        for i, c in enumerate(chunks_of(text)):
            con.execute("INSERT INTO chunks (doc_id, ord, text) VALUES (?,?,?)",
                        (cur.lastrowid, i, c))

    con.execute("INSERT INTO docs_fts(rowid, filename, text) "
                "SELECT id, filename, text FROM documents")

    # --- lab results, via the verified parser -------------------------------
    rows = []
    for p in files:
        try:
            for ws in ex.pages(p):
                rows += ex.extract_page(ws, p.name)
        except Exception as e:                      # noqa: BLE001
            print(f"  ! {p.name}: {e}", file=sys.stderr)

    # Group on the CANONICAL name: 'ESR, automated' and 'ESR,automated' are the
    # same test, and grouping on the raw spelling would let two different values
    # pass the conflict check and then overwrite each other on insert.
    merged = defaultdict(list)
    for r in rows:
        merged[(r["date"], CANON.get(r["analyte"], r["analyte"]))].append(r)

    kept = excluded = conflicts = 0
    for (date, analyte), group in sorted(merged.items()):
        if analyte in NOT_AN_ANALYTE:
            excluded += 1
            continue
        raw_name = group[0]["analyte"]
        vals = sorted({g["value"] for g in group})
        if len(vals) > 1 and len({parse_value(v)[1] for v in vals}) > 1:
            # differing numbers are a real disagreement; never pick one
            print(f"  ! conflict {date} {analyte}: {vals}", file=sys.stderr)
            conflicts += 1
            continue
        # '1' vs '1.0' is formatting, not disagreement -- keep the longest form
        value_raw = max(vals, key=len)
        newest = max(group, key=lambda g: g["source"])
        comp, num = parse_value(value_raw)
        low, high, unit = parse_ref(newest["ref"])
        interp = None
        if low is None and high is None:
            src = con.execute("SELECT text FROM documents WHERE filename = ?",
                              (newest["source"],)).fetchone()
            if src:
                interp = legend_for(raw_name, src[0])
        flag = next((g["flag"] for g in group if g["flag"]), "")
        con.execute(
            "INSERT OR REPLACE INTO lab_results (collect_date, analyte,"
            " analyte_raw, category, value_raw, value_num, comparator, unit,"
            " flag, ref_low, ref_high, ref_raw, abnormal, n_sheets,"
            " interpretation, sources)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (date, analyte, raw_name, OF_CATEGORY.get(analyte), value_raw, num,
             comp, unit, flag, low, high, newest["ref"], int(bool(flag)),
             # count distinct CONTENT: two filenames holding identical bytes are
             # one report, not two independent confirmations
             len({doc_sha.get(g["source"], g["source"]) for g in group}),
             interp,
             ";".join(sorted({g["source"] for g in group}))))
        kept += 1

    con.commit()
    n_doc, n_chunk = (con.execute("SELECT COUNT(*) FROM documents").fetchone()[0],
                      con.execute("SELECT COUNT(*) FROM chunks").fetchone()[0])
    n_dates = con.execute(
        "SELECT COUNT(DISTINCT collect_date) FROM lab_results").fetchone()[0]
    con.close()

    # Validate before replacing the existing database. A parser regression that
    # silently halves the results must not overwrite a good build.
    if kept == 0 or n_doc != len(files):
        sys.exit(f"refusing to publish: {n_doc}/{len(files)} documents, "
                 f"{kept} results — left the previous {DB.name} untouched")
    if DB.exists():
        prev = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
        try:
            before = prev.execute("SELECT COUNT(*) FROM lab_results").fetchone()[0]
        except sqlite3.Error:
            before = 0
        prev.close()
        if before and kept < before * 0.9:
            sys.exit(f"refusing to publish: {kept} results vs {before} in the "
                     f"current {DB.name} — investigate before rebuilding")
    for suffix in ("-wal", "-shm"):
        Path(str(tmp) + suffix).unlink(missing_ok=True)
    tmp.replace(DB)
    DB.chmod(0o600)          # medical records: not world- or group-readable

    print(f"{DB.name}: {n_doc} documents, {n_chunk} chunks, "
          f"{kept} lab results over {n_dates} draw dates"
          + (f", {excluded} legend artifacts excluded" if excluded else "")
          + (f", {conflicts} CONFLICTS DROPPED" if conflicts else ""))


def pdftext(p):
    import subprocess
    return subprocess.run(["pdftotext", "-layout", str(p), "-"],
                          capture_output=True, text=True).stdout


if __name__ == "__main__":
    main()

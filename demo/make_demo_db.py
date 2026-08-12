"""Build a demo database from synthetic data — no real records involved.

Used for the screenshots in the README and as a fixture to develop against, so
nobody has to point the tools at real medical data to see them work, and no
real values can end up in a public image.

The numbers are generated, the name is invented, and the dates are arbitrary.
They are plausible enough to exercise the UI and the statistics, and mean
nothing.

    python3 demo/make_demo_db.py            # -> demo/demo.db
"""
import random
import sqlite3
import sys
from datetime import date, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE.parent / "analyse"))

import build_db as bd                                   # noqa: E402

DB = Path(sys.argv[1]) if len(sys.argv) > 1 else HERE / "demo.db"
RNG = random.Random(20260812)          # fixed seed: the demo is reproducible

# (analyte, unit, ref_low, ref_high, mean, sd, decimals)
PANEL = [
    ("ESR", "mm/hr", None, 24.0, 9, 4, 0),
    ("CRP", "mg/L", None, 5.0, 1.2, 0.6, 1),
    ("HGB", "g/dL", 13.4, 17.1, 14.4, 0.6, 1),
    ("HCT", "L/L", 0.400, 0.510, 0.44, 0.02, 3),
    ("RBC", "x10^12/L", 4.30, 5.90, 5.0, 0.3, 2),
    ("MCV", "fL", 82.0, 97.0, 88.0, 3.0, 1),
    ("MCH", "pg", 27.0, 33.0, 30.0, 1.2, 1),
    ("WBC", "x10^9/L", 3.7, 9.2, 6.2, 1.1, 1),
    ("PLT", "x10^9/L", 145, 370, 250, 35, 0),
    ("Creatinine", "umol/L", 60, 110, 80, 8, 0),
    ("ALT", "U/L", 10, 53, 26, 8, 0),
    ("Albumin", "g/L", 35, 50, 43, 2, 0),
    ("Sodium", "mmol/L", 136, 145, 140, 2, 0),
    ("Potassium", "mmol/L", 3.4, 4.8, 4.1, 0.3, 1),
]
CATEGORY = {a: bd.OF_CATEGORY.get(a) for a, *_ in PANEL}

DOC_TEXT = """Hospital Authority                     Lab No: DEMO0000001
Demo Hospital                          Name: DOE, JOHN (DEMO)
                                       HKID No: A000000(0)
Chemical Pathology Laboratory          Doctor: DEMO, CLINICIAN
Clinical Details: demonstration data only

This document contains generated sample values for demonstration. It is not a
medical record and describes nobody. Every figure was produced by a random
number generator.
"""


def draws(n=14):
    d = date(2026, 6, 1)
    out = []
    for _ in range(n):
        out.append(d)
        d -= timedelta(days=RNG.randint(80, 200))
    return sorted(out)


def main():
    DB.unlink(missing_ok=True)
    con = sqlite3.connect(DB)
    con.executescript(bd.SCHEMA)

    dates = draws()
    for i, d in enumerate(dates):
        con.execute(
            "INSERT INTO documents (filename, sha1, doc_date, doc_type, site,"
            " is_lab, n_chars, text) VALUES (?,?,?,?,?,?,?,?)",
            (f"{d}_lab-Demo_DEMO.pdf", f"demo{i:036d}", d.isoformat(),
             "lab-ChemicalPathology", "DEMO", 1, len(DOC_TEXT), DOC_TEXT))
    con.execute("INSERT INTO docs_fts(rowid, filename, text) "
                "SELECT id, filename, text FROM documents")

    for analyte, unit, lo, hi, mean, sd, dp in PANEL:
        drift = RNG.uniform(-0.25, 0.25) * sd
        for i, d in enumerate(dates):
            val = RNG.gauss(mean + drift * i, sd)
            # no measurement here can be negative, and a one-sided reference
            # range gives no lower bound to clamp against
            val = max(val, lo * 0.9 if lo is not None else 0.1)
            val = round(val, dp)
            if dp == 0:
                val = int(val)
            flag = ""
            if hi is not None and val > hi:
                flag = "H"
            elif lo is not None and val < lo:
                flag = "L"
            con.execute(
                "INSERT INTO lab_results (collect_date, analyte, analyte_raw,"
                " category, value_raw, value_num, comparator, unit, flag,"
                " ref_low, ref_high, ref_raw, abnormal, n_sheets,"
                " interpretation, sources) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (d.isoformat(), analyte, analyte, CATEGORY.get(analyte),
                 str(val), float(val), None, unit, flag, lo, hi,
                 f"{lo}-{hi} {unit}", int(bool(flag)),
                 min(5, len(dates) - i), None, f"{d}_lab-Demo_DEMO.pdf"))
    con.commit()
    n = con.execute("SELECT COUNT(*) FROM lab_results").fetchone()[0]
    con.close()
    print(f"{DB}: {n} synthetic results over {len(dates)} dates "
          f"({len(PANEL)} tests). Contains no real data.")


if __name__ == "__main__":
    main()

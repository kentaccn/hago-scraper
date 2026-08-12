"""Turn the HA GO / eHealth lab PDFs into one analyte x collect-date table.

The sheets are cumulative: one report carries up to five collect dates side by
side, each analyte's values aligned under its date column. Whitespace layout is
not reliable enough for numbers that matter -- a blank cell shifts every later
value one column left -- so this reads real word coordinates from
`pdftotext -bbox-layout` and assigns each value to the nearest column centre.

Pages are handled separately: a report's second panel starts its y coordinates
over again, so grouping rows document-wide splices unrelated tables together.
"""
import csv
import os
import re
import subprocess
import sys
import xml.etree.ElementTree as ET
from collections import defaultdict
from pathlib import Path

# Load ~/.hago-scraper.env so every stage sees the same paths. Without this
# only the shell wrappers read it, and one stage writes where the next never
# looks.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import config                              # noqa: E402
config.load()

SRC = Path(os.environ.get("HAGO_DIR",
                          Path.home() / "repo/personal/medical/HAGO"))
# The date of birth is printed on every report and must never be mistaken for a
# collect date. Set DOB_YEAR to filter it out; nothing is hard-coded here.
DOB_YEAR = os.environ.get("DOB_YEAR", "")
XH = "{http://www.w3.org/1999/xhtml}"

SHORT = re.compile(r"^(\d{2})/(\d{2})/(\d{2})$")
LONG = re.compile(r"^(\d{2})/(\d{2})/(\d{4})$")
VALUE = re.compile(r"^(?:[<>]=?)?\d[\d,]*\.?\d*$|^(?:Negative|Positive|Nil"
                   r"|Detected|Reactive|Non-Reactive|Trace|Normal)$", re.I)
SKIP_ROW = re.compile(r"Reference|Interval|Units|Request No|Urgency|Specimen"
                      r"|Collect (Date|Time)|Arrive (Date|Time)|Report |Page No"
                      r"|Authorized|Generated|End of report|Footnote|Lab No"
                      r"|HKID|Hosp No|DOB|Sex/Age|Location|Req\. Loc|Doctor"
                      r"|Clinical Details|Hospital|Laboratory|^Name|Bed:"
                      r"|Date/time|effect from", re.I)

COL_TOL = 26.0        # pt; column pitch is ~58pt
ROW_TOL = 3.0
FLAGS = {"H", "L", "HH", "LL", "*"}


def iso(d, m, y):
    y = int(y)
    return f"{y if y > 100 else 2000 + y:04d}-{int(m):02d}-{int(d):02d}"


def pages(pdf):
    r = subprocess.run(["pdftotext", "-bbox-layout", str(pdf), "-"],
                       capture_output=True, text=True)
    if r.returncode != 0:
        # an unreadable PDF must not be mistaken for an empty one
        raise RuntimeError(f"pdftotext failed on {pdf.name}: "
                           f"{r.stderr.strip()[:200]}")
    xml = r.stdout
    root = ET.fromstring(xml)
    for page in root.iter(f"{XH}page"):
        ws = []
        for w in page.iter(f"{XH}word"):
            t = (w.text or "").strip()
            if not t:
                continue
            x0, x1 = float(w.get("xMin")), float(w.get("xMax"))
            ws.append({"t": t, "x0": x0, "x1": x1, "cx": (x0 + x1) / 2,
                       "y": float(w.get("yMin"))})
        if ws:
            yield ws


def rows_of(ws):
    rows = defaultdict(list)
    for w in sorted(ws, key=lambda w: (w["y"], w["x0"])):
        for y in rows:
            if abs(y - w["y"]) <= ROW_TOL:
                rows[y].append(w)
                break
        else:
            rows[w["y"]].append(w)
    return [(y, sorted(v, key=lambda w: w["x0"]))
            for y, v in sorted(rows.items())]


def line_of(row):
    return " ".join(w["t"] for w in row)


def date_columns(rows):
    """[(centre_x, iso)] from the Collect Date header block, left to right."""
    cols = {}
    for y, row in rows:
        for w in row:
            m = SHORT.match(w["t"])
            if m and 1 <= int(m.group(2)) <= 12:
                cols.setdefault(round(w["cx"]), (w["cx"], iso(*m.groups()), y))
    if not cols:
        return []
    ordered = sorted(cols.values())
    top = min(c[2] for c in ordered)
    ordered = [c for c in ordered if c[2] - top < 60]   # header block only
    return [(cx, d) for cx, d, _ in ordered]


def single_date(rows):
    """Non-cumulative sheet: 'Date/time Collected : dd/mm/yyyy hh:mm'."""
    seen = False
    for y, row in rows:
        if "Collected" in line_of(row):
            seen = True
        if not seen:
            continue
        for w in row:
            m = LONG.match(w["t"])
            # A date of birth is printed on every report. Reject anything too
            # old to be a collect date regardless of configuration, and the
            # exact DOB year as well when it is supplied.
            if (m and 1 <= int(m.group(2)) <= 12
                    and int(m.group(3)) >= 2000
                    and m.group(3) != DOB_YEAR):
                return iso(*m.groups()), w["cx"]
    return None, None


def body_start(rows):
    """y below which result rows begin."""
    ys = [y for y, row in rows
          if re.search(r"Specimen type|Request No", line_of(row), re.I)]
    return max(ys) if ys else 0


# Guidance tables below the results reuse the analyte names with threshold
# numbers ("LDL-C <3.0 <2.6 <1.8"), which read as results if left in.
END_MARK = re.compile(r"Desirable levels|Treatment goals|End of report"
                      r"|Footnote|Interpretation|For adults:", re.I)


def body_end(rows, start_y):
    ys = [y for y, row in rows if y > start_y and END_MARK.search(line_of(row))]
    return min(ys) if ys else float("inf")


def extract_page(ws, name):
    rows = rows_of(ws)
    cols = date_columns(rows)
    tol = COL_TOL
    single = False
    if not cols:
        d, cx = single_date(rows)
        if not d:
            return []
        # One-date sheet: the single value sits wherever the template put it,
        # not under the date, so match loosely and take only the first value on
        # the row -- anything after it is the reference interval.
        cols, tol, single = [(cx or 200.0, d)], float("inf"), True
    start_y = body_start(rows)
    end_y = body_end(rows, start_y)
    first_x, last_x = cols[0][0], cols[-1][0]
    out = []
    for y, row in rows:
        if y <= start_y or y >= end_y or SKIP_ROW.search(line_of(row)):
            continue
        label = [w for w in row if w["x1"] < first_x - COL_TOL] if not single \
            else [w for w in row if not VALUE.match(w["t"])
                  and w["x0"] < min((v["x0"] for v in row
                                     if VALUE.match(v["t"])), default=1e9)]
        analyte = " ".join(w["t"] for w in label).strip(" .,-:")
        if len(analyte) < 3 or not re.search(r"[A-Za-z]", analyte):
            continue
        # The interpretive notes at the foot of a report are full-width prose,
        # and sentences like "Plasma glucose concentration <2.5 or >= 11.1"
        # otherwise parse as results. A real result row carries only values and
        # H/L flags inside the column band.
        band = [w for w in row if w not in label
                and first_x - COL_TOL <= w["cx"] <= last_x + COL_TOL]
        prose = [w for w in band
                 if not VALUE.match(w["t"]) and len(w["t"]) >= 4
                 and re.fullmatch(r"[A-Za-z][A-Za-z\-']+", w["t"])]
        if len(prose) >= 2:
            continue
        # Everything right of the last column is the lab's own reference
        # interval and units -- quote those rather than hard-coding ranges.
        ref = " ".join(w["t"] for w in row if w["cx"] > last_x + COL_TOL) \
            if not single else ""
        for w in row:
            if w in label or not VALUE.match(w["t"]):
                continue
            # "Not Detected" / "Non-Reactive" tokenise as two words, and taking
            # the second alone inverts the result -- a negative reported as a
            # positive. Carry the negator into the value.
            token = w["t"]
            if re.match(r"^(Detected|Reactive|Positive)$", token, re.I):
                left = [v for v in row if v["x1"] <= w["x0"]]
                if left and re.fullmatch(r"(not|non|no)-?", left[-1]["t"], re.I):
                    token = f"{left[-1]['t']} {token}"
            if not single and w["cx"] > last_x + COL_TOL:
                continue
            cx, date = min(cols, key=lambda c: abs(c[0] - w["cx"]))
            if abs(cx - w["cx"]) <= tol:
                # the lab prints H / L beside an out-of-range value; trust that
                # over any range comparison of our own
                flag = next((f["t"] for f in row if f["t"] in FLAGS
                             and 0 <= f["x0"] - w["x1"] <= 16), "")
                out.append({"date": date, "analyte": analyte, "value": token,
                            "flag": flag, "ref": ref, "source": name})
            if single:
                break             # the rest of the row is the reference range
    return out


def main():
    rows, empty = [], []
    files = sorted(SRC.glob("*.pdf"))
    for p in files:
        got = []
        try:
            for ws in pages(p):
                got += extract_page(ws, p.name)
        except ET.ParseError as e:
            print(f"  ! parse {p.name}: {e}", file=sys.stderr)
        if not got and "lab-" in p.name:
            empty.append(p.name)
        rows.extend(got)

    merged = defaultdict(list)
    for r in rows:
        merged[(r["date"], r["analyte"])].append(r)
    out = []
    for (date, analyte), group in sorted(merged.items()):
        vals = sorted({g["value"] for g in group})
        newest = max(group, key=lambda g: g["source"])
        out.append({"date": date, "analyte": analyte,
                    "value": vals[0] if len(vals) == 1 else "|".join(vals),
                    "flag": next((g["flag"] for g in group if g["flag"]), ""),
                    "ref": newest["ref"],
                    "n_sheets": len({g["source"] for g in group}),
                    "conflict": "Y" if len(vals) > 1 else "",
                    "sources": ";".join(sorted({g["source"] for g in group}))})
    w = csv.DictWriter(sys.stdout, fieldnames=["date", "analyte", "value",
                                               "flag", "ref", "n_sheets",
                                               "conflict", "sources"])
    w.writeheader()
    w.writerows(out)
    print(f"{len(files)} pdfs -> {len(out)} (date, analyte) pairs, "
          f"{sum(1 for r in out if r['conflict'])} conflicts", file=sys.stderr)
    for u in empty:
        print(f"  ! nothing extracted: {u}", file=sys.stderr)


if __name__ == "__main__":       # importable: build_db.py reuses this parser
    main()

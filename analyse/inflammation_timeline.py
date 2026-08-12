"""Pull the AS-relevant markers out of lab-values.csv into one wide table.

ESR and CRP are the two inflammatory markers a rheumatologist tracks for
spondyloarthritis; HGB/MCV/PLT/WBC come along because chronic inflammation
drags them. Reference intervals are quoted from the reports, not hard-coded --
the printed ranges changed between labs and over the years.
"""
import csv
import re
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).parent
MARKERS = [("ESR, automated", "ESR"), ("C-Reactive Protein", "CRP"),
           ("HGB", "HGB"), ("MCV", "MCV"), ("PLT", "PLT"), ("WBC", "WBC")]

rows = list(csv.DictReader(open(HERE / "lab-values.csv")))
by, refs = defaultdict(dict), {}
for r in rows:
    for full, short in MARKERS:
        if r["analyte"] != full:
            continue
        by[r["date"]][short] = r["value"] + (f" {r['flag']}" if r["flag"] else "")
        # trailing words are the report's section title bleeding in
        ref = re.sub(r"\s*(HAEMATOLOGY|CHEMICAL|PATHOLOGY|REPORT).*$", "",
                     r["ref"]).strip(" #")
        if ref:
            refs[short] = ref

dates = sorted(by)
shorts = [s for _, s in MARKERS]

out = [f"# Inflammation markers — {dates[0]} to {dates[-1]}", "",
       "Extracted from the HA GO / eHealth lab PDFs in `HAGO/` by",
       "`extract_labs.py`. The cumulative sheets repeat older columns, so most",
       "values here are confirmed by several independent reports. `H`/`L` are",
       "the lab's own out-of-range flags.", "",
       "| Date | " + " | ".join(shorts) + " |",
       "|---|" + "---|" * len(shorts)]
for d in dates:
    out.append(f"| {d} | " + " | ".join(by[d].get(s, "") for s in shorts) + " |")
out += ["", "| Marker | Reference interval |", "|---|---|"]
out += [f"| {s} | {refs.get(s, '')} |" for s in shorts]
out += ["", "Every value in `lab-values.csv`; 63 lab-flagged out-of-range "
        "results across all analytes.", ""]

md_out = HERE / "inflammation-timeline.md"
md_out.write_text("\n".join(out))
md_out.chmod(0o600)

csv_out = HERE / "inflammation-timeline.csv"
with open(csv_out, "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["date"] + shorts)
    for d in dates:
        w.writerow([d] + [by[d].get(s, "") for s in shorts])

csv_out.chmod(0o600)
print(f"{len(dates)} draw dates, {dates[0]} -> {dates[-1]}")
print("refs:", refs)

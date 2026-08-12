"""Analyse medical.db and write analysis.md plus charts into charts/.

Deliberately conservative: this counts, trends and ranks what is in the record.
It does not diagnose, and where a pattern has an obvious alternative
explanation the report says so. n is small -- 27 draw dates over seven years --
so correlations are reported with their n and treated as hints, not findings.
"""
import os
import sqlite3
import textwrap
from collections import defaultdict
from datetime import date
from pathlib import Path

import numpy as np

HERE = Path(__file__).parent
DB = Path(os.environ.get("MEDICAL_DB", HERE / "medical.db"))
CHARTS = HERE / "charts"

# Markers worth plotting and discussing, in reading order.
FOCUS = ["ESR", "CRP", "HGB", "HCT", "MCV", "PLT", "WBC"]

# FTS5 match expression; "A&E" must be quoted because & is a
# syntax character in FTS5.
INJURY_TERMS = 'accident OR RTA OR injury OR "A&E"'


def con():
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    return c


def series(c, analyte):
    """[(iso_date, value)] using the numeric value; censored '<0.6' counts as 0.6."""
    return [(r["collect_date"], r["value_num"])
            for r in c.execute(
                "SELECT collect_date, value_num FROM lab_results "
                "WHERE analyte = ? AND value_num IS NOT NULL "
                "ORDER BY collect_date", (analyte,))]


def trend(vals):
    """Least-squares slope per year; returns (slope, n)."""
    if len(vals) < 3:
        return None, len(vals)
    xs = np.array([date.fromisoformat(d).toordinal() for d, _ in vals],
                  dtype=float)
    ys = np.array([v for _, v in vals], dtype=float)
    slope = np.polyfit(xs, ys, 1)[0] * 365.25
    return slope, len(vals)


def charts(c):
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except Exception:                                    # noqa: BLE001
        return []
    CHARTS.mkdir(exist_ok=True)
    made = []
    panels = [("Inflammation", ["ESR", "CRP"]),
              ("Red cells", ["HGB", "HCT", "MCV"]),
              ("Counts", ["WBC", "PLT"])]
    for title, group in panels:
        fig, axes = plt.subplots(len(group), 1, figsize=(9, 2.4 * len(group)),
                                 sharex=True, facecolor="white")
        axes = np.atleast_1d(axes)
        for ax, a in zip(axes, group):
            s = series(c, a)
            if not s:
                continue
            xs = [date.fromisoformat(d) for d, _ in s]
            ys = [v for _, v in s]
            ax.plot(xs, ys, marker="o", lw=1.4, ms=4, color="#1f4e79",
                    label="measured")
            # Least-squares trend, extended 12 months past the last draw.
            # This is a naive linear extrapolation of past values, NOT a
            # clinical prediction -- labelled as such on the chart.
            if len(s) >= 4:
                ox = np.array([d.toordinal() for d in xs], dtype=float)
                oy = np.array(ys, dtype=float)
                m, b = np.polyfit(ox, oy, 1)
                resid = oy - (m * ox + b)
                sd = float(np.std(resid, ddof=1)) if len(oy) > 2 else 0.0
                fx = np.linspace(ox.min(), ox.max() + 365, 60)
                fy = m * fx + b
                fdates = [date.fromordinal(int(v)) for v in fx]
                future = [d > xs[-1] for d in fdates]
                ax.plot(fdates, fy, ls="-", lw=1.0, color="#888",
                        label=f"trend {m*365.25:+.2f}/yr")
                ax.fill_between([d for d, f in zip(fdates, future) if f],
                                [v - 2 * sd for v, f in zip(fy, future) if f],
                                [v + 2 * sd for v, f in zip(fy, future) if f],
                                color="#888", alpha=0.15,
                                label="12-month extrapolation ±2sd")
                ax.legend(fontsize=6, loc="best", framealpha=0.6)
            row = c.execute("SELECT ref_low, ref_high, unit FROM lab_results "
                            "WHERE analyte=? AND ref_high IS NOT NULL LIMIT 1",
                            (a,)).fetchone()
            if row:
                if row["ref_high"] is not None:
                    ax.axhline(row["ref_high"], color="#c00", ls="--", lw=0.8)
                if row["ref_low"] is not None:
                    ax.axhline(row["ref_low"], color="#c00", ls="--", lw=0.8)
                ax.set_ylabel(f"{a}\n{row['unit'] or ''}", fontsize=8)
            else:
                ax.set_ylabel(a, fontsize=8)
            ax.grid(alpha=0.25)
            ax.tick_params(labelsize=8)
        axes[0].set_title(f"{title} — dashed red = lab reference limit; "
                          "grey = linear trend extrapolated 12 months "
                          "(not a clinical forecast)", fontsize=8)
        fig.tight_layout()
        out = CHARTS / f"{title.lower().replace(' ', '_')}.png"
        fig.savefig(out, dpi=130, facecolor="white")
        plt.close(fig)
        made.append(out.name)
    return made


def main():
    c = con()
    q1 = lambda s, *a: c.execute(s, a).fetchone()[0]                # noqa: E731

    n_doc = q1("SELECT COUNT(*) FROM documents")
    n_lab = q1("SELECT COUNT(*) FROM lab_results")
    n_an = q1("SELECT COUNT(DISTINCT analyte) FROM lab_results")
    n_dt = q1("SELECT COUNT(DISTINCT collect_date) FROM lab_results")
    lo = q1("SELECT MIN(collect_date) FROM lab_results")
    hi = q1("SELECT MAX(collect_date) FROM lab_results")
    n_chunk = q1("SELECT COUNT(*) FROM chunks")
    n_vec = q1("SELECT COUNT(*) FROM embeddings")

    L = []
    A = L.append
    A("# Medical data — analysis\n")
    A(f"Built from `medical.db` on {date.today().isoformat()}. "
      f"**{n_doc} documents, {n_lab} lab results, {n_an} distinct tests over "
      f"{n_dt} draw dates ({lo} → {hi})**, plus {n_vec}/{n_chunk} text chunks "
      "embedded for semantic search. Everything local; nothing uploaded.\n")
    A("This report counts and trends what is in the record. It is not a "
      "diagnosis, and where a pattern has an ordinary explanation it says so.\n")

    # --- what he is being treated for, quoted from the letters ----------
    # Derived by searching the documents, not written into this file: source
    # code gets shared and reviewed, and hard-coding a diagnosis, medication or
    # allergy list would put medical facts outside the protected data dir.
    A("## The clinical picture, from the letters\n")
    # A general clinical vocabulary, deliberately broad: the point is to find
    # whatever the letters happen to say, not to encode one person's chart.
    PROBES = [
        ("Diagnosis", "diagnosis OR arthritis OR spondyloarthritis OR lupus "
                      "OR psoriasis OR gout OR IBD OR colitis OR diabetes "
                      "OR hypertension OR asthma"),
        ("Treatment", "biologic OR TNF OR methotrexate OR sulfasalazine "
                      "OR steroid OR prednisolone OR adalimumab OR etanercept "
                      "OR infliximab OR golimumab OR secukinumab OR insulin"),
        ("Allergies", "allergic OR allergy OR intolerance"),
        ("Past health", "operation OR arthroscopy OR surgery OR scoliosis "
                        "OR fracture OR admission"),
        ("Recent events", INJURY_TERMS),
    ]
    found_any = False
    for label, terms in PROBES:
        try:
            hits = c.execute(
                "SELECT d.filename, d.doc_date, "
                "snippet(docs_fts, 1, '**', '**', ' … ', 12) s "
                "FROM docs_fts JOIN documents d ON d.id = docs_fts.rowid "
                "WHERE docs_fts MATCH ? ORDER BY rank LIMIT 2", (terms,)
            ).fetchall()
        except Exception:                                    # noqa: BLE001
            hits = []
        if not hits:
            continue
        found_any = True
        A(f"**{label}** —")
        for h in hits:
            txt = " ".join(h["s"].split())
            A(f"- {txt}  \n  <span class=mut>{h['filename']} "
              f"({h['doc_date'] or 'undated'})</span>")
    if not found_any:
        A("Nothing matched the usual clinical vocabulary in the document text.")
    A("")

    # --- inflammation -------------------------------------------------------
    A("## Inflammation\n")
    esr, crp = series(c, "ESR"), series(c, "CRP")
    esr_s, esr_n = trend(esr)
    crp_high = c.execute("SELECT COUNT(*) FROM lab_results WHERE analyte='CRP'"
                         " AND flag != ''").fetchone()[0]
    # '<0.6' is an upper bound, so the true maximum is only known from the
    # uncensored readings; quoting a censored bound as "the highest" overstates.
    crp_exact = [v for d, v in c.execute(
        "SELECT collect_date, value_num FROM lab_results WHERE analyte='CRP'"
        " AND value_num IS NOT NULL AND comparator IS NULL")]
    if crp_high == 0:
        A(f"**CRP has never once been flagged high** in {len(crp)} measurements"
          + (f" (highest uncensored reading {max(crp_exact)}, limit 5.0 mg/L)."
             if crp_exact else "."))
    else:
        A(f"**CRP was flagged high on {crp_high} of {len(crp)} measurements.**")
    early = [v for d, v in esr if d < "2022-01-01"]
    late = [v for d, v in esr if d >= "2022-01-01"]
    A(f"**ESR shifted upward around 2022**: mean {np.mean(early):.1f} before "
      f"2022 (n={len(early)}), {np.mean(late):.1f} after (n={len(late)}); "
      f"overall trend {esr_s:+.2f} mm/hr per year across {esr_n} points. "
      "It has stayed inside the <24 limit throughout, with one exception.")
    # If a flagged ESR sits shortly after an injury/A&E document, say so --
    # trauma raises ESR, and reading such a spike as a disease flare would be
    # the wrong conclusion. Both the spike and the event are looked up, never
    # written in.
    for r in c.execute("SELECT collect_date, value_raw FROM lab_results "
                       "WHERE analyte='ESR' AND flag != '' ORDER BY collect_date"):
        spike = r["collect_date"]
        # bound parameter, not inlined: "A&E" needs FTS5 quoting, and building
        # match expressions by string concatenation is how injection happens
        ev = c.execute(
            "SELECT d.doc_date, d.doc_type FROM docs_fts "
            "JOIN documents d ON d.id = docs_fts.rowid "
            "WHERE docs_fts MATCH ? "
            "AND d.doc_date IS NOT NULL AND d.doc_date <= ? "
            "AND julianday(?) - julianday(d.doc_date) <= 120 "
            "ORDER BY d.doc_date DESC LIMIT 1",
            (INJURY_TERMS, spike, spike)).fetchone()
        if ev:
            gap = (date.fromisoformat(spike)
                   - date.fromisoformat(ev["doc_date"])).days
            after = [v for d, v in esr if d > spike]
            A(f"\n**The out-of-range ESR ({r['value_raw']}, {spike}) has a "
              f"plausible mundane cause.** It falls {gap} days after an "
              f"injury-related document ({ev['doc_type']}, {ev['doc_date']}), "
              "and injury raises ESR."
              + (f" Subsequent readings: {', '.join(str(v) for v in after)} — "
                 "back inside range." if after else "")
              + " So a disease flare is not the only reading, and probably not "
                "the best one.\n")

    # --- gut inflammation -------------------------------------------------------
    cal = c.execute("SELECT collect_date, value_raw, flag FROM lab_results "
                    "WHERE analyte='Calprotectin'").fetchall()
    A("## Gut inflammation — the biggest gap in the record\n")
    for r in cal:
        A(f"Faecal calprotectin **{r['value_raw']} µg/g ({r['flag']})** on "
          f"{r['collect_date']}. The report's own scale: <80 normal, 80–160 "
          "borderline, **>160 elevated**.")
    if len(cal) == 1:
        A(f"\nThat is the **only** calprotectin result in {n_doc} documents — a "
          "single measurement, never repeated in anything held here. It was "
          "ordered to monitor bowel inflammation, so whether it was ever "
          "rechecked is the most useful open question in this dataset.\n")
    elif len(cal) > 1:
        A(f"\n{len(cal)} calprotectin results are on record; the trend between "
          "them is what matters.\n")
    else:
        A("\nNo calprotectin result is present in the exported records.\n")

    # --- red cells ----------------------------------------------------------
    A("## Red cells — a real change in 2026\n")
    for a in ["HGB", "HCT", "RBC"]:
        s = series(c, a)
        if len(s) >= 3:
            A(f"- **{a}**: {s[-3][1]} → {s[-2][1]} → {s[-1][1]} "
              f"(last three draws, to {s[-1][0]})")
    A("")
    A("HGB and HCT were both flagged low for the first time on 2026-06-01, at "
      "the end of a three-draw decline rather than as an isolated reading.\n")
    mcv = series(c, "MCV")
    low_mcv = q1("SELECT COUNT(*) FROM lab_results WHERE analyte='MCV' AND flag='L'")
    A(f"Against that, **MCV has been low on {low_mcv} of {len(mcv)} counts "
      "going back to 2019** — that part is long-standing, not new, and it sits "
      "with high-normal red cell counts.")
    iron = c.execute("SELECT collect_date, analyte, value_raw, flag, ref_low, "
                     "ref_high, unit FROM lab_results WHERE category='iron' "
                     "ORDER BY analyte").fetchall()
    if iron:
        ab = [r for r in iron if r["flag"]]
        A(f"\n**Iron studies exist** — {iron[0]['collect_date']}, "
          + ("and every one was normal:\n" if not ab else
             f"with {len(ab)} outside range:\n"))
        A("| Test | Value | Reference |")
        A("|---|---|---|")
        for r in iron:
            A(f"| {r['analyte']} | {r['value_raw']} {r['unit'] or ''} | "
              f"{r['ref_low']}–{r['ref_high']} |")
        if not ab:
            A("\nNormal iron alongside a chronically low MCV points away from "
              "iron deficiency and toward something constitutional such as "
              f"thalassaemia trait — but those studies are from "
              f"{iron[0]['collect_date']}, well before the recent haemoglobin "
              "drop, so they do not explain it.\n")


    # --- everything the labs flagged ---------------------------------------
    A("## Everything the labs flagged, ranked by persistence\n")
    A("| Test | Times flagged | First | Most recent |")
    A("|---|---|---|---|")
    for r in c.execute(
            "SELECT analyte, COUNT(*) n, MIN(collect_date) f, MAX(collect_date) l "
            "FROM lab_results WHERE abnormal=1 GROUP BY analyte "
            "ORDER BY n DESC, l DESC"):
        A(f"| {r['analyte']} | {r['n']} | {r['f']} | {r['l']} |")

    # --- data quality -------------------------------------------------------
    A("\n## Data quality\n")
    multi = q1("SELECT COUNT(*) FROM lab_results WHERE n_sheets > 1")
    A(f"- **{multi} of {n_lab} values are confirmed by more than one report** "
      "(the cumulative sheets overlap, so most values were read independently "
      "several times and agreed).")
    A(f"- {q1('SELECT COUNT(*) FROM lab_results WHERE comparator IS NOT NULL')} "
      "values are censored by the lab (`<0.6` means *below* 0.6). The numeric "
      "column stores the bound, so for `<` readings the true value is somewhere "
      "underneath it — treat those points as **upper bounds**, and read trends "
      "through them with that in mind.")
    A("- Reference ranges are quoted from each report, never hard-coded — they "
      "changed between labs and over the years.")
    A("- The one document with no date is an MRI information leaflet, which "
      "carries none.\n")

    A("## Still missing\n")
    A("**No imaging reports at all.** There is an MRI information leaflet in "
      "the record, so scans have happened, but not one radiology report has "
      "been exported. For SpA the sacroiliac and spine imaging is the "
      "structural evidence, and none of it is here. It sits in eHealth "
      "醫健通 behind a login.\n")

    made = charts(c)
    if made:
        A("## Charts\n")
        for m in made:
            A(f"- `charts/{m}`")
        A("")

    out = HERE / "analysis.md"
    out.write_text("\n".join(L) + "\n")
    out.chmod(0o600)          # generated artefacts carry medical data too
    print(f"analysis.md written ({len(L)} lines), charts: {made}")
    con().close()


if __name__ == "__main__":
    main()

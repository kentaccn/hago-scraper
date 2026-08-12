"""Query medical.db -- semantic search, keyword search, and lab lookups.

    python3 query.py ask   "gut inflammation"        # meaning-based (vectors)
    python3 query.py find  "calprotectin"            # exact words (FTS5)
    python3 query.py lab   ESR                       # one analyte over time
    python3 query.py on    2026-06-01                # everything from one draw
    python3 query.py flags                           # every out-of-range result
    python3 query.py sql   "SELECT ..."              # anything else

Semantic search is an exact cosine over unit vectors held in SQLite -- for this
corpus that is both faster and more accurate than an approximate index.
"""
import json
import os
import sqlite3
import sys
import textwrap
import urllib.request
from pathlib import Path

import numpy as np

DB = Path(os.environ.get("MEDICAL_DB",
                         Path(__file__).parent / "medical.db"))
HOST = os.environ.get("OLLAMA", "http://localhost:11434")
MODEL = "nomic-embed-text"


def con():
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    return c


def embed_query(text):
    req = urllib.request.Request(
        f"{HOST}/api/embed",
        data=json.dumps({"model": MODEL, "input": [text]}).encode(),
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as r:
        v = np.asarray(json.load(r)["embeddings"][0], dtype=np.float32)
    return v / (np.linalg.norm(v) or 1.0)


def ask(q, k=6):
    c = con()
    # Only compare vectors produced by the SAME model: mixing models of equal
    # dimension yields plausible-looking but meaningless rankings.
    rows = c.execute(
        "SELECT e.chunk_id, e.vec, e.dim, ch.text, d.filename, d.doc_date "
        "FROM embeddings e JOIN chunks ch ON ch.id = e.chunk_id "
        "JOIN documents d ON d.id = ch.doc_id WHERE e.model = ?",
        (MODEL,)).fetchall()
    if not rows:
        sys.exit(f"no embeddings for {MODEL} -- run embed_db.py")
    if len({r["dim"] for r in rows}) != 1:
        sys.exit("stored vectors have mixed dimensions -- rebuild embeddings")
    mat = np.frombuffer(b"".join(r["vec"] for r in rows),
                        dtype=np.float32).reshape(len(rows), rows[0]["dim"])
    scores = mat @ embed_query(q)
    for i in np.argsort(-scores)[:k]:
        r = rows[int(i)]
        print(f"\n[{scores[i]:.3f}] {r['filename']}  ({r['doc_date'] or 'undated'})")
        body = " ".join(r["text"].split())
        print(textwrap.fill(body[:420], 88, initial_indent="  ",
                            subsequent_indent="  "))


def find(q, k=10):
    for r in con().execute(
            "SELECT d.filename, d.doc_date, snippet(docs_fts, 1, '>>', '<<', ' ... ', 14) s "
            "FROM docs_fts JOIN documents d ON d.id = docs_fts.rowid "
            "WHERE docs_fts MATCH ? ORDER BY rank LIMIT ?", (q, k)):
        print(f"\n{r['filename']} ({r['doc_date'] or 'undated'})")
        print(textwrap.fill(" ".join(r["s"].split()), 88,
                            initial_indent="  ", subsequent_indent="  "))


def lab(analyte):
    rows = con().execute(
        "SELECT collect_date, value_raw, flag, unit, ref_low, ref_high, n_sheets "
        "FROM lab_results WHERE analyte = ? COLLATE NOCASE ORDER BY collect_date",
        (analyte,)).fetchall()
    if not rows:
        near = con().execute(
            "SELECT DISTINCT analyte FROM lab_results WHERE analyte LIKE ?",
            (f"%{analyte}%",)).fetchall()
        sys.exit(f"no such analyte. close matches: {[n[0] for n in near][:8]}")
    r0 = rows[0]
    print(f"{analyte}   ref {fmt_ref(r0['ref_low'], r0['ref_high'])} "
          f"{r0['unit'] or ''}   {len(rows)} results")
    for r in rows:
        bar = "#" * min(40, int(r["n_sheets"]))
        print(f"  {r['collect_date']}  {r['value_raw']:>8} {r['flag'] or ' '}  {bar}")


def fmt_ref(low, high):
    """'13.4-17.1' / '<24' / '>1.0' -- a one-sided range must not print as '-24'."""
    if low is not None and high is not None:
        return f"{low:g}-{high:g}"
    if high is not None:
        return f"<{high:g}"
    if low is not None:
        return f">{low:g}"
    return ""


def on(date):
    for r in con().execute(
            "SELECT analyte, value_raw, flag, unit, ref_low, ref_high, category "
            "FROM lab_results WHERE collect_date = ? ORDER BY category, analyte",
            (date,)):
        print(f"  {r['category'] or '':13} {r['analyte']:24} "
              f"{r['value_raw']:>8} {r['flag'] or ' '}  "
              f"({fmt_ref(r['ref_low'], r['ref_high'])} {r['unit'] or ''})")


def flags():
    for r in con().execute(
            "SELECT collect_date, analyte, value_raw, flag, unit, ref_low, ref_high "
            "FROM lab_results WHERE abnormal = 1 ORDER BY collect_date DESC"):
        print(f"  {r['collect_date']}  {r['analyte']:24} {r['value_raw']:>8} "
              f"{r['flag']}  ({fmt_ref(r['ref_low'], r['ref_high'])} {r['unit'] or ''})")


def sql(q):
    for r in con().execute(q):
        print(tuple(r))


CMDS = {"ask": ask, "find": find, "lab": lab, "on": on,
        "flags": lambda: flags(), "sql": sql}

if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] not in CMDS:
        sys.exit(__doc__)
    fn = CMDS[sys.argv[1]]
    fn(*sys.argv[2:]) if len(sys.argv) > 2 else fn()

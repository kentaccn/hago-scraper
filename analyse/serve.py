"""Serve a medical.db over HTTP — read-only, stdlib only.

    python3 serve.py

Where it listens is an explicit decision, because the payload is medical
records. `BIND_MODE` picks one of:

    tailscale   the tailnet address only (default). Private by construction.
    localhost   127.0.0.1 only — the right choice behind a Cloudflare Tunnel,
                an SSH tunnel, or any reverse proxy that terminates auth.
    lan         this machine's LAN address. Anyone on that network can reach
                it; only sensible on a network you control.
    any         every interface (0.0.0.0). Requires ALLOW_ANY_INTERFACE=1 as
                well, because on café or hotel wifi this publishes your
                records to strangers.

Or set BIND to an explicit address and skip the guesswork.

If AUTH_TOKEN is set, every request must carry it (Bearer header, `ht` cookie,
or `?token=` once, which then sets the cookie). Use it whenever the listener is
not already private — a Cloudflare Tunnel without Access in front of it is a
public URL.

GET only. Nothing is written. Set MEDICAL_DB to point at the database.
"""
import hmac
import html
import json
import os
import re
import sqlite3
import subprocess
import sys
import urllib.request
from datetime import date, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import numpy as np

import analytes

HERE = Path(__file__).parent
DB = Path(os.environ.get("MEDICAL_DB", HERE / "medical.db"))
PORT = int(os.environ.get("PORT", "8137"))
OLLAMA = os.environ.get("OLLAMA", "http://localhost:11434")
MODEL = os.environ.get("EMBED_MODEL", "nomic-embed-text")
# Optional shared secret. Required whenever the listener is not
# already private (a tunnel without Access in front is a public URL).
AUTH_TOKEN = os.environ.get("AUTH_TOKEN", "")

CSS = """
:root{--bg:#ffffff;--fg:#1a1a1a;--mut:#666;--line:#e3e3e0;--accent:#1f4e79;
      --bad:#b00020;--card:#fafaf8}
*{box-sizing:border-box}
html,body{background:var(--bg)}
body{margin:0;color:var(--fg);font:15px/1.55 -apple-system,
     BlinkMacSystemFont,"Segoe UI",Helvetica,Arial,sans-serif}
header{position:sticky;top:0;background:var(--bg);border-bottom:1px solid var(--line);
       padding:.7rem 1rem;display:flex;gap:.9rem;flex-wrap:wrap;align-items:center}
header a{color:var(--accent);text-decoration:none;font-weight:600}
main{max-width:940px;margin:0 auto;padding:1rem 1rem 4rem}
h1{font-size:1.25rem;margin:.4rem 0 1rem}h2{font-size:1.05rem;margin:1.6rem 0 .6rem}
table{border-collapse:collapse;width:100%;font-size:.9rem}
td,th{padding:.4rem .5rem;border-bottom:1px solid var(--line);text-align:left}
th{color:var(--mut);font-weight:600}
.bad{color:var(--bad);font-weight:700}
.card{background:var(--card);border:1px solid var(--line);border-radius:10px;
      padding:.8rem 1rem;margin:.6rem 0}
.mut{color:var(--mut);font-size:.85rem}
.zh{font-size:.9rem;color:#333}
input[type=search]{width:100%;padding:.6rem .7rem;font-size:1rem;border-radius:8px;
      border:1px solid var(--line);background:#fff;color:var(--fg)}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(160px,1fr));gap:.4rem}
.grid a{display:block;padding:.45rem .6rem;border:1px solid var(--line);
      border-radius:8px;text-decoration:none;color:var(--fg);background:var(--card)}
img{max-width:100%;height:auto;border:1px solid var(--line);border-radius:8px;
    background:#fff}
pre{white-space:pre-wrap;word-wrap:break-word;font-size:.82rem}
.wrap{overflow-x:auto}
svg{max-width:100%;height:auto;background:#fff}
"""

NAV = ("<header><a href='/'>Overview</a><a href='/labs'>Tests</a>"
       "<a href='/flags'>Abnormal</a><a href='/search'>Search</a>"
       "<a href='/analysis'>Analysis</a><a href='/docs'>Documents</a></header>")


def con():
    c = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    c.row_factory = sqlite3.Row
    return c


def page(title, body):
    return (f"<!doctype html><html><head><meta charset=utf-8>"
            f"<meta name=viewport content='width=device-width,initial-scale=1'>"
            f"<title>{html.escape(title)}</title><style>{CSS}</style></head>"
            f"<body>{NAV}<main><h1>{html.escape(title)}</h1>{body}</main>"
            f"</body></html>").encode()


def e(x):
    return html.escape(str(x if x is not None else ""))


def fmt_ref(low, high):
    if low is not None and high is not None:
        return f"{low:g}–{high:g}"
    if high is not None:
        return f"&lt;{high:g}"
    if low is not None:
        return f"&gt;{low:g}"
    return ""


def next_due(dates, today=None):
    """Suggest when this test would next fall due, from the interval history.

    This is descriptive, not clinical: it says "you have historically had this
    every N months, and the last one was X ago". Ordering the test is the
    doctor's call, so the wording never tells him to book one.
    """
    ds = sorted(date.fromisoformat(d) for d in dates)
    if len(ds) < 3:
        return None
    gaps = sorted((ds[i + 1] - ds[i]).days for i in range(len(ds) - 1))
    med = gaps[len(gaps) // 2]
    if med <= 0:
        return None
    today = today or date.today()
    due = ds[-1] + timedelta(days=med)
    return {"median_days": med, "last": ds[-1], "due": due,
            "overdue_days": (today - due).days}


def spark(points, ref_low, ref_high, unit, months=12):
    """Inline SVG: measured points, least-squares trend, and a 12-month linear
    extrapolation. The extrapolation is arithmetic, not a clinical forecast --
    it says where the line goes if nothing changes, nothing more."""
    pts = [(date.fromisoformat(d).toordinal(), v) for d, v in points
           if v is not None]
    if len(pts) < 2:
        return ""
    W, H, PAD_L, PAD_R, PAD_T, PAD_B = 880, 260, 52, 14, 16, 30
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    x_end = max(xs) + int(30.44 * months)
    lo_y = min(ys + [ref_low] if ref_low is not None else ys)
    hi_y = max(ys + [ref_high] if ref_high is not None else ys)
    trend = None
    if len(pts) >= 4:
        m, b = np.polyfit(np.array(xs, float), np.array(ys, float), 1)
        sd = float(np.std(np.array(ys, float)
                          - (m * np.array(xs, float) + b), ddof=1))
        trend = (m, b, sd)
        lo_y = min(lo_y, m * x_end + b - 2 * sd)
        hi_y = max(hi_y, m * x_end + b + 2 * sd)
    span_y = (hi_y - lo_y) or 1.0
    lo_y -= span_y * 0.08
    hi_y += span_y * 0.08
    span_x = (x_end - min(xs)) or 1

    def X(o):
        return PAD_L + (o - min(xs)) / span_x * (W - PAD_L - PAD_R)

    def Y(v):
        return PAD_T + (hi_y - v) / (hi_y - lo_y) * (H - PAD_T - PAD_B)

    o = [f"<svg viewBox='0 0 {W} {H}' xmlns='http://www.w3.org/2000/svg' "
         f"role='img'><rect width='{W}' height='{H}' fill='#fff'/>"]
    for lim, lab in ((ref_low, "low"), (ref_high, "high")):
        if lim is not None:
            o.append(f"<line x1='{PAD_L}' y1='{Y(lim):.1f}' x2='{W-PAD_R}' "
                     f"y2='{Y(lim):.1f}' stroke='#c00' stroke-width='1' "
                     f"stroke-dasharray='5 4'/>")
            o.append(f"<text x='{W-PAD_R}' y='{Y(lim)-4:.1f}' font-size='10' "
                     f"fill='#c00' text-anchor='end'>{lim:g}</text>")
    if trend:
        m, b, sd = trend
        x0, x1 = min(xs), x_end
        o.append(f"<path d='M {X(max(xs)):.1f} {Y(m*max(xs)+b+2*sd):.1f} "
                 f"L {X(x1):.1f} {Y(m*x1+b+2*sd):.1f} "
                 f"L {X(x1):.1f} {Y(m*x1+b-2*sd):.1f} "
                 f"L {X(max(xs)):.1f} {Y(m*max(xs)+b-2*sd):.1f} Z' "
                 f"fill='#999' opacity='0.16'/>")
        o.append(f"<line x1='{X(x0):.1f}' y1='{Y(m*x0+b):.1f}' "
                 f"x2='{X(x1):.1f}' y2='{Y(m*x1+b):.1f}' stroke='#888' "
                 f"stroke-width='1.2'/>")
    o.append("<polyline fill='none' stroke='#1f4e79' stroke-width='1.8' "
             "points='" + " ".join(f"{X(x):.1f},{Y(v):.1f}" for x, v in pts)
             + "'/>")
    for x, v in pts:
        o.append(f"<circle cx='{X(x):.1f}' cy='{Y(v):.1f}' r='3' "
                 f"fill='#1f4e79'/>")
    first, last = date.fromordinal(min(xs)), date.fromordinal(max(xs))
    o.append(f"<text x='{PAD_L}' y='{H-8}' font-size='10' fill='#666'>{first}</text>")
    o.append(f"<text x='{X(max(xs)):.1f}' y='{H-8}' font-size='10' fill='#666' "
             f"text-anchor='middle'>{last}</text>")
    o.append(f"<text x='{W-PAD_R}' y='{H-8}' font-size='10' fill='#666' "
             f"text-anchor='end'>+{months}m</text>")
    if trend:
        o.append(f"<text x='{PAD_L}' y='{PAD_T+2}' font-size='10' fill='#666'>"
                 f"trend {trend[0]*365.25:+.2f} {html.escape(unit or '')}/year"
                 f" · grey band = {months}-month extrapolation, not a forecast"
                 f"</text>")
    return "".join(o) + "</svg>"


def overview():
    c = con()
    g = lambda q: c.execute(q).fetchone()[0]                      # noqa: E731
    latest = g("SELECT MAX(collect_date) FROM lab_results")
    b = [f"<div class=card><b>{g('SELECT COUNT(*) FROM lab_results')}</b> lab results · "
         f"<b>{g('SELECT COUNT(DISTINCT analyte) FROM lab_results')}</b> tests · "
         f"<b>{g('SELECT COUNT(DISTINCT collect_date) FROM lab_results')}</b> draw dates · "
         f"<b>{g('SELECT COUNT(*) FROM documents')}</b> documents"
         f"<div class=mut>{g('SELECT MIN(collect_date) FROM lab_results')} → {latest}"
         f" · served read-only over Tailscale</div></div>"]
    b.append(f"<h2>Latest draw — {e(latest)}</h2><div class=wrap><table>"
             "<tr><th>Test</th><th>Value</th><th>Reference</th></tr>")
    for r in c.execute("SELECT analyte, value_raw, flag, unit, ref_low, ref_high "
                       "FROM lab_results WHERE collect_date=? "
                       "ORDER BY flag='' , category, analyte", (latest,)):
        cls = " class=bad" if r["flag"] else ""
        b.append(f"<tr><td><a href='/lab?a={e(r['analyte'])}'>{e(r['analyte'])}</a></td>"
                 f"<td{cls}>{e(r['value_raw'])} {e(r['flag'])}</td>"
                 f"<td class=mut>{fmt_ref(r['ref_low'], r['ref_high'])} {e(r['unit'])}</td></tr>")
    b.append("</table></div>")
    # Roll-up of what has drifted past its own historical interval. Descriptive
    # only -- the doctor decides what actually gets ordered.
    rows = c.execute("SELECT analyte, GROUP_CONCAT(collect_date) ds "
                     "FROM lab_results GROUP BY analyte").fetchall()
    over = []
    for r in rows:
        nd = next_due(r["ds"].split(","))
        if nd and nd["overdue_days"] > 60:
            over.append((nd["overdue_days"], r["analyte"], nd))
    if over:
        over.sort(reverse=True)
        b.append("<h2>Past their usual interval · 超過慣常檢查間隔</h2>"
                 "<div class=wrap><table><tr><th>Test</th><th>Last done</th>"
                 "<th>Usual interval</th><th>Overdue by</th></tr>")
        for days, a, nd in over[:12]:
            d = analytes.describe(a)
            zh = f" <span class=zh>{e(d[1])}</span>" if d else ""
            b.append(f"<tr><td><a href='/lab?a={e(a)}'>{e(a)}</a>{zh}</td>"
                     f"<td>{nd['last']}</td>"
                     f"<td class=mut>~{nd['median_days']/30.44:.0f} months</td>"
                     f"<td class=bad>{days/30.44:.0f} months</td></tr>")
        b.append("</table></div><div class=mut>Based on the gaps between your "
                 "own past tests, not a clinical schedule.</div>")
    b.append("<h2>Trends</h2>")
    for png in ("inflammation", "red_cells", "counts"):
        if (HERE / "charts" / f"{png}.png").exists():
            b.append(f"<img src='/charts/{png}.png' alt='{png}'>")
    return page("Medical overview", "".join(b))


def labs():
    rows = con().execute(
        "SELECT analyte, category, COUNT(*) n, MAX(collect_date) last, "
        "SUM(abnormal) ab FROM lab_results GROUP BY analyte "
        "ORDER BY category, analyte").fetchall()
    out, cat = [], None
    for r in rows:
        if r["category"] != cat:
            cat = r["category"]
            out.append(f"</div><h2>{e(cat or 'other')}</h2><div class=grid>")
        flag = f" <span class=bad>{r['ab']}</span>" if r["ab"] else ""
        d = analytes.describe(r["analyte"])
        zh = f"<div class=zh>{e(d[1])}</div>" if d else ""
        out.append(f"<a href='/lab?a={e(r['analyte'])}'>{e(r['analyte'])}{flag}"
                   f"{zh}<div class=mut>{r['n']} · {r['last']}</div></a>")
    return page("Tests", "".join(out)[6:] + "</div>")


def lab(a):
    rows = con().execute(
        "SELECT collect_date, value_raw, value_num, flag, unit, ref_low, ref_high,"
        " n_sheets, sources FROM lab_results WHERE analyte=? COLLATE NOCASE"
        " ORDER BY collect_date DESC", (a,)).fetchall()
    if not rows:
        return page("Not found", f"<p>No test named {e(a)}.</p>")
    r0 = rows[0]
    b = []
    d = analytes.describe(a)
    if d:
        en_name, zh_name, en_use, zh_use = d
        b.append(f"<div class=card><b>{e(en_name)}</b> · <b>{e(zh_name)}</b>"
                 f"<div style='margin-top:.4rem'>{e(en_use)}</div>"
                 f"<div class=zh style='margin-top:.3rem'>{e(zh_use)}</div></div>")
    b.append(f"<div class=card>Reference {fmt_ref(r0['ref_low'], r0['ref_high'])} "
             f"{e(r0['unit'])} · {len(rows)} results</div>")
    series = [(r["collect_date"], r["value_num"]) for r in reversed(rows)]
    nd = next_due([r["collect_date"] for r in rows])
    if nd:
        every = (f"{nd['median_days']/30.44:.0f} months"
                 if nd["median_days"] >= 45 else f"{nd['median_days']} days")
        every_zh = (f"約{nd['median_days']/30.44:.0f}個月"
                    if nd["median_days"] >= 45 else f"約{nd['median_days']}日")
        over_m = nd["overdue_days"] / 30.44
        if nd["overdue_days"] > 0:
            # The projected date is already in the past, so quoting it as "next"
            # is useless. Say it is due now and by how much it has slipped.
            head = "Due now — overdue"
            when = (f"On that rhythm it was due around <b>{nd['due']}</b>, "
                    f"which is <b>{over_m:.0f} months ago</b>. The last one was "
                    f"{nd['last']}.")
            when_zh = (f"按過往{every_zh}一次的頻率，早於 {nd['due']} 就應該再做，"
                       f"即係已經遲咗約 {over_m:.0f} 個月。"
                       f"最近一次係 {nd['last']}。")
            cls = " class=bad"
        else:
            head = "Next test"
            when = (f"On that rhythm the next one falls due around "
                    f"<b>{nd['due']}</b>, in about {abs(over_m):.0f} months. "
                    f"The last one was {nd['last']}.")
            when_zh = (f"按過往{every_zh}一次的頻率，下次大約喺 {nd['due']}，"
                       f"即係仲有大約 {abs(over_m):.0f} 個月。"
                       f"最近一次係 {nd['last']}。")
            cls = ""
        b.append(f"<div class=card><b{cls}>{head}</b> · <b{cls}>"
                 f"{'已逾期' if nd['overdue_days'] > 0 else '下次檢查'}</b>"
                 f"<div style='margin-top:.4rem'>{when}</div>"
                 f"<div class=zh style='margin-top:.3rem'>{when_zh}</div>"
                 f"<div class=mut style='margin-top:.3rem'>Based on the gaps "
                 f"between your own past tests, not a clinical schedule — worth "
                 f"raising at the next appointment. "
                 f"呢個只係按你過往檢查間隔推算，唔係醫生嘅安排，"
                 f"可以喺覆診時提出。</div></div>")
    b.append(spark(series, r0["ref_low"], r0["ref_high"], r0["unit"]))
    b.append('<div class=wrap><table>'
             "<tr><th>Date</th><th>Value</th><th>Confirmed by</th></tr>")
    for r in rows:
        cls = " class=bad" if r["flag"] else ""
        b.append(f"<tr><td>{e(r['collect_date'])}</td>"
                 f"<td{cls}>{e(r['value_raw'])} {e(r['flag'])}</td>"
                 f"<td class=mut>{r['n_sheets']}</td></tr>")
    b.append("</table></div>")
    b.append("<div class=mut style='margin-top:.5rem'><b>“Confirmed by”</b> = how "
             "many separate lab reports show this same number. Each sheet "
             "repeats up to five earlier collect dates, so a value often appears "
             "on several reports; 5 means five independent reports agree, 1 "
             "means only one report carries it. It is a check on the reading, "
             "not a count of blood draws."
             "<div class=zh style='margin-top:.3rem'>「確認次數」= 有幾多份"
             "化驗報告顯示同一個數值。每張化驗單會重複列出之前最多五次抽血日期，"
             "所以同一個結果通常會出現喺幾份報告上；5 即係五份報告都一致，"
             "1 即係只有一份。呢個係核對讀數用，唔係抽血次數。</div></div>")
    return page(a, "".join(b))


def flags_page():
    b = ["<div class=wrap><table><tr><th>Date</th><th>Test</th><th>Value</th>"
         "<th>Reference</th></tr>"]
    for r in con().execute(
            "SELECT collect_date, analyte, value_raw, flag, unit, ref_low, ref_high "
            "FROM lab_results WHERE abnormal=1 ORDER BY collect_date DESC"):
        b.append(f"<tr><td>{e(r['collect_date'])}</td>"
                 f"<td><a href='/lab?a={e(r['analyte'])}'>{e(r['analyte'])}</a></td>"
                 f"<td class=bad>{e(r['value_raw'])} {e(r['flag'])}</td>"
                 f"<td class=mut>{fmt_ref(r['ref_low'], r['ref_high'])} {e(r['unit'])}</td></tr>")
    return page("Out-of-range results", "".join(b) + "</table></div>")


def embed_query(text):
    req = urllib.request.Request(
        f"{OLLAMA}/api/embed",
        data=json.dumps({"model": MODEL, "input": [text]}).encode(),
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        v = np.asarray(json.load(r)["embeddings"][0], dtype=np.float32)
    return v / (np.linalg.norm(v) or 1.0)


def search(q):
    form = (f"<form method=get action='/search'><input type=search name=q "
            f"placeholder='e.g. inflammation, kidney function, a medication name' "
            f"value='{e(q)}' autofocus></form>")
    if not q:
        return page("Search", form + "<p class=mut>Meaning-based search over "
                    "every document, plus exact keyword matches.</p>")
    b = [form]
    c = con()
    try:
        # same-model only; mixing models silently degrades the ranking
        rows = c.execute(
            "SELECT e.vec, e.dim, ch.text, d.filename, d.doc_date, d.id did "
            "FROM embeddings e JOIN chunks ch ON ch.id=e.chunk_id "
            "JOIN documents d ON d.id=ch.doc_id WHERE e.model=?",
            (MODEL,)).fetchall()
        if not rows or len({r["dim"] for r in rows}) != 1:
            raise RuntimeError("no usable embeddings for " + MODEL)
        mat = np.frombuffer(b"".join(r["vec"] for r in rows),
                            dtype=np.float32).reshape(len(rows), rows[0]["dim"])
        scores = mat @ embed_query(q)
        b.append("<h2>By meaning</h2>")
        for i in np.argsort(-scores)[:6]:
            r = rows[int(i)]
            snippet = " ".join(r["text"].split())[:400]
            b.append(f"<div class=card><a href='/doc?id={r['did']}'>{e(r['filename'])}</a> "
                     f"<span class=mut>{e(r['doc_date'] or 'undated')} · "
                     f"{scores[i]:.2f}</span><div>{e(snippet)}…</div></div>")
    except Exception as ex:                                       # noqa: BLE001
        b.append(f"<p class=mut>Semantic search unavailable ({e(ex)}). "
                 "Is Ollama running?</p>")
    try:
        b.append("<h2>Exact matches</h2>")
        hits = c.execute(
            "SELECT d.id, d.filename, d.doc_date, "
            "snippet(docs_fts,1,'<b>','</b>',' … ',14) s "
            "FROM docs_fts JOIN documents d ON d.id=docs_fts.rowid "
            "WHERE docs_fts MATCH ? ORDER BY rank LIMIT 8", (q,)).fetchall()
        for r in hits:
            b.append(f"<div class=card><a href='/doc?id={r['id']}'>{e(r['filename'])}</a>"
                     f"<span class=mut> {e(r['doc_date'] or '')}</span>"
                     f"<div>{r['s']}</div></div>")
        if not hits:
            b.append("<p class=mut>No exact matches.</p>")
    except sqlite3.OperationalError:
        b.append("<p class=mut>(keyword syntax not valid)</p>")
    return page(f"Search — {q}", "".join(b))


def docs():
    b = ["<div class=wrap><table><tr><th>Date</th><th>Type</th><th>Site</th></tr>"]
    for r in con().execute("SELECT id, filename, doc_date, doc_type, site FROM "
                           "documents ORDER BY doc_date DESC"):
        b.append(f"<tr><td>{e(r['doc_date'] or '—')}</td>"
                 f"<td><a href='/doc?id={r['id']}'>{e(r['doc_type'])}</a></td>"
                 f"<td class=mut>{e(r['site'])}</td></tr>")
    return page("Documents", "".join(b) + "</table></div>")


def doc(i):
    r = con().execute("SELECT * FROM documents WHERE id=?", (i,)).fetchone()
    if not r:
        return page("Not found", "<p>No such document.</p>")
    return page(r["filename"],
                f"<div class=mut>{e(r['doc_date'] or 'undated')} · {e(r['site'])}</div>"
                f"<pre>{e(r['text'])}</pre>")


def md(path, title):
    if not path.exists():
        return page(title, "<p>Not generated yet.</p>")
    t = path.read_text()
    t = re.sub(r"^# .*\n", "", t, count=1)
    out, in_tbl = [], False
    for line in t.splitlines():
        if line.startswith("|"):
            cells = [c.strip() for c in line.strip("|").split("|")]
            if set("".join(cells)) <= set("-: "):
                continue
            tag = "td" if in_tbl else "th"
            if not in_tbl:
                out.append("<div class=wrap><table>")
                in_tbl = True
            out.append("<tr>" + "".join(f"<{tag}>{md_inline(c)}</{tag}>"
                                        for c in cells) + "</tr>")
            continue
        if in_tbl:
            out.append("</table></div>")
            in_tbl = False
        if line.startswith("## "):
            out.append(f"<h2>{e(line[3:])}</h2>")
        elif line.startswith("- "):
            out.append(f"<div>• {md_inline(line[2:])}</div>")
        elif line.strip():
            out.append(f"<p>{md_inline(line)}</p>")
    if in_tbl:
        out.append("</table></div>")
    return page(title, "".join(out))


def md_inline(s):
    s = e(s)
    s = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", s)
    s = re.sub(r"`(.+?)`", r"<code>\1</code>", s)
    return re.sub(r"\*(.+?)\*", r"<i>\1</i>", s)


class H(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *a):
        pass                                     # no request log of medical paths

    def send(self, body, ctype="text/html; charset=utf-8", code=200):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)

    def authorised(self, q):
        """Bearer header, `ht` cookie, or ?token= once. Constant-time compare."""
        if not AUTH_TOKEN:
            return True
        given = ""
        auth = self.headers.get("Authorization", "")
        if auth.startswith("Bearer "):
            given = auth[7:]
        if not given:
            for part in (self.headers.get("Cookie") or "").split(";"):
                k, _, v = part.strip().partition("=")
                if k == "ht":
                    given = v
        if not given:
            given = (q.get("token") or [""])[0]
        return hmac.compare_digest(given, AUTH_TOKEN)

    def do_GET(self):
        u = urlparse(self.path)
        q = parse_qs(u.query)
        if not self.authorised(q):
            body = page("Not authorised",
                        "<p>This instance requires a token. Append "
                        "<code>?token=…</code> once and it will be remembered "
                        "for this browser.</p>")
            self.send_response(401)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if AUTH_TOKEN and q.get("token"):
            # move the secret out of the URL bar and into a cookie
            self.send_response(302)
            self.send_header("Location", u.path or "/")
            self.send_header("Set-Cookie",
                             f"ht={AUTH_TOKEN}; Path=/; HttpOnly; SameSite=Lax"
                             + ("; Secure" if os.environ.get("BEHIND_TLS") else ""))
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        one = lambda k: (q.get(k) or [""])[0]                    # noqa: E731
        try:
            if u.path == "/":
                return self.send(overview())
            if u.path == "/labs":
                return self.send(labs())
            if u.path == "/lab":
                return self.send(lab(one("a")))
            if u.path == "/flags":
                return self.send(flags_page())
            if u.path == "/search":
                return self.send(search(one("q")))
            if u.path == "/docs":
                return self.send(docs())
            if u.path == "/doc":
                return self.send(doc(one("id")))
            if u.path == "/analysis":
                return self.send(md(HERE / "analysis.md", "Analysis"))
            if u.path.startswith("/charts/"):
                # only ever serve the generated PNGs, by exact name
                name = Path(u.path).name
                p = HERE / "charts" / name
                if p.suffix == ".png" and p.parent == HERE / "charts" and p.exists():
                    return self.send(p.read_bytes(), "image/png")
            self.send(page("Not found", "<p>No such page.</p>"), code=404)
        except Exception as ex:                                  # noqa: BLE001
            self.send(page("Error", f"<pre>{e(ex)}</pre>"), code=500)


def tailscale_ip():
    """The tailnet address, without depending on the `tailscale` CLI being on
    PATH — under launchd it is not. Tailscale hands out 100.64.0.0/10, so the
    interface list is the more reliable source."""
    try:
        out = subprocess.run(["ifconfig"], capture_output=True, text=True,
                             timeout=8).stdout
        for m in re.finditer(r"inet (100\.(\d+)\.\d+\.\d+)", out):
            if 64 <= int(m.group(2)) <= 127:      # the CGNAT range Tailscale uses
                return m.group(1)
    except Exception:                                            # noqa: BLE001
        pass
    for cmd in (["tailscale", "ip", "-4"],
                ["/Applications/Tailscale.app/Contents/MacOS/Tailscale",
                 "ip", "-4"]):
        try:
            out = subprocess.run(cmd, capture_output=True, text=True,
                                 timeout=8).stdout.strip().splitlines()
            if out and out[0].startswith("100."):
                return out[0]
        except Exception:                                        # noqa: BLE001
            pass
    return None


def lan_ip():
    """This machine's primary LAN address, or None."""
    import socket
    s_ = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s_.connect(("192.0.2.1", 9))     # TEST-NET-1; no packet is actually sent
        return s_.getsockname()[0]
    except Exception:                                            # noqa: BLE001
        return None
    finally:
        s_.close()


def resolve_bind():
    """(address, human explanation). Exits rather than binding somewhere the
    operator did not ask for."""
    explicit = os.environ.get("BIND")
    if explicit:
        return explicit, f"explicit BIND={explicit}"
    mode = os.environ.get("BIND_MODE", "tailscale").lower()
    if mode == "localhost":
        return "127.0.0.1", ("loopback only — reach it through a tunnel or "
                             "reverse proxy")
    if mode == "tailscale":
        ip = tailscale_ip()
        if not ip:
            sys.exit("BIND_MODE=tailscale but no tailnet address was found.\n"
                     "Refusing to fall back to a wider interface with medical "
                     "records on board.\nStart Tailscale, or choose "
                     "BIND_MODE=localhost / lan / any, or set BIND=<address>.")
        return ip, "tailnet address only"
    if mode == "lan":
        ip = lan_ip()
        if not ip:
            sys.exit("BIND_MODE=lan but no LAN address was found. Set BIND.")
        return ip, f"LAN address {ip} — everyone on this network can reach it"
    if mode == "any":
        if os.environ.get("ALLOW_ANY_INTERFACE") != "1":
            sys.exit("BIND_MODE=any exposes medical records on every interface, "
                     "including whatever wifi you are on.\nSet "
                     "ALLOW_ANY_INTERFACE=1 as well if you really mean it, and "
                     "set AUTH_TOKEN.")
        return "0.0.0.0", "EVERY interface — make sure AUTH_TOKEN is set"
    sys.exit(f"unknown BIND_MODE={mode!r} "
             "(tailscale | localhost | lan | any, or set BIND)")


if __name__ == "__main__":
    if not DB.exists():
        sys.exit(f"{DB} not found — run build_db.py first")
    addr, why = resolve_bind()
    shown = "127.0.0.1" if addr == "0.0.0.0" else addr
    if not AUTH_TOKEN and addr not in ("127.0.0.1",) and \
            not (addr.startswith("100.") or addr.startswith("127.")):
        print("WARNING: listening beyond loopback/tailnet with no AUTH_TOKEN set.",
              file=sys.stderr)
    print(f"{DB.name} -> http://{shown}:{PORT}  ({why}"
          + (", token required)" if AUTH_TOKEN else ")"))
    ThreadingHTTPServer((addr, PORT), H).serve_forever()

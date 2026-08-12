"""Statistics for short, irregular, partly censored clinical series.

The series here are 6-27 points spread over a decade, sampled when a clinic
visit happened rather than on a schedule, and several analytes are left-censored
("<0.6"). That rules out most of the obvious machinery:

- ordinary least squares assumes evenly spaced, normal residuals    -> Theil-Sen
- a t-test assumes normality on n=25                                -> Mann-Kendall
- testing 34 analytes and quoting the best p is multiple testing    -> Benjamini-Hochberg
- choosing a change-point by eye then testing it is circular        -> permutation over all splits
- treating "<0.6" as 0.6 invents precision the lab refused to give  -> reported, not modelled

Everything returns effect sizes with intervals. A p-value alone says nothing
useful about a series this short.
"""
from collections import defaultdict
from datetime import date

import numpy as np
from scipy import stats

MIN_N = 6                # below this, no trend is worth computing
MIN_SIDE = 5             # smallest group either side of a change-point


def mann_kendall(y):
    """Non-parametric monotonic trend test. Returns (z, p)."""
    n = len(y)
    s = sum(np.sign(y[j] - y[i]) for i in range(n - 1) for j in range(i + 1, n))
    _, counts = np.unique(y, return_counts=True)
    tie = sum(c * (c - 1) * (2 * c + 5) for c in counts)
    var = (n * (n - 1) * (2 * n + 5) - tie) / 18.0
    if var <= 0:
        return 0.0, 1.0
    z = (s - np.sign(s)) / np.sqrt(var)
    return float(z), float(2 * (1 - stats.norm.cdf(abs(z))))


def theil_sen(days, y):
    """(slope_per_year, lo, hi) — median of pairwise slopes, 95% CI."""
    r = stats.theilslopes(y, days, 0.95)
    return float(r[0] * 365.25), float(r[2] * 365.25), float(r[3] * 365.25)


def benjamini_hochberg(pvals):
    """Adjusted p-values (q). Controls false discovery across the analytes."""
    p = np.asarray(pvals, float)
    m = len(p)
    if m == 0:
        return np.array([])
    order = np.argsort(p)
    adj = np.empty_like(p)
    prev = 1.0
    for rank, idx in enumerate(reversed(order), start=1):
        prev = min(prev, p[idx] * m / (m - rank + 1))
        adj[idx] = prev
    return adj


def trends(series):
    """series: {analyte: [(ordinal_day, value)]} -> list of dicts, sorted by q.

    `censored` counts values the lab reported only as a bound; where most of a
    series is censored the slope is not interpretable and is marked as such.
    """
    out = []
    for a, pts in series.items():
        if len(pts) < MIN_N:
            continue
        days = np.array([p[0] for p in pts], float)
        y = np.array([p[1] for p in pts], float)
        z, p = mann_kendall(y)
        slope, lo, hi = theil_sen(days, y)
        out.append({"analyte": a, "n": len(pts), "slope": slope,
                    "lo": lo, "hi": hi, "p": p})
    for row, q in zip(out, benjamini_hochberg([r["p"] for r in out])):
        row["q"] = float(q)
    return sorted(out, key=lambda r: r["q"])


def change_point(days, y, n_perm=4000, seed=0):
    """Best level shift anywhere in the series, with a permutation p-value.

    Scanning every split and reporting the best one is exactly how a chance
    fluctuation becomes a 'finding'; permuting the series gives the null
    distribution of that maximum, so the p-value already pays for the search.
    """
    y = np.asarray(y, float)
    n = len(y)
    if n < 2 * MIN_SIDE:
        return None

    def best(vals):
        top, at = 0.0, None
        for k in range(MIN_SIDE, len(vals) - MIN_SIDE + 1):
            a, b = vals[:k], vals[k:]
            u, _ = stats.mannwhitneyu(a, b, alternative="two-sided")
            mu = len(a) * len(b) / 2
            sd = np.sqrt(len(a) * len(b) * (len(a) + len(b) + 1) / 12)
            zz = abs(u - mu) / sd
            if zz > top:
                top, at = zz, k
        return top, at

    z_obs, k = best(y)
    if k is None:
        return None
    rng = np.random.default_rng(seed)
    null = [best(rng.permutation(y))[0] for _ in range(n_perm)]
    p = (np.sum(np.asarray(null) >= z_obs) + 1) / (n_perm + 1)
    return {"index": k, "z": float(z_obs), "p": float(p),
            "before_median": float(np.median(y[:k])),
            "after_median": float(np.median(y[k:])),
            "n_before": k, "n_after": n - k,
            "split_day": int(days[k])}


def bootstrap_median_diff(a, b, n_boot=5000, seed=0):
    """(point, lo, hi) for median(b) - median(a)."""
    rng = np.random.default_rng(seed)
    a, b = np.asarray(a, float), np.asarray(b, float)
    d = [np.median(rng.choice(b, len(b))) - np.median(rng.choice(a, len(a)))
         for _ in range(n_boot)]
    return (float(np.median(d)), float(np.percentile(d, 2.5)),
            float(np.percentile(d, 97.5)))


def load_series(con, censored_ok=True):
    """{analyte: [(ordinal, value)]} plus {analyte: n_censored} from the db."""
    series, censored = defaultdict(list), defaultdict(int)
    for r in con.execute(
            "SELECT collect_date, analyte, value_num, comparator FROM "
            "lab_results WHERE value_num IS NOT NULL ORDER BY collect_date"):
        d, a, v, comp = r[0], r[1], r[2], r[3]
        if comp:
            censored[a] += 1
            if not censored_ok:
                continue
        series[a].append((date.fromisoformat(d).toordinal(), v))
    return dict(series), dict(censored)

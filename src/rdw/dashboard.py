"""Build a self-contained HTML dashboard (inline SVG, no external assets) from the analytics queries.

Backends:  --backend sqlite   local demo database (build/local/warehouse.sqlite)
           --backend redshift Redshift Serverless through the Data API
For a managed BI tool, connect Amazon QuickSight to the same tables (see README).
"""
import argparse
import html
import os
import sqlite3

from rdw.sqlfiles import parse_named_queries

W, H = 720, 260
PAD_L, PAD_R, PAD_T, PAD_B = 56, 12, 14, 34


def _fmt(n):
    n = float(n)
    for unit, div in (("B", 1e9), ("M", 1e6), ("K", 1e3)):
        if abs(n) >= div:
            return "%.1f%s" % (n / div, unit)
    return "%.0f" % n


def _month_label(ym):
    s = str(int(ym))
    return s[:4] + "-" + s[4:]


def bar_chart(labels, series, colors, every=3):
    """Grouped-overlay bars: first series full width, later series narrower on top."""
    top = max(max(s) for s in series) or 1
    n = len(labels)
    slot = (W - PAD_L - PAD_R) / n
    parts = []
    for i in range(5):
        y = PAD_T + (H - PAD_T - PAD_B) * i / 4
        val = top * (1 - i / 4)
        parts.append('<line x1="%d" x2="%d" y1="%.1f" y2="%.1f" class="grid"/>' % (PAD_L, W - PAD_R, y, y))
        parts.append('<text x="%d" y="%.1f" class="axis" text-anchor="end">%s</text>' % (PAD_L - 6, y + 4, _fmt(val)))
    for si, s in enumerate(series):
        bw = slot * (0.72 - 0.3 * si)
        for i, v in enumerate(s):
            h = (H - PAD_T - PAD_B) * v / top
            x = PAD_L + slot * i + (slot - bw) / 2
            parts.append('<rect x="%.1f" y="%.1f" width="%.1f" height="%.1f" fill="%s"/>'
                         % (x, H - PAD_B - h, bw, max(h, 0), colors[si]))
    for i, lab in enumerate(labels):
        if i % every == 0:
            parts.append('<text x="%.1f" y="%d" class="axis" text-anchor="middle">%s</text>'
                         % (PAD_L + slot * (i + 0.5), H - 12, html.escape(lab)))
    return '<svg viewBox="0 0 %d %d" role="img">%s</svg>' % (W, H, "".join(parts))


def line_chart(labels, values, color, ticks=6):
    top = max(values) or 1
    n = len(values)
    pts = []
    for i, v in enumerate(values):
        x = PAD_L + (W - PAD_L - PAD_R) * i / max(n - 1, 1)
        y = H - PAD_B - (H - PAD_T - PAD_B) * v / top
        pts.append("%.1f,%.1f" % (x, y))
    parts = []
    for i in range(5):
        y = PAD_T + (H - PAD_T - PAD_B) * i / 4
        parts.append('<line x1="%d" x2="%d" y1="%.1f" y2="%.1f" class="grid"/>' % (PAD_L, W - PAD_R, y, y))
        parts.append('<text x="%d" y="%.1f" class="axis" text-anchor="end">%s</text>' % (PAD_L - 6, y + 4, _fmt(top * (1 - i / 4))))
    parts.append('<polyline fill="none" stroke="%s" stroke-width="1.6" points="%s"/>' % (color, " ".join(pts)))
    for k in range(ticks):
        i = round((n - 1) * k / (ticks - 1))
        x = PAD_L + (W - PAD_L - PAD_R) * i / max(n - 1, 1)
        parts.append('<text x="%.1f" y="%d" class="axis" text-anchor="middle">%s</text>' % (x, H - 12, html.escape(str(labels[i])[:7])))
    return '<svg viewBox="0 0 %d %d" role="img">%s</svg>' % (W, H, "".join(parts))


def hbar_chart(labels, values, color):
    top = max(values) or 1
    row = 22
    h = PAD_T + row * len(values) + 8
    left = 200
    parts = []
    for i, (lab, v) in enumerate(zip(labels, values)):
        y = PAD_T + row * i
        bw = (W - left - 60) * v / top
        parts.append('<text x="%d" y="%d" class="axis" text-anchor="end">%s</text>' % (left - 8, y + 13, html.escape(lab)))
        parts.append('<rect x="%d" y="%d" width="%.1f" height="14" fill="%s"/>' % (left, y + 2, bw, color))
        parts.append('<text x="%.1f" y="%d" class="axis">%.1f%%</text>' % (left + bw + 6, y + 13, v))
    return '<svg viewBox="0 0 %d %d" role="img">%s</svg>' % (W, h, "".join(parts))


def build_html(results, subtitle):
    monthly = results["d1_monthly_kpis"]
    revenue = sum(float(r["revenue"]) for r in monthly)
    profit = sum(float(r["profit"]) for r in monthly)
    orders = sum(int(r["orders"]) for r in monthly)
    repeat = results["q5_repeat_purchase_rate"][0]
    pareto = results["q6_pareto_top_20_percent_products"][0]
    cats = sorted(results["q4_margin_by_category"], key=lambda r: -float(r["margin_pct"]))
    daily = results["q3_seven_day_moving_average"]

    kpis = [("Revenue", _fmt(revenue)), ("Profit", _fmt(profit)),
            ("Margin", "%.1f%%" % (100 * profit / revenue if revenue else 0)),
            ("Orders", _fmt(orders)),
            ("Repeat customers", "%.1f%%" % float(repeat["repeat_rate_pct"])),
            ("Top 20%% products", "%.1f%% of revenue" % float(pareto["top_20_percent_revenue_share_pct"]))]
    cards = "".join('<div class="kpi"><div class="v">%s</div><div class="l">%s</div></div>' % (html.escape(v), html.escape(l.replace("%%", "%")))
                    for l, v in kpis)
    labels = [_month_label(r["year_month"]) for r in monthly]
    c1 = bar_chart(labels, [[float(r["revenue"]) for r in monthly], [float(r["profit"]) for r in monthly]],
                   ["var(--rev)", "var(--profit)"])
    c2 = line_chart([str(r["full_date"]) for r in daily], [float(r["revenue_7d_avg"]) for r in daily], "var(--rev)")
    c3 = hbar_chart(["%s / %s" % (r["category"], r["subcategory"]) for r in cats[:10]],
                    [float(r["margin_pct"]) for r in cats[:10]], "var(--profit)")
    return """<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Retail Sales Warehouse Dashboard</title>
<style>
:root{--bg:#fff;--fg:#1d2433;--mut:#5b6577;--card:#f4f6fa;--grid:#d9dee8;--rev:#2f6fdb;--profit:#1f9d6b}
@media (prefers-color-scheme:dark){:root{--bg:#10141c;--fg:#e8ecf4;--mut:#9aa5b8;--card:#1a2030;--grid:#2c3447;--rev:#6ea2ff;--profit:#4cc79a}}
body{margin:0;padding:24px;background:var(--bg);color:var(--fg);font:14px/1.45 system-ui,Segoe UI,Arial,sans-serif;max-width:820px;margin:auto}
h1{font-size:20px;margin:0}.sub{color:var(--mut);margin:2px 0 16px}
.kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(120px,1fr));gap:10px;margin-bottom:18px}
.kpi{background:var(--card);border-radius:8px;padding:10px 12px}.kpi .v{font-size:18px;font-weight:600}.kpi .l{color:var(--mut);font-size:12px}
section{background:var(--card);border-radius:8px;padding:12px 14px;margin-bottom:14px}h2{font-size:14px;margin:0 0 6px}
svg{width:100%%;height:auto;display:block}.grid{stroke:var(--grid);stroke-width:1}.axis{fill:var(--mut);font-size:10px}
.legend span{display:inline-block;width:10px;height:10px;margin:0 4px 0 10px;border-radius:2px}
</style></head><body>
<h1>Retail Sales Warehouse</h1><div class="sub">%s</div>
<div class="kpis">%s</div>
<section><h2>Monthly revenue and profit</h2><div class="legend"><span style="background:var(--rev)"></span>Revenue<span style="background:var(--profit)"></span>Profit</div>%s</section>
<section><h2>Daily revenue, 7-day moving average</h2>%s</section>
<section><h2>Profit margin by category (top 10)</h2>%s</section>
</body></html>""" % (html.escape(subtitle), cards, c1, c2, c3)


def fetch_sqlite(db_path):
    from rdw.local import read_sql
    conn = sqlite3.connect(db_path)
    out = {}
    for name, stmt in parse_named_queries(read_sql("06_analytics.sql")).items():
        cur = conn.execute(stmt)
        cols = [d[0] for d in cur.description]
        out[name] = [dict(zip(cols, r)) for r in cur.fetchall()]
    return out


def fetch_redshift(workgroup, database):
    from rdw.local import read_sql
    from rdw.redshift_data import DataApi
    api = DataApi(workgroup, database)
    return {name: api.query(stmt) for name, stmt in parse_named_queries(read_sql("06_analytics.sql")).items()}


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--backend", choices=["sqlite", "redshift"], default="sqlite")
    ap.add_argument("--db", default="build/local/warehouse.sqlite")
    ap.add_argument("--workgroup")
    ap.add_argument("--database", default="dev")
    ap.add_argument("--out", default="build/dashboard.html")
    a = ap.parse_args()
    if a.backend == "sqlite":
        results, sub = fetch_sqlite(a.db), "SQLite demo (synthetic data)"
    else:
        if not a.workgroup:
            raise SystemExit("--workgroup is required for the redshift backend")
        results, sub = fetch_redshift(a.workgroup, a.database), "Amazon Redshift Serverless (synthetic data)"
    os.makedirs(os.path.dirname(a.out) or ".", exist_ok=True)
    with open(a.out, "w", encoding="utf-8") as fh:
        fh.write(build_html(results, sub))
    print("wrote", a.out)


if __name__ == "__main__":
    main()

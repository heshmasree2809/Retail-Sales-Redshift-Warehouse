"""Synthetic retail data generator (NOT real retailer data).

Writes the curated-zone layout the warehouse loads:
    <out>/curated/dim_date|dim_product|dim_store|dim_customer/part-0000.parquet
    <out>/curated/sales/sale_date=YYYY-MM-DD/*.parquet      (date-partitioned, like the Glue output)
Column ORDER and dtypes are part of the contract with sql/02_load.sql (Redshift maps Parquet by position).
A small share of deliberately bad rows is injected so the validation and reject path has work to do;
the exact expected reject counts are written to manifest.json.
"""
import argparse
import datetime as dt
import json
import os
import shutil

import numpy as np
import pandas as pd

SCHEMA = {
    "dim_date": [("date_key", "int32"), ("full_date", "date"), ("cal_year", "int32"), ("cal_quarter", "int32"),
                 ("cal_month", "int32"), ("month_name", "str"), ("year_month", "int32"), ("day_of_month", "int32"),
                 ("day_of_week", "int32"), ("day_name", "str"), ("is_weekend", "int32")],
    "dim_product": [("product_key", "int32"), ("sku", "str"), ("product_name", "str"), ("category", "str"),
                    ("subcategory", "str"), ("unit_cost", "float64"), ("unit_price", "float64")],
    "dim_store": [("store_key", "int32"), ("store_name", "str"), ("city", "str"), ("state", "str"),
                  ("region", "str"), ("store_type", "str")],
    "dim_customer": [("customer_key", "int32"), ("customer_id", "str"), ("segment", "str"), ("state", "str"),
                     ("signup_date", "date")],
    "sales": [("order_id", "int64"), ("line_number", "int32"), ("date_key", "int32"), ("product_key", "int32"),
              ("store_key", "int32"), ("customer_key", "int32"), ("quantity", "int32"), ("unit_price", "float64"),
              ("discount_pct", "int32")],
}
# table each curated prefix is loaded into
LOAD_TARGET = {"dim_date": "dim_date", "dim_product": "dim_product", "dim_store": "dim_store",
               "dim_customer": "dim_customer", "sales": "stg_sales"}

CATEGORIES = {
    # category: (subcategories, mean list price, (min, max) cost ratio)
    "Electronics": (["Phones", "Audio", "Computing", "Accessories"], 4200, (0.80, 0.92)),
    "Grocery": (["Staples", "Snacks", "Beverages", "Dairy"], 160, (0.72, 0.88)),
    "Apparel": (["Menswear", "Womenswear", "Kids", "Footwear"], 1100, (0.40, 0.62)),
    "Home & Kitchen": (["Cookware", "Furniture", "Decor", "Storage"], 900, (0.55, 0.75)),
    "Beauty": (["Skincare", "Haircare", "Fragrance"], 420, (0.35, 0.55)),
    "Sports": (["Fitness", "Outdoor", "Team Sports"], 1500, (0.55, 0.75)),
    "Toys": (["Games", "Learning", "Collectibles"], 600, (0.50, 0.70)),
    "Books": (["Fiction", "Non-fiction", "Academic"], 350, (0.60, 0.80)),
}
REGIONS = {"South": ["Andhra Pradesh", "Karnataka", "Tamil Nadu", "Telangana"],
           "West": ["Maharashtra", "Gujarat"], "North": ["Delhi", "Punjab", "Uttar Pradesh"],
           "East": ["West Bengal", "Odisha"]}
CITIES = {"Andhra Pradesh": ["Guntur", "Vijayawada", "Visakhapatnam"], "Karnataka": ["Bengaluru", "Mysuru"],
          "Tamil Nadu": ["Chennai", "Coimbatore"], "Telangana": ["Hyderabad", "Warangal"],
          "Maharashtra": ["Mumbai", "Pune"], "Gujarat": ["Ahmedabad", "Surat"], "Delhi": ["New Delhi"],
          "Punjab": ["Ludhiana"], "Uttar Pradesh": ["Lucknow", "Noida"], "West Bengal": ["Kolkata"],
          "Odisha": ["Bhubaneswar"]}
ORPHAN_PRODUCT, ORPHAN_STORE, ORPHAN_CUSTOMER, ORPHAN_DATE = 999999, 9999, 99999999, 20990101


def build_dim_date(start, end):
    days = pd.date_range(start, end, freq="D")
    return pd.DataFrame({
        "date_key": days.strftime("%Y%m%d").astype("int64"),
        "full_date": days.date,
        "cal_year": days.year, "cal_quarter": days.quarter, "cal_month": days.month,
        "month_name": days.strftime("%B"),
        "year_month": days.year * 100 + days.month,
        "day_of_month": days.day, "day_of_week": days.dayofweek + 1,
        "day_name": days.strftime("%A"),
        "is_weekend": (days.dayofweek >= 5).astype(int),
    })


def build_dim_product(rng, n=600):
    cats = list(CATEGORIES)
    rows = []
    for key in range(1, n + 1):
        cat = cats[(key - 1) % len(cats)]
        subs, mean_price, (lo, hi) = CATEGORIES[cat]
        sub = subs[rng.integers(len(subs))]
        price = round(float(rng.lognormal(np.log(mean_price), 0.5)), 2)
        cost = round(price * float(rng.uniform(lo, hi)), 2)
        rows.append((key, "SKU%05d" % key, "%s Item %04d" % (sub, key), cat, sub, cost, price))
    return pd.DataFrame(rows, columns=[c for c, _ in SCHEMA["dim_product"]])


def build_dim_store(rng, n=40):
    states = [(r, s) for r, ss in REGIONS.items() for s in ss]
    rows = []
    for key in range(1, n + 1):
        region, state = states[(key - 1) % len(states)]
        city = CITIES[state][rng.integers(len(CITIES[state]))]
        stype = ["Mall", "High Street", "Outlet"][rng.integers(3)]
        rows.append((key, "%s %s %02d" % (city, stype, key), city, state, region, stype))
    return pd.DataFrame(rows, columns=[c for c, _ in SCHEMA["dim_store"]])


def build_dim_customer(rng, n):
    states = [s for ss in REGIONS.values() for s in ss]
    keys = np.arange(1, n + 1)
    signup = pd.Timestamp("2020-01-01") + pd.to_timedelta(rng.integers(0, 1460, n), unit="D")
    return pd.DataFrame({
        "customer_key": keys,
        "customer_id": ["C%07d" % k for k in keys],
        "segment": rng.choice(["Regular", "Premium", "New"], n, p=[0.70, 0.12, 0.18]),
        "state": rng.choice(states, n),
        "signup_date": signup.date,
    })


def build_sales(rng, rows, dim_date, dim_product, n_stores, n_customers):
    sizes_p = np.array([0.35, 0.30, 0.17, 0.11, 0.07])  # mean 2.25 lines per order
    n_orders = int(rows / 2.25 * 1.1) + 10
    sizes = rng.choice(np.arange(1, 6), n_orders, p=sizes_p)
    order_ids = np.arange(1, n_orders + 1, dtype="int64") + 10_000_000
    lines = np.repeat(order_ids, sizes)[:rows]
    order_pos = np.repeat(np.arange(n_orders), sizes)[:rows]

    # seasonality: Nov/Dec peak, January dip, weekends busier
    month = dim_date["cal_month"].to_numpy()
    w = np.where(month >= 11, 1.4, np.where(month == 1, 0.85, 1.0)) * np.where(dim_date["is_weekend"] == 1, 1.25, 1.0)
    order_date = rng.choice(dim_date["date_key"].to_numpy(), n_orders, p=w / w.sum())
    order_store = rng.integers(1, n_stores + 1, n_orders)
    order_customer = rng.integers(1, n_customers + 1, n_orders)

    ranks = rng.permutation(len(dim_product)) + 1          # Zipf-like product popularity
    pop = 1.0 / ranks ** 0.9
    product_key = rng.choice(dim_product["product_key"].to_numpy(), rows, p=pop / pop.sum())
    price_by_key = dict(zip(dim_product["product_key"], dim_product["unit_price"]))

    df = pd.DataFrame({
        "order_id": lines,
        "line_number": 0,
        "date_key": order_date[order_pos],
        "product_key": product_key,
        "store_key": order_store[order_pos],
        "customer_key": order_customer[order_pos],
        "quantity": rng.choice([1, 2, 3, 4, 5], rows, p=[0.55, 0.25, 0.10, 0.06, 0.04]),
        "unit_price": [price_by_key[k] for k in product_key],
        "discount_pct": rng.choice([0, 0, 0, 5, 10, 15, 20], rows),
    })
    df["line_number"] = df.groupby("order_id").cumcount() + 1
    return df


def inject_bad_rows(rng, sales, bad_rate):
    """Mutate/append rows; return (frame, expected reject counts by reason)."""
    n_bad = int(len(sales) * bad_rate)
    if n_bad == 0:
        return sales, {}
    plan = {"non_positive_quantity": 0.35, "unknown_product": 0.15, "unknown_store": 0.10,
            "unknown_customer": 0.10, "unknown_date": 0.10, "duplicate_line": 0.20}
    counts = {k: int(n_bad * v) for k, v in plan.items()}
    mutate_total = sum(v for k, v in counts.items() if k != "duplicate_line")
    pool = rng.choice(len(sales), mutate_total + counts["duplicate_line"], replace=False)
    sales = sales.copy()
    pos = 0
    for reason in ("non_positive_quantity", "unknown_product", "unknown_store", "unknown_customer", "unknown_date"):
        idx = pool[pos:pos + counts[reason]]
        pos += counts[reason]
        if reason == "non_positive_quantity":
            sales.iloc[idx, sales.columns.get_loc("quantity")] = rng.choice([0, -1], len(idx))
        else:
            col, val = {"unknown_product": ("product_key", ORPHAN_PRODUCT), "unknown_store": ("store_key", ORPHAN_STORE),
                        "unknown_customer": ("customer_key", ORPHAN_CUSTOMER), "unknown_date": ("date_key", ORPHAN_DATE)}[reason]
            sales.iloc[idx, sales.columns.get_loc(col)] = val
    dup = sales.iloc[pool[pos:pos + counts["duplicate_line"]]]
    sales = pd.concat([sales, dup], ignore_index=True)
    return sales, counts


def _cast(df, table):
    out = pd.DataFrame()
    for col, kind in SCHEMA[table]:
        s = df[col]
        out[col] = s.astype({"int32": "int32", "int64": "int64", "float64": "float64"}[kind]) if kind in ("int32", "int64", "float64") else s
    return out


def write_tables(tables, out_dir, fmt):
    cur = os.path.join(out_dir, "curated")
    if fmt in ("parquet", "both"):
        try:
            import pyarrow  # noqa: F401
        except ImportError:
            raise SystemExit("Parquet output needs pyarrow: pip install -r requirements.txt")
        if os.path.isdir(cur):
            shutil.rmtree(cur)
        for name, df in tables.items():
            path = os.path.join(cur, name)
            os.makedirs(path, exist_ok=True)
            if name == "sales":
                part = df.copy()
                part["sale_date"] = pd.to_datetime(part["date_key"].astype(str), format="%Y%m%d", errors="coerce") \
                    .dt.strftime("%Y-%m-%d").fillna("1970-01-01")
                part.to_parquet(path, partition_cols=["sale_date"], index=False)
            else:
                df.to_parquet(os.path.join(path, "part-0000.parquet"), index=False)
    if fmt in ("csv", "both"):
        csv_dir = os.path.join(out_dir, "csv")
        os.makedirs(csv_dir, exist_ok=True)
        for name, df in tables.items():
            df.to_csv(os.path.join(csv_dir, name + ".csv"), index=False)


def generate(rows=1_000_000, out_dir="build/data", seed=42, bad_rate=0.005, fmt="parquet",
             start="2023-01-01", end="2024-12-31"):
    rng = np.random.default_rng(seed)
    n_customers = max(1000, rows // 3)
    dim_date = build_dim_date(start, end)
    dim_product = build_dim_product(rng)
    dim_store = build_dim_store(rng)
    dim_customer = build_dim_customer(rng, n_customers)
    sales = build_sales(rng, rows, dim_date, dim_product, len(dim_store), n_customers)
    sales, expected = inject_bad_rows(rng, sales, bad_rate)
    tables = {"dim_date": _cast(dim_date, "dim_date"), "dim_product": _cast(dim_product, "dim_product"),
              "dim_store": _cast(dim_store, "dim_store"), "dim_customer": _cast(dim_customer, "dim_customer"),
              "sales": _cast(sales, "sales")}
    os.makedirs(out_dir, exist_ok=True)
    write_tables(tables, out_dir, fmt)
    manifest = {"synthetic": True, "seed": seed, "sales_rows_written": int(len(sales)),
                "expected_rejects": expected, "expected_reject_total": int(sum(expected.values())),
                "date_range": [start, end]}
    with open(os.path.join(out_dir, "manifest.json"), "w") as fh:
        json.dump(manifest, fh, indent=2)
    return tables, manifest


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--rows", type=int, default=1_000_000)
    ap.add_argument("--out", default="build/data")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--bad-rate", type=float, default=0.005)
    ap.add_argument("--format", choices=["parquet", "csv", "both"], default="parquet")
    a = ap.parse_args()
    _, m = generate(a.rows, a.out, a.seed, a.bad_rate, a.format)
    print("wrote %d sales rows (synthetic) to %s; expected rejects: %d %s"
          % (m["sales_rows_written"], a.out, m["expected_reject_total"], m["expected_rejects"]))


if __name__ == "__main__":
    main()

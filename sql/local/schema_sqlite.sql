-- Local SQLite twin of 01_schema.sql, used only by the offline demo and tests.
-- tests/test_sql_contract.py fails if the column lists drift from the Redshift schema.

CREATE TABLE IF NOT EXISTS dim_date (
    date_key         INTEGER NOT NULL PRIMARY KEY,
    full_date        TEXT NOT NULL,
    cal_year         INTEGER NOT NULL,
    cal_quarter      INTEGER NOT NULL,
    cal_month        INTEGER NOT NULL,
    month_name       TEXT NOT NULL,
    year_month       INTEGER NOT NULL,
    day_of_month     INTEGER NOT NULL,
    day_of_week      INTEGER NOT NULL,
    day_name         TEXT NOT NULL,
    is_weekend       INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS dim_product (
    product_key      INTEGER NOT NULL PRIMARY KEY,
    sku              TEXT NOT NULL,
    product_name     TEXT NOT NULL,
    category         TEXT NOT NULL,
    subcategory      TEXT NOT NULL,
    unit_cost        REAL NOT NULL,
    unit_price       REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS dim_store (
    store_key        INTEGER NOT NULL PRIMARY KEY,
    store_name       TEXT NOT NULL,
    city             TEXT NOT NULL,
    state            TEXT NOT NULL,
    region           TEXT NOT NULL,
    store_type       TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS dim_customer (
    customer_key     INTEGER NOT NULL PRIMARY KEY,
    customer_id      TEXT NOT NULL,
    segment          TEXT NOT NULL,
    state            TEXT NOT NULL,
    signup_date      TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS stg_sales (
    row_id           INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id         INTEGER,
    line_number      INTEGER,
    date_key         INTEGER,
    product_key      INTEGER,
    store_key        INTEGER,
    customer_key     INTEGER,
    quantity         INTEGER,
    unit_price       REAL,
    discount_pct     INTEGER,
    reject_reason    TEXT
);

CREATE TABLE IF NOT EXISTS fact_sales (
    sales_key        INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id         INTEGER NOT NULL,
    line_number      INTEGER NOT NULL,
    date_key         INTEGER NOT NULL,
    product_key      INTEGER NOT NULL,
    store_key        INTEGER NOT NULL,
    customer_key     INTEGER NOT NULL,
    quantity         INTEGER NOT NULL,
    unit_price       NUMERIC NOT NULL,
    discount_pct     INTEGER NOT NULL,
    revenue          NUMERIC NOT NULL,
    cost             NUMERIC NOT NULL,
    profit           NUMERIC NOT NULL,
    UNIQUE (order_id, line_number)
);

CREATE TABLE IF NOT EXISTS sales_rejects (
    batch_id         TEXT,
    order_id         INTEGER,
    line_number      INTEGER,
    date_key         INTEGER,
    product_key      INTEGER,
    store_key        INTEGER,
    customer_key     INTEGER,
    quantity         INTEGER,
    unit_price       REAL,
    discount_pct     INTEGER,
    reject_reason    TEXT
);

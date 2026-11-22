-- Redshift schema: star schema + staging + rejects. Safe to re-run (IF NOT EXISTS).
-- Primary/foreign keys are informational in Redshift (the planner uses them, nothing enforces them);
-- integrity is enforced by 03_transform.sql and verified by 05_quality_checks.sql.

CREATE TABLE IF NOT EXISTS dim_date (
    date_key         INTEGER NOT NULL,
    full_date        DATE NOT NULL,
    cal_year         INTEGER NOT NULL,
    cal_quarter      INTEGER NOT NULL,
    cal_month        INTEGER NOT NULL,
    month_name       VARCHAR(12) NOT NULL,
    year_month       INTEGER NOT NULL,
    day_of_month     INTEGER NOT NULL,
    day_of_week      INTEGER NOT NULL,
    day_name         VARCHAR(12) NOT NULL,
    is_weekend       INTEGER NOT NULL,
    PRIMARY KEY (date_key)
) DISTSTYLE ALL SORTKEY (date_key);

CREATE TABLE IF NOT EXISTS dim_product (
    product_key      INTEGER NOT NULL,
    sku              VARCHAR(20) NOT NULL,
    product_name     VARCHAR(100) NOT NULL,
    category         VARCHAR(50) NOT NULL,
    subcategory      VARCHAR(50) NOT NULL,
    unit_cost        DOUBLE PRECISION NOT NULL,
    unit_price       DOUBLE PRECISION NOT NULL,
    PRIMARY KEY (product_key)
) DISTSTYLE ALL SORTKEY (product_key);

CREATE TABLE IF NOT EXISTS dim_store (
    store_key        INTEGER NOT NULL,
    store_name       VARCHAR(60) NOT NULL,
    city             VARCHAR(40) NOT NULL,
    state            VARCHAR(40) NOT NULL,
    region           VARCHAR(20) NOT NULL,
    store_type       VARCHAR(20) NOT NULL,
    PRIMARY KEY (store_key)
) DISTSTYLE ALL SORTKEY (store_key);

CREATE TABLE IF NOT EXISTS dim_customer (
    customer_key     INTEGER NOT NULL,
    customer_id      VARCHAR(20) NOT NULL,
    segment          VARCHAR(20) NOT NULL,
    state            VARCHAR(40) NOT NULL,
    signup_date      DATE NOT NULL,
    PRIMARY KEY (customer_key)
) DISTSTYLE KEY DISTKEY (customer_key) SORTKEY (customer_key);

-- Landing table for the curated Parquet. row_id and reject_reason are not in the files.
CREATE TABLE IF NOT EXISTS stg_sales (
    row_id           BIGINT IDENTITY(1,1),
    order_id         BIGINT,
    line_number      INTEGER,
    date_key         INTEGER,
    product_key      INTEGER,
    store_key        INTEGER,
    customer_key     INTEGER,
    quantity         INTEGER,
    unit_price       DOUBLE PRECISION,
    discount_pct     INTEGER,
    reject_reason    VARCHAR(40)
) DISTSTYLE EVEN;

-- Fact table at order-line grain. DISTKEY(product_key) co-locates rows for product rollups;
-- SORTKEY(date_key) lets date-range filters skip blocks via zone maps.
CREATE TABLE IF NOT EXISTS fact_sales (
    sales_key        BIGINT IDENTITY(1,1),
    order_id         BIGINT NOT NULL,
    line_number      INTEGER NOT NULL,
    date_key         INTEGER NOT NULL,
    product_key      INTEGER NOT NULL,
    store_key        INTEGER NOT NULL,
    customer_key     INTEGER NOT NULL,
    quantity         INTEGER NOT NULL,
    unit_price       DECIMAL(10,2) NOT NULL,
    discount_pct     INTEGER NOT NULL,
    revenue          DECIMAL(14,2) NOT NULL,
    cost             DECIMAL(14,2) NOT NULL,
    profit           DECIMAL(14,2) NOT NULL,
    PRIMARY KEY (order_id, line_number),
    FOREIGN KEY (date_key) REFERENCES dim_date (date_key),
    FOREIGN KEY (product_key) REFERENCES dim_product (product_key),
    FOREIGN KEY (store_key) REFERENCES dim_store (store_key),
    FOREIGN KEY (customer_key) REFERENCES dim_customer (customer_key)
) DISTSTYLE KEY DISTKEY (product_key) SORTKEY (date_key);

-- Rows that failed validation, kept per batch for review.
CREATE TABLE IF NOT EXISTS sales_rejects (
    batch_id         VARCHAR(80),
    order_id         BIGINT,
    line_number      INTEGER,
    date_key         INTEGER,
    product_key      INTEGER,
    store_key        INTEGER,
    customer_key     INTEGER,
    quantity         INTEGER,
    unit_price       DOUBLE PRECISION,
    discount_pct     INTEGER,
    reject_reason    VARCHAR(40)
) DISTSTYLE EVEN;

GRANT SELECT ON ALL TABLES IN SCHEMA public TO PUBLIC;

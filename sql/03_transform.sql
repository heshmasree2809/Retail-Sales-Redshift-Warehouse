-- Shared by Redshift and the local SQLite demo (keep it portable).
-- Validate staged rows (first matching rule wins), quarantine bad rows, merge good rows by date.

UPDATE stg_sales SET reject_reason = 'null_key'
WHERE reject_reason IS NULL
  AND (order_id IS NULL OR line_number IS NULL OR date_key IS NULL OR product_key IS NULL
       OR store_key IS NULL OR customer_key IS NULL OR quantity IS NULL OR unit_price IS NULL);

UPDATE stg_sales SET reject_reason = 'non_positive_quantity'
WHERE reject_reason IS NULL AND (quantity <= 0 OR unit_price <= 0);

UPDATE stg_sales SET reject_reason = 'unknown_date'
WHERE reject_reason IS NULL AND date_key NOT IN (SELECT date_key FROM dim_date);

UPDATE stg_sales SET reject_reason = 'unknown_product'
WHERE reject_reason IS NULL AND product_key NOT IN (SELECT product_key FROM dim_product);

UPDATE stg_sales SET reject_reason = 'unknown_store'
WHERE reject_reason IS NULL AND store_key NOT IN (SELECT store_key FROM dim_store);

UPDATE stg_sales SET reject_reason = 'unknown_customer'
WHERE reject_reason IS NULL AND customer_key NOT IN (SELECT customer_key FROM dim_customer);

UPDATE stg_sales SET reject_reason = 'duplicate_line'
WHERE row_id IN (
    SELECT row_id FROM (
        SELECT row_id,
               ROW_NUMBER() OVER (PARTITION BY order_id, line_number ORDER BY row_id) AS rn
        FROM stg_sales
        WHERE reject_reason IS NULL
    ) t
    WHERE t.rn > 1
);

DELETE FROM sales_rejects WHERE batch_id = '{{BATCH_ID}}';

INSERT INTO sales_rejects (batch_id, order_id, line_number, date_key, product_key, store_key, customer_key, quantity, unit_price, discount_pct, reject_reason)
SELECT '{{BATCH_ID}}', order_id, line_number, date_key, product_key, store_key, customer_key, quantity, unit_price, discount_pct, reject_reason
FROM stg_sales
WHERE reject_reason IS NOT NULL;

-- Idempotent by date: replace every date present in this batch, so a re-run never double counts.
DELETE FROM fact_sales
WHERE date_key IN (SELECT DISTINCT date_key FROM stg_sales WHERE reject_reason IS NULL);

INSERT INTO fact_sales (order_id, line_number, date_key, product_key, store_key, customer_key, quantity, unit_price, discount_pct, revenue, cost, profit)
SELECT order_id, line_number, date_key, product_key, store_key, customer_key, quantity,
       CAST(unit_price AS DECIMAL(10,2)), discount_pct,
       CAST(revenue AS DECIMAL(14,2)), CAST(cost AS DECIMAL(14,2)),
       CAST(revenue AS DECIMAL(14,2)) - CAST(cost AS DECIMAL(14,2))
FROM (
    SELECT s.order_id, s.line_number, s.date_key, s.product_key, s.store_key, s.customer_key,
           s.quantity, s.unit_price, s.discount_pct,
           ROUND(s.quantity * s.unit_price * (100 - s.discount_pct) / 100.0, 2) AS revenue,
           ROUND(s.quantity * p.unit_cost, 2) AS cost
    FROM stg_sales s
    JOIN dim_product p ON p.product_key = s.product_key
    WHERE s.reject_reason IS NULL
) x;

-- Shared. One result set: (check_name, failed_count). Any failed_count > 0 fails the pipeline.
SELECT 'fact_null_keys' AS check_name, COUNT(*) AS failed_count
FROM fact_sales
WHERE order_id IS NULL OR date_key IS NULL OR product_key IS NULL OR store_key IS NULL OR customer_key IS NULL
UNION ALL
SELECT 'fact_orphan_date', COUNT(*) FROM fact_sales f LEFT JOIN dim_date d ON d.date_key = f.date_key WHERE d.date_key IS NULL
UNION ALL
SELECT 'fact_orphan_product', COUNT(*) FROM fact_sales f LEFT JOIN dim_product p ON p.product_key = f.product_key WHERE p.product_key IS NULL
UNION ALL
SELECT 'fact_orphan_store', COUNT(*) FROM fact_sales f LEFT JOIN dim_store s ON s.store_key = f.store_key WHERE s.store_key IS NULL
UNION ALL
SELECT 'fact_orphan_customer', COUNT(*) FROM fact_sales f LEFT JOIN dim_customer c ON c.customer_key = f.customer_key WHERE c.customer_key IS NULL
UNION ALL
SELECT 'fact_duplicate_lines', COUNT(*)
FROM (SELECT order_id, line_number FROM fact_sales GROUP BY order_id, line_number HAVING COUNT(*) > 1) t
UNION ALL
SELECT 'fact_negative_amounts', COUNT(*) FROM fact_sales WHERE revenue < 0 OR cost < 0 OR quantity <= 0
UNION ALL
SELECT 'revenue_formula_mismatch', COUNT(*)
FROM fact_sales
WHERE ABS(CAST(revenue AS DOUBLE PRECISION) - ROUND(quantity * CAST(unit_price AS DOUBLE PRECISION) * (100 - discount_pct) / 100.0, 2)) > 0.01
UNION ALL
SELECT 'profit_identity_mismatch', COUNT(*)
FROM fact_sales
WHERE ABS(CAST(revenue AS DOUBLE PRECISION) - CAST(cost AS DOUBLE PRECISION) - CAST(profit AS DOUBLE PRECISION)) > 0.005
UNION ALL
SELECT 'staging_vs_fact_rowcount',
       ABS((SELECT COUNT(*) FROM stg_sales WHERE reject_reason IS NULL)
         - (SELECT COUNT(*) FROM fact_sales WHERE date_key IN (SELECT DISTINCT date_key FROM stg_sales WHERE reject_reason IS NULL)))
UNION ALL
SELECT 'reject_rate_over_5_percent',
       CASE WHEN (SELECT COUNT(*) FROM stg_sales WHERE reject_reason IS NOT NULL)
                 > 0.05 * (SELECT COUNT(*) FROM stg_sales) THEN 1 ELSE 0 END;

-- Redshift only. {{FACT}} is replaced with fact_sales (tuned) or fact_sales_untuned.
-- fact_sales: DISTKEY(product_key) SORTKEY(date_key). fact_sales_untuned: DISTSTYLE EVEN, sorted by load order.

-- name: b1_quarter_revenue_by_category_region
SELECT p.category, s.region, SUM(f.revenue) AS revenue, SUM(f.profit) AS profit
FROM {{FACT}} f
JOIN dim_product p ON p.product_key = f.product_key
JOIN dim_store s ON s.store_key = f.store_key
WHERE f.date_key BETWEEN 20241001 AND 20241231
GROUP BY p.category, s.region
ORDER BY revenue DESC;

-- name: b2_one_month_top_products
SELECT p.product_name, SUM(f.quantity) AS units, SUM(f.revenue) AS revenue
FROM {{FACT}} f
JOIN dim_product p ON p.product_key = f.product_key
WHERE f.date_key BETWEEN 20240601 AND 20240630
GROUP BY p.product_name
ORDER BY revenue DESC
LIMIT 20;

-- name: b3_full_scan_revenue_by_product
SELECT p.category, p.subcategory, COUNT(*) AS lines, SUM(f.revenue) AS revenue
FROM {{FACT}} f
JOIN dim_product p ON p.product_key = f.product_key
GROUP BY p.category, p.subcategory
ORDER BY revenue DESC;

-- Shared (Redshift + local SQLite). Named queries: "-- name: <id>" starts each one.

-- name: q1_top_products_per_store
WITH product_store AS (
    SELECT s.store_name, p.product_name, SUM(f.revenue) AS revenue
    FROM fact_sales f
    JOIN dim_store s ON s.store_key = f.store_key
    JOIN dim_product p ON p.product_key = f.product_key
    GROUP BY s.store_name, p.product_name
), ranked AS (
    SELECT store_name, product_name, revenue,
           RANK() OVER (PARTITION BY store_name ORDER BY revenue DESC) AS rnk
    FROM product_store
)
SELECT store_name, rnk, product_name, revenue
FROM ranked
WHERE rnk <= 3
ORDER BY store_name, rnk;

-- name: q2_month_over_month_growth
WITH monthly AS (
    SELECT d.year_month, SUM(f.revenue) AS revenue
    FROM fact_sales f
    JOIN dim_date d ON d.date_key = f.date_key
    GROUP BY d.year_month
), with_prev AS (
    SELECT year_month, revenue, LAG(revenue) OVER (ORDER BY year_month) AS prev_revenue
    FROM monthly
)
SELECT year_month, revenue, prev_revenue,
       ROUND(100.0 * (CAST(revenue AS DOUBLE PRECISION) - CAST(prev_revenue AS DOUBLE PRECISION))
             / NULLIF(CAST(prev_revenue AS DOUBLE PRECISION), 0), 2) AS mom_growth_pct
FROM with_prev
ORDER BY year_month;

-- name: q3_seven_day_moving_average
WITH daily AS (
    SELECT d.full_date, SUM(f.revenue) AS revenue
    FROM fact_sales f
    JOIN dim_date d ON d.date_key = f.date_key
    GROUP BY d.full_date
)
SELECT full_date, revenue,
       ROUND(AVG(CAST(revenue AS DOUBLE PRECISION))
             OVER (ORDER BY full_date ROWS BETWEEN 6 PRECEDING AND CURRENT ROW), 2) AS revenue_7d_avg
FROM daily
ORDER BY full_date;

-- name: q4_margin_by_category
SELECT p.category, p.subcategory,
       SUM(f.revenue) AS revenue, SUM(f.profit) AS profit,
       ROUND(100.0 * CAST(SUM(f.profit) AS DOUBLE PRECISION)
             / NULLIF(CAST(SUM(f.revenue) AS DOUBLE PRECISION), 0), 2) AS margin_pct
FROM fact_sales f
JOIN dim_product p ON p.product_key = f.product_key
GROUP BY p.category, p.subcategory
HAVING SUM(f.revenue) > 0
ORDER BY margin_pct DESC;

-- name: q5_repeat_purchase_rate
WITH cust AS (
    SELECT customer_key, COUNT(DISTINCT order_id) AS orders
    FROM fact_sales
    GROUP BY customer_key
)
SELECT COUNT(*) AS customers,
       SUM(CASE WHEN orders > 1 THEN 1 ELSE 0 END) AS repeat_customers,
       ROUND(100.0 * CAST(SUM(CASE WHEN orders > 1 THEN 1 ELSE 0 END) AS DOUBLE PRECISION) / COUNT(*), 2) AS repeat_rate_pct
FROM cust;

-- name: q6_pareto_top_20_percent_products
WITH prod AS (
    SELECT p.product_key, SUM(f.revenue) AS revenue
    FROM fact_sales f
    JOIN dim_product p ON p.product_key = f.product_key
    GROUP BY p.product_key
), ranked AS (
    SELECT revenue,
           ROW_NUMBER() OVER (ORDER BY revenue DESC) AS rn,
           COUNT(*) OVER () AS n_products,
           SUM(CAST(revenue AS DOUBLE PRECISION)) OVER (ORDER BY revenue DESC ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) AS cum_revenue,
           SUM(CAST(revenue AS DOUBLE PRECISION)) OVER () AS total_revenue
    FROM prod
)
SELECT MAX(n_products) AS products,
       SUM(CASE WHEN rn <= 0.2 * n_products THEN 1 ELSE 0 END) AS top_20_percent_products,
       ROUND(100.0 * SUM(CASE WHEN rn <= 0.2 * n_products THEN CAST(revenue AS DOUBLE PRECISION) ELSE 0 END) / MAX(total_revenue), 2) AS top_20_percent_revenue_share_pct,
       MIN(CASE WHEN cum_revenue >= 0.8 * total_revenue THEN rn END) AS products_for_80_percent_revenue
FROM ranked;

-- name: d1_monthly_kpis
SELECT d.year_month,
       SUM(f.revenue) AS revenue,
       SUM(f.profit) AS profit,
       COUNT(DISTINCT f.order_id) AS orders
FROM fact_sales f
JOIN dim_date d ON d.date_key = f.date_key
GROUP BY d.year_month
ORDER BY d.year_month;

-- Redshift only. Loads the curated Parquet from S3.
-- Parquet is mapped to the column list BY POSITION, so the generator/Glue output must keep this order.
-- Dimensions are small and fully refreshed; sales lands in staging and is merged by 03_transform.sql.

TRUNCATE dim_date;
COPY dim_date (date_key, full_date, cal_year, cal_quarter, cal_month, month_name, year_month, day_of_month, day_of_week, day_name, is_weekend)
FROM 's3://{{BUCKET}}/curated/dim_date/' IAM_ROLE '{{IAM_ROLE_ARN}}' FORMAT AS PARQUET;

TRUNCATE dim_product;
COPY dim_product (product_key, sku, product_name, category, subcategory, unit_cost, unit_price)
FROM 's3://{{BUCKET}}/curated/dim_product/' IAM_ROLE '{{IAM_ROLE_ARN}}' FORMAT AS PARQUET;

TRUNCATE dim_store;
COPY dim_store (store_key, store_name, city, state, region, store_type)
FROM 's3://{{BUCKET}}/curated/dim_store/' IAM_ROLE '{{IAM_ROLE_ARN}}' FORMAT AS PARQUET;

TRUNCATE dim_customer;
COPY dim_customer (customer_key, customer_id, segment, state, signup_date)
FROM 's3://{{BUCKET}}/curated/dim_customer/' IAM_ROLE '{{IAM_ROLE_ARN}}' FORMAT AS PARQUET;

TRUNCATE stg_sales;
COPY stg_sales (order_id, line_number, date_key, product_key, store_key, customer_key, quantity, unit_price, discount_pct)
FROM 's3://{{BUCKET}}/curated/sales/' IAM_ROLE '{{IAM_ROLE_ARN}}' FORMAT AS PARQUET;

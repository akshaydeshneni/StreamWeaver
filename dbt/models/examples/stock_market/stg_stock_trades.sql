-- This dbt model represents the "Silver" layer of our Medallion Architecture.
-- Its purpose is to take the raw data from the Bronze layer, clean it,
-- and prepare it for further analysis and aggregation in the Gold layer.

{{
  -- The config block tells dbt how to materialize this model.
  -- 'table': This model will be created as a new table in the data warehouse.
  -- 'schema': This model will be created in the 'silver' schema.
  config(
    materialized='table',
    schema='silver'
  )
}}

WITH source_data AS (
  -- This CTE (Common Table Expression) selects the raw data from our source.
  -- The `source()` function is a dbt macro that references the 'raw_stock_trades'
  -- table defined in `models/bronze/sources.yml`.
  SELECT
    symbol,
    price,
    volume,
    event_time
  FROM {{ source('raw_data', 'raw_stock_trades') }}
)

-- This is the final SELECT statement that defines the structure of the silver table.
SELECT
  -- We cast columns to their correct data types and give them clearer names.
  CAST(symbol AS VARCHAR) AS stock_symbol,
  CAST(price AS DOUBLE) AS trade_price,
  CAST(volume AS BIGINT) AS trade_volume,
  CAST(event_time AS TIMESTAMP) AS trade_timestamp
FROM source_data
WHERE
  -- This WHERE clause applies a basic data quality check to filter out
  -- any records that are clearly erroneous (e.g., trades with no price or volume).
  price > 0 AND volume > 0

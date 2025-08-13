-- This dbt model represents the "Gold" layer of our Medallion Architecture.
-- It builds on the cleaned data from the Silver layer (`stg_stock_trades`)
-- to create a business-ready, aggregated table. In this case, we are creating
-- a daily summary for each stock symbol.

{{
  -- This model is materialized as a table in the 'gold' schema.
  config(
    materialized='table',
    schema='gold'
  )
}}

WITH daily_trades AS (
  -- This CTE prepares the data for aggregation.
  -- The `ref()` function is a dbt macro that creates a dependency on the 'stg_stock_trades' model.
  SELECT
    stock_symbol,
    trade_price,
    trade_volume,
    CAST(trade_timestamp AS DATE) AS trade_date,

    -- We use window functions to find the first and last trade price for each stock on each day.
    -- This allows us to calculate the open and close prices.
    -- PARTITION BY defines the window (each stock on each day).
    -- ORDER BY trade_timestamp defines the order within the window.
    FIRST_VALUE(trade_price) OVER (PARTITION BY stock_symbol, CAST(trade_timestamp AS DATE) ORDER BY trade_timestamp) AS open_price,
    LAST_VALUE(trade_price) OVER (PARTITION BY stock_symbol, CAST(trade_timestamp AS DATE) ORDER BY trade_timestamp) AS close_price
  FROM {{ ref('stg_stock_trades') }}
)

-- This final SELECT statement performs the daily aggregation.
SELECT
  trade_date,
  stock_symbol,

  -- Since the window function propagates the same open/close price to every row
  -- within the partition, we can use MAX() to select that single value after grouping.
  -- MIN() or AVG() would also work.
  MAX(open_price) AS open_price,
  MAX(trade_price) AS high_price,
  MIN(trade_price) AS low_price,
  MAX(close_price) AS close_price,
  SUM(trade_volume) AS total_volume
FROM daily_trades
GROUP BY
  trade_date,
  stock_symbol

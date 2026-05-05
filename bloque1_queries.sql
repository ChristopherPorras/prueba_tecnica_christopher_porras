-- Bloque 1 - SQL avanzado
-- Dialecto: BigQuery Standard SQL.
-- Supuesto: los CSV fueron cargados como tablas transactions, transaction_items, stores, products, vendors y store_promotions.
-- GMV neto: COMPLETED suma positivo y RETURNED resta.

-- Query 1: Ventas comparables (Comp Sales)
DECLARE current_start DATE DEFAULT DATE '2025-01-01';
DECLARE current_end DATE DEFAULT DATE '2025-06-30';
DECLARE previous_start DATE DEFAULT DATE_SUB(current_start, INTERVAL 1 YEAR);
DECLARE previous_end DATE DEFAULT DATE_SUB(current_end, INTERVAL 1 YEAR);

WITH tx AS (
  SELECT
    t.transaction_id,
    DATE(t.transaction_date) AS transaction_date,
    t.store_id,
    CASE WHEN t.status = 'RETURNED' THEN -t.total_amount ELSE t.total_amount END AS net_gmv
  FROM transactions t
),
eligible_stores AS (
  SELECT store_id, store_name, country, format
  FROM stores
  WHERE DATE(opening_date) <= previous_start
),
sales AS (
  SELECT
    s.country,
    s.format,
    s.store_id,
    s.store_name,
    SUM(IF(tx.transaction_date BETWEEN current_start AND current_end, tx.net_gmv, 0)) AS gmv_current,
    SUM(IF(tx.transaction_date BETWEEN previous_start AND previous_end, tx.net_gmv, 0)) AS gmv_previous
  FROM tx
  JOIN eligible_stores s USING (store_id)
  WHERE tx.transaction_date BETWEEN previous_start AND current_end
  GROUP BY 1, 2, 3, 4
)
SELECT
  country,
  format,
  store_id,
  store_name,
  gmv_current,
  gmv_previous,
  SAFE_DIVIDE(gmv_current, gmv_previous) - 1 AS comp_sales_growth_pct,
  DENSE_RANK() OVER (PARTITION BY format ORDER BY SAFE_DIVIDE(gmv_current, gmv_previous) - 1 DESC) AS rank_store_growth_in_format
FROM sales
WHERE gmv_current <> 0 AND gmv_previous <> 0
ORDER BY format, rank_store_growth_in_format;

-- Query 2: Productividad por metro cuadrado
WITH params AS (
  SELECT DATE '2025-04-01' AS quarter_start, DATE '2025-06-30' AS quarter_end
),
store_sales AS (
  SELECT
    s.store_id,
    s.store_name,
    s.country,
    s.format,
    s.region,
    s.size_sqm,
    SUM(CASE WHEN t.status = 'RETURNED' THEN -t.total_amount ELSE t.total_amount END) AS gmv,
    COUNT(DISTINCT t.transaction_id) AS transactions
  FROM transactions t
  JOIN stores s USING (store_id)
  CROSS JOIN params p
  WHERE DATE(t.transaction_date) BETWEEN p.quarter_start AND p.quarter_end
  GROUP BY 1, 2, 3, 4, 5, 6
),
scored AS (
  SELECT
    *,
    SAFE_DIVIDE(gmv, size_sqm) AS gmv_per_sqm,
    SAFE_DIVIDE(transactions, size_sqm) AS transactions_per_sqm,
    SAFE_DIVIDE(gmv, transactions) AS avg_ticket,
    PERCENTILE_CONT(SAFE_DIVIDE(gmv, size_sqm), 0.25) OVER (PARTITION BY format) AS p25_gmv_per_sqm
  FROM store_sales
)
SELECT
  *,
  DENSE_RANK() OVER (PARTITION BY format ORDER BY gmv_per_sqm DESC) AS rank_in_format,
  IF(gmv_per_sqm < p25_gmv_per_sqm, 'BAJO_RENDIMIENTO', 'OK') AS performance_flag
FROM scored
ORDER BY format, rank_in_format;

-- Query 3: Cohortes de clientes con tarjeta de lealtad
WITH loyalty_tx AS (
  SELECT
    customer_id,
    transaction_id,
    DATE_TRUNC(DATE(transaction_date), MONTH) AS tx_month,
    total_amount
  FROM transactions
  WHERE loyalty_card = TRUE
    AND customer_id IS NOT NULL
    AND status = 'COMPLETED'
),
first_purchase AS (
  SELECT customer_id, MIN(tx_month) AS cohort_month
  FROM loyalty_tx
  GROUP BY 1
),
activity AS (
  SELECT
    f.cohort_month,
    DATE_DIFF(l.tx_month, f.cohort_month, MONTH) AS month_n,
    l.customer_id,
    l.total_amount
  FROM loyalty_tx l
  JOIN first_purchase f USING (customer_id)
),
cohort_size AS (
  SELECT cohort_month, COUNT(DISTINCT customer_id) AS cohort_customers
  FROM first_purchase
  GROUP BY 1
),
metrics AS (
  SELECT
    a.cohort_month,
    a.month_n,
    COUNT(DISTINCT a.customer_id) AS active_customers,
    AVG(a.total_amount) AS avg_ticket,
    ANY_VALUE(cs.cohort_customers) AS cohort_customers,
    SAFE_DIVIDE(COUNT(DISTINCT a.customer_id), ANY_VALUE(cs.cohort_customers)) AS retention_rate
  FROM activity a
  JOIN cohort_size cs USING (cohort_month)
  WHERE month_n IN (0, 1, 2, 3, 6)
  GROUP BY 1, 2
)
SELECT
  cohort_month,
  MAX(cohort_customers) AS cohort_customers,
  MAX(IF(month_n = 0, retention_rate, NULL)) AS retention_m0,
  MAX(IF(month_n = 1, retention_rate, NULL)) AS retention_m1,
  MAX(IF(month_n = 2, retention_rate, NULL)) AS retention_m2,
  MAX(IF(month_n = 3, retention_rate, NULL)) AS retention_m3,
  MAX(IF(month_n = 6, retention_rate, NULL)) AS retention_m6,
  MAX(IF(month_n = 0, avg_ticket, NULL)) AS avg_ticket_m0,
  MAX(IF(month_n = 1, avg_ticket, NULL)) AS avg_ticket_m1,
  MAX(IF(month_n = 2, avg_ticket, NULL)) AS avg_ticket_m2,
  MAX(IF(month_n = 3, avg_ticket, NULL)) AS avg_ticket_m3,
  MAX(IF(month_n = 6, avg_ticket, NULL)) AS avg_ticket_m6,
  CASE
    WHEN MAX(IF(month_n = 6, avg_ticket, NULL)) > MAX(IF(month_n = 0, avg_ticket, NULL)) THEN 'CRECE'
    WHEN MAX(IF(month_n = 6, avg_ticket, NULL)) < MAX(IF(month_n = 0, avg_ticket, NULL)) THEN 'DECRECE'
    ELSE 'SIN_DATOS'
  END AS ticket_trend_m0_to_m6
FROM metrics
GROUP BY cohort_month
ORDER BY cohort_month;

-- Query 4: GMROI por proveedor y categoria
WITH item_sales AS (
  SELECT
    p.vendor_id,
    COALESCE(v.vendor_name, 'SIN_VENDOR') AS vendor_name,
    p.category,
    ti.item_id,
    DATE(t.transaction_date) AS sale_date,
    ti.quantity,
    ti.quantity * ti.unit_price AS gmv,
    ti.quantity * p.cost AS cost_total
  FROM transaction_items ti
  JOIN transactions t USING (transaction_id)
  JOIN products p USING (item_id)
  LEFT JOIN vendors v USING (vendor_id)
  WHERE t.status = 'COMPLETED'
)
SELECT
  vendor_id,
  vendor_name,
  category,
  SUM(gmv) AS gmv,
  SUM(cost_total) AS cost_total,
  SUM(gmv) - SUM(cost_total) AS gross_margin,
  SAFE_DIVIDE(SUM(gmv) - SUM(cost_total), SUM(cost_total)) AS gmroi,
  COUNT(DISTINCT item_id) AS active_skus,
  SAFE_DIVIDE(SUM(quantity), DATE_DIFF(MAX(sale_date), MIN(sale_date), DAY) + 1) AS sales_velocity_units_day,
  IF(SAFE_DIVIDE(SUM(gmv) - SUM(cost_total), SUM(cost_total)) < 1, 'GMROI_BAJO_1', 'OK') AS gmroi_flag
FROM item_sales
GROUP BY 1, 2, 3
ORDER BY gmroi ASC;

-- Query 5: Deteccion de posibles quiebres de stock
WITH params AS (SELECT DATE '2025-06-30' AS max_date),
daily_sales AS (
  SELECT
    t.store_id,
    ti.item_id,
    DATE(t.transaction_date) AS sale_date,
    SUM(ti.quantity) AS units,
    SUM(ti.quantity * ti.unit_price) AS gmv
  FROM transaction_items ti
  JOIN transactions t USING (transaction_id)
  WHERE t.status = 'COMPLETED'
  GROUP BY 1, 2, 3
),
store_item_bounds AS (
  SELECT store_id, item_id, MIN(sale_date) AS first_sale_date, (SELECT max_date FROM params) AS max_date
  FROM daily_sales
  GROUP BY 1, 2
),
spine AS (
  SELECT b.store_id, b.item_id, day AS calendar_date
  FROM store_item_bounds b, UNNEST(GENERATE_DATE_ARRAY(b.first_sale_date, b.max_date)) AS day
),
missing_days AS (
  SELECT
    s.store_id,
    s.item_id,
    s.calendar_date,
    DATE_SUB(s.calendar_date, INTERVAL ROW_NUMBER() OVER (PARTITION BY s.store_id, s.item_id ORDER BY s.calendar_date) DAY) AS island_key
  FROM spine s
  LEFT JOIN daily_sales d
    ON d.store_id = s.store_id
   AND d.item_id = s.item_id
   AND d.sale_date = s.calendar_date
  WHERE d.sale_date IS NULL
),
gaps AS (
  SELECT
    store_id,
    item_id,
    MIN(calendar_date) AS gap_start,
    MAX(calendar_date) AS gap_end,
    COUNT(*) AS gap_days
  FROM missing_days
  GROUP BY 1, 2, island_key
  HAVING COUNT(*) >= 3
),
scored AS (
  SELECT
    g.*,
    SAFE_DIVIDE((
      SELECT SUM(d.gmv)
      FROM daily_sales d
      WHERE d.store_id = g.store_id
        AND d.item_id = g.item_id
        AND d.sale_date BETWEEN DATE_SUB(g.gap_start, INTERVAL 14 DAY) AND DATE_SUB(g.gap_start, INTERVAL 1 DAY)
    ), 14) AS avg_daily_gmv_before_gap
  FROM gaps g
)
SELECT
  s.store_id,
  st.store_name,
  s.item_id,
  p.item_name,
  p.category,
  COALESCE(v.vendor_name, 'SIN_VENDOR') AS vendor_name,
  s.gap_start,
  s.gap_end,
  s.gap_days,
  s.avg_daily_gmv_before_gap,
  s.avg_daily_gmv_before_gap * s.gap_days AS estimated_lost_gmv
FROM scored s
JOIN stores st USING (store_id)
JOIN products p USING (item_id)
LEFT JOIN vendors v USING (vendor_id)
ORDER BY estimated_lost_gmv DESC;

-- Query 6: Impacto de promociones en ticket y volumen
WITH tx_category AS (
  SELECT
    t.transaction_id,
    p.category,
    LOGICAL_OR(ti.was_on_promo) AS has_promo_item,
    SUM(ti.quantity) AS category_units,
    SUM(ti.quantity * ti.unit_price) AS category_gmv,
    ANY_VALUE(t.total_amount) AS transaction_ticket
  FROM transactions t
  JOIN transaction_items ti USING (transaction_id)
  JOIN products p USING (item_id)
  WHERE t.status = 'COMPLETED'
  GROUP BY 1, 2
)
SELECT
  category,
  has_promo_item,
  COUNT(DISTINCT transaction_id) AS transactions,
  AVG(transaction_ticket) AS avg_ticket,
  AVG(category_units) AS avg_units,
  AVG(category_gmv) AS avg_category_gmv
FROM tx_category
GROUP BY 1, 2
ORDER BY category, has_promo_item;

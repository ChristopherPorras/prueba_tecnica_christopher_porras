-- Bloque 1 - SQL avanzado adaptado a SQLite.
-- Este archivo crea tablas de resultado para revisarlas en SQLite Viewer.

DROP TABLE IF EXISTS bloque1_q1_ventas_comparables;
CREATE TABLE bloque1_q1_ventas_comparables AS
WITH params AS (
  SELECT
    DATE('2025-01-01') AS current_start,
    DATE('2025-06-30') AS current_end,
    DATE('2024-01-01') AS previous_start,
    DATE('2024-06-30') AS previous_end
),
tx AS (
  SELECT
    transaction_id,
    DATE(transaction_date) AS transaction_date,
    store_id,
    CASE WHEN status = 'RETURNED' THEN -total_amount ELSE total_amount END AS ventas_netas
  FROM transactions
),
eligible_stores AS (
  SELECT store_id, store_name, country, format
  FROM stores
  WHERE DATE(opening_date) <= (SELECT previous_start FROM params)
),
sales AS (
  SELECT
    s.country,
    s.format,
    s.store_id,
    s.store_name,
    SUM(CASE
      WHEN tx.transaction_date BETWEEN (SELECT current_start FROM params) AND (SELECT current_end FROM params)
      THEN tx.ventas_netas ELSE 0
    END) AS ventas_netas_periodo_actual,
    SUM(CASE
      WHEN tx.transaction_date BETWEEN (SELECT previous_start FROM params) AND (SELECT previous_end FROM params)
      THEN tx.ventas_netas ELSE 0
    END) AS ventas_netas_periodo_anterior
  FROM tx
  JOIN eligible_stores s ON s.store_id = tx.store_id
  WHERE tx.transaction_date BETWEEN (SELECT previous_start FROM params) AND (SELECT current_end FROM params)
  GROUP BY s.country, s.format, s.store_id, s.store_name
)
SELECT
  country,
  format,
  store_id,
  store_name,
  ROUND(ventas_netas_periodo_actual, 2) AS ventas_netas_periodo_actual,
  ROUND(ventas_netas_periodo_anterior, 2) AS ventas_netas_periodo_anterior,
  ROUND(ventas_netas_periodo_actual / NULLIF(ventas_netas_periodo_anterior, 0) - 1, 4) AS crecimiento_ventas_comparables_pct,
  DENSE_RANK() OVER (
    PARTITION BY format
    ORDER BY ventas_netas_periodo_actual / NULLIF(ventas_netas_periodo_anterior, 0) - 1 DESC
  ) AS ranking_crecimiento_tienda_formato
FROM sales
WHERE ventas_netas_periodo_actual <> 0
  AND ventas_netas_periodo_anterior <> 0
ORDER BY format, ranking_crecimiento_tienda_formato;

DROP TABLE IF EXISTS bloque1_q2_productividad_tienda;
CREATE TABLE bloque1_q2_productividad_tienda AS
WITH store_sales AS (
  SELECT
    s.store_id,
    s.store_name,
    s.country,
    s.format,
    s.region,
    s.size_sqm,
    SUM(CASE WHEN t.status = 'RETURNED' THEN -t.total_amount ELSE t.total_amount END) AS ventas_netas,
    COUNT(DISTINCT t.transaction_id) AS transacciones
  FROM transactions t
  JOIN stores s ON s.store_id = t.store_id
  WHERE DATE(t.transaction_date) BETWEEN DATE('2025-04-01') AND DATE('2025-06-30')
  GROUP BY s.store_id, s.store_name, s.country, s.format, s.region, s.size_sqm
),
scored AS (
  SELECT
    *,
    ventas_netas / NULLIF(size_sqm, 0) AS ventas_netas_por_metro_cuadrado,
    transacciones * 1.0 / NULLIF(size_sqm, 0) AS transacciones_por_metro_cuadrado,
    ventas_netas / NULLIF(transacciones, 0) AS ticket_promedio
  FROM store_sales
),
ordenado AS (
  SELECT
    *,
    ROW_NUMBER() OVER (PARTITION BY format ORDER BY ventas_netas_por_metro_cuadrado) AS posicion_formato,
    COUNT(*) OVER (PARTITION BY format) AS tiendas_formato
  FROM scored
),
percentil AS (
  SELECT
    format,
    MAX(CASE
      WHEN posicion_formato = CAST((tiendas_formato - 1) * 0.25 AS INTEGER) + 1
      THEN ventas_netas_por_metro_cuadrado
    END) AS percentil_25_ventas_por_metro_cuadrado
  FROM ordenado
  GROUP BY format
)
SELECT
  o.store_id,
  o.store_name,
  o.country,
  o.format,
  o.region,
  o.size_sqm,
  ROUND(o.ventas_netas, 2) AS ventas_netas,
  o.transacciones,
  ROUND(o.ventas_netas_por_metro_cuadrado, 2) AS ventas_netas_por_metro_cuadrado,
  ROUND(o.transacciones_por_metro_cuadrado, 4) AS transacciones_por_metro_cuadrado,
  ROUND(o.ticket_promedio, 2) AS ticket_promedio,
  ROUND(p.percentil_25_ventas_por_metro_cuadrado, 2) AS percentil_25_ventas_por_metro_cuadrado,
  DENSE_RANK() OVER (PARTITION BY o.format ORDER BY o.ventas_netas_por_metro_cuadrado DESC) AS ranking_en_formato,
  CASE
    WHEN o.ventas_netas_por_metro_cuadrado < p.percentil_25_ventas_por_metro_cuadrado THEN 'BAJO_RENDIMIENTO'
    ELSE 'OK'
  END AS alerta_rendimiento
FROM ordenado o
JOIN percentil p ON p.format = o.format
ORDER BY o.format, ranking_en_formato;

DROP TABLE IF EXISTS bloque1_q3_cohortes_lealtad;
CREATE TABLE bloque1_q3_cohortes_lealtad AS
WITH loyalty_tx AS (
  SELECT
    customer_id,
    transaction_id,
    DATE(transaction_date, 'start of month') AS tx_month,
    total_amount
  FROM transactions
  WHERE loyalty_card = 1
    AND customer_id IS NOT NULL
    AND status = 'COMPLETED'
),
first_purchase AS (
  SELECT
    customer_id,
    MIN(tx_month) AS cohort_month
  FROM loyalty_tx
  GROUP BY customer_id
),
activity AS (
  SELECT
    f.cohort_month,
    (
      (CAST(strftime('%Y', l.tx_month) AS INTEGER) - CAST(strftime('%Y', f.cohort_month) AS INTEGER)) * 12
      + (CAST(strftime('%m', l.tx_month) AS INTEGER) - CAST(strftime('%m', f.cohort_month) AS INTEGER))
    ) AS month_n,
    l.customer_id,
    l.total_amount
  FROM loyalty_tx l
  JOIN first_purchase f ON f.customer_id = l.customer_id
),
cohort_size AS (
  SELECT
    cohort_month,
    COUNT(DISTINCT customer_id) AS cohort_customers
  FROM first_purchase
  GROUP BY cohort_month
),
metrics AS (
  SELECT
    a.cohort_month,
    a.month_n,
    COUNT(DISTINCT a.customer_id) AS active_customers,
    AVG(a.total_amount) AS avg_ticket,
    MAX(cs.cohort_customers) AS cohort_customers,
    COUNT(DISTINCT a.customer_id) * 1.0 / NULLIF(MAX(cs.cohort_customers), 0) AS retention_rate
  FROM activity a
  JOIN cohort_size cs ON cs.cohort_month = a.cohort_month
  WHERE a.month_n IN (0, 1, 2, 3, 6)
  GROUP BY a.cohort_month, a.month_n
)
SELECT
  cohort_month,
  MAX(cohort_customers) AS cohort_customers,
  ROUND(MAX(CASE WHEN month_n = 0 THEN retention_rate END), 4) AS retencion_mes_0,
  ROUND(MAX(CASE WHEN month_n = 1 THEN retention_rate END), 4) AS retencion_mes_1,
  ROUND(MAX(CASE WHEN month_n = 2 THEN retention_rate END), 4) AS retencion_mes_2,
  ROUND(MAX(CASE WHEN month_n = 3 THEN retention_rate END), 4) AS retencion_mes_3,
  ROUND(MAX(CASE WHEN month_n = 6 THEN retention_rate END), 4) AS retencion_mes_6,
  ROUND(MAX(CASE WHEN month_n = 0 THEN avg_ticket END), 2) AS ticket_promedio_mes_0,
  ROUND(MAX(CASE WHEN month_n = 1 THEN avg_ticket END), 2) AS ticket_promedio_mes_1,
  ROUND(MAX(CASE WHEN month_n = 2 THEN avg_ticket END), 2) AS ticket_promedio_mes_2,
  ROUND(MAX(CASE WHEN month_n = 3 THEN avg_ticket END), 2) AS ticket_promedio_mes_3,
  ROUND(MAX(CASE WHEN month_n = 6 THEN avg_ticket END), 2) AS ticket_promedio_mes_6,
  CASE
    WHEN MAX(CASE WHEN month_n = 6 THEN avg_ticket END) > MAX(CASE WHEN month_n = 0 THEN avg_ticket END) THEN 'CRECE'
    WHEN MAX(CASE WHEN month_n = 6 THEN avg_ticket END) < MAX(CASE WHEN month_n = 0 THEN avg_ticket END) THEN 'DECRECE'
    ELSE 'SIN_DATOS'
  END AS tendencia_ticket_mes_0_a_mes_6
FROM metrics
GROUP BY cohort_month
ORDER BY cohort_month;

DROP TABLE IF EXISTS bloque1_q4_retorno_margen_proveedor_categoria;
CREATE TABLE bloque1_q4_retorno_margen_proveedor_categoria AS
WITH item_sales AS (
  SELECT
    p.vendor_id,
    COALESCE(v.vendor_name, 'SIN_VENDOR') AS vendor_name,
    p.category,
    ti.item_id,
    DATE(t.transaction_date) AS sale_date,
    ti.quantity,
    ti.quantity * ti.unit_price AS ventas_brutas_item,
    ti.quantity * p.cost AS costo_total
  FROM transaction_items ti
  JOIN transactions t ON t.transaction_id = ti.transaction_id
  JOIN products p ON p.item_id = ti.item_id
  LEFT JOIN vendors v ON v.vendor_id = p.vendor_id
  WHERE t.status = 'COMPLETED'
)
SELECT
  vendor_id,
  vendor_name,
  category,
  ROUND(SUM(ventas_brutas_item), 2) AS ventas_brutas_items,
  ROUND(SUM(costo_total), 2) AS costo_total,
  ROUND(SUM(ventas_brutas_item) - SUM(costo_total), 2) AS margen_bruto,
  ROUND((SUM(ventas_brutas_item) - SUM(costo_total)) / NULLIF(SUM(costo_total), 0), 4) AS retorno_margen_bruto_sobre_costo,
  COUNT(DISTINCT item_id) AS items_activos,
  ROUND(SUM(quantity) * 1.0 / NULLIF(JULIANDAY(MAX(sale_date)) - JULIANDAY(MIN(sale_date)) + 1, 0), 4) AS velocidad_unidades_por_dia,
  CASE
    WHEN (SUM(ventas_brutas_item) - SUM(costo_total)) / NULLIF(SUM(costo_total), 0) < 1 THEN 'RETORNO_MARGEN_BAJO_1'
    ELSE 'OK'
  END AS alerta_retorno_margen
FROM item_sales
GROUP BY vendor_id, vendor_name, category
ORDER BY retorno_margen_bruto_sobre_costo ASC;

DROP TABLE IF EXISTS bloque1_q5_posibles_quiebres_stock;
CREATE TABLE bloque1_q5_posibles_quiebres_stock AS
WITH RECURSIVE
daily_sales AS (
  SELECT
    t.store_id,
    ti.item_id,
    DATE(t.transaction_date) AS sale_date,
    SUM(ti.quantity) AS unidades,
    SUM(ti.quantity * ti.unit_price) AS ventas_brutas
  FROM transaction_items ti
  JOIN transactions t ON t.transaction_id = ti.transaction_id
  WHERE t.status = 'COMPLETED'
  GROUP BY t.store_id, ti.item_id, DATE(t.transaction_date)
),
store_item_bounds AS (
  SELECT
    store_id,
    item_id,
    MIN(sale_date) AS first_sale_date,
    DATE('2025-06-30') AS max_date
  FROM daily_sales
  GROUP BY store_id, item_id
),
spine(store_id, item_id, calendar_date, max_date) AS (
  SELECT store_id, item_id, first_sale_date, max_date
  FROM store_item_bounds
  UNION ALL
  SELECT store_id, item_id, DATE(calendar_date, '+1 day'), max_date
  FROM spine
  WHERE calendar_date < max_date
),
missing_days AS (
  SELECT
    s.store_id,
    s.item_id,
    s.calendar_date,
    DATE(
      s.calendar_date,
      '-' || ROW_NUMBER() OVER (PARTITION BY s.store_id, s.item_id ORDER BY s.calendar_date) || ' day'
    ) AS island_key
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
  GROUP BY store_id, item_id, island_key
  HAVING COUNT(*) >= 3
),
scored AS (
  SELECT
    g.*,
    (
      SELECT SUM(d.ventas_brutas) / 14.0
      FROM daily_sales d
      WHERE d.store_id = g.store_id
        AND d.item_id = g.item_id
        AND d.sale_date BETWEEN DATE(g.gap_start, '-14 day') AND DATE(g.gap_start, '-1 day')
    ) AS venta_diaria_promedio_previa
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
  ROUND(COALESCE(s.venta_diaria_promedio_previa, 0), 2) AS venta_diaria_promedio_previa,
  ROUND(COALESCE(s.venta_diaria_promedio_previa, 0) * s.gap_days, 2) AS venta_estimada_perdida
FROM scored s
JOIN stores st ON st.store_id = s.store_id
JOIN products p ON p.item_id = s.item_id
LEFT JOIN vendors v ON v.vendor_id = p.vendor_id
ORDER BY venta_estimada_perdida DESC;

DROP TABLE IF EXISTS bloque1_q6_promociones_ticket_volumen;
CREATE TABLE bloque1_q6_promociones_ticket_volumen AS
WITH tx_category AS (
  SELECT
    t.transaction_id,
    p.category,
    MAX(CASE WHEN ti.was_on_promo = 1 THEN 1 ELSE 0 END) AS tiene_item_en_promocion,
    SUM(ti.quantity) AS unidades_categoria,
    SUM(ti.quantity * ti.unit_price) AS ventas_categoria,
    MAX(t.total_amount) AS ticket_transaccion
  FROM transactions t
  JOIN transaction_items ti ON ti.transaction_id = t.transaction_id
  JOIN products p ON p.item_id = ti.item_id
  WHERE t.status = 'COMPLETED'
  GROUP BY t.transaction_id, p.category
)
SELECT
  category,
  tiene_item_en_promocion,
  COUNT(DISTINCT transaction_id) AS transacciones,
  ROUND(AVG(ticket_transaccion), 2) AS ticket_promedio,
  ROUND(AVG(unidades_categoria), 4) AS unidades_promedio,
  ROUND(AVG(ventas_categoria), 2) AS ventas_promedio_categoria
FROM tx_category
GROUP BY category, tiene_item_en_promocion
ORDER BY category, tiene_item_en_promocion;

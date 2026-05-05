/*
  Bloque 1 - Queries avanzadas en SQL Server T-SQL.
  Ejecutable desde VS Code con la extension MSSQL despues de cargar los CSV.

  Definicion usada:
  ventas_netas = ventas completadas positivas y devoluciones negativas.
*/

USE RetailPruebaTecnica;
GO

/* Query 1: Ventas comparables
   Compara enero-junio 2025 contra enero-junio 2024 solo en tiendas que ya
   estaban abiertas al inicio del periodo anterior.
*/
DECLARE @current_start DATE = '2025-01-01';
DECLARE @current_end DATE = '2025-06-30';
DECLARE @previous_start DATE = DATEADD(YEAR, -1, @current_start);
DECLARE @previous_end DATE = DATEADD(YEAR, -1, @current_end);

WITH tx AS (
  SELECT
    transaction_id,
    transaction_date,
    store_id,
    CASE WHEN status = 'RETURNED' THEN -total_amount ELSE total_amount END AS ventas_netas
  FROM dbo.transactions
),
eligible_stores AS (
  SELECT store_id, store_name, country, format
  FROM dbo.stores
  WHERE opening_date <= @previous_start
),
sales AS (
  SELECT
    s.country,
    s.format,
    s.store_id,
    s.store_name,
    SUM(CASE WHEN tx.transaction_date BETWEEN @current_start AND @current_end THEN tx.ventas_netas ELSE 0 END) AS ventas_actuales,
    SUM(CASE WHEN tx.transaction_date BETWEEN @previous_start AND @previous_end THEN tx.ventas_netas ELSE 0 END) AS ventas_anteriores
  FROM tx
  JOIN eligible_stores s ON s.store_id = tx.store_id
  WHERE tx.transaction_date BETWEEN @previous_start AND @current_end
  GROUP BY s.country, s.format, s.store_id, s.store_name
)
SELECT
  country,
  format,
  store_id,
  store_name,
  ventas_actuales,
  ventas_anteriores,
  ventas_actuales / NULLIF(ventas_anteriores, 0) - 1 AS crecimiento_ventas_comparables,
  DENSE_RANK() OVER (
    PARTITION BY format
    ORDER BY ventas_actuales / NULLIF(ventas_anteriores, 0) - 1 DESC
  ) AS ranking_tienda_dentro_formato
FROM sales
WHERE ventas_actuales <> 0 AND ventas_anteriores <> 0
ORDER BY format, ranking_tienda_dentro_formato;
GO

/* Query 2: Productividad por metro cuadrado
   Calcula ventas netas, transacciones, ticket promedio y alerta de bajo rendimiento
   para el ultimo trimestre del dataset: abril-junio 2025.
*/
DECLARE @quarter_start DATE = '2025-04-01';
DECLARE @quarter_end DATE = '2025-06-30';

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
  FROM dbo.transactions t
  JOIN dbo.stores s ON s.store_id = t.store_id
  WHERE t.transaction_date BETWEEN @quarter_start AND @quarter_end
  GROUP BY s.store_id, s.store_name, s.country, s.format, s.region, s.size_sqm
),
scored AS (
  SELECT
    *,
    ventas_netas / NULLIF(size_sqm, 0) AS ventas_netas_por_metro_cuadrado,
    transacciones * 1.0 / NULLIF(size_sqm, 0) AS transacciones_por_metro_cuadrado,
    ventas_netas / NULLIF(transacciones, 0) AS ticket_promedio,
    PERCENTILE_CONT(0.25) WITHIN GROUP (ORDER BY ventas_netas / NULLIF(size_sqm, 0))
      OVER (PARTITION BY format) AS percentil_25_formato
  FROM store_sales
)
SELECT
  *,
  DENSE_RANK() OVER (PARTITION BY format ORDER BY ventas_netas_por_metro_cuadrado DESC) AS ranking_dentro_formato,
  CASE
    WHEN ventas_netas_por_metro_cuadrado < percentil_25_formato THEN 'BAJO_RENDIMIENTO'
    ELSE 'OK'
  END AS alerta_rendimiento
FROM scored
ORDER BY format, ranking_dentro_formato;
GO

/* Query 3: Cohortes de clientes con tarjeta de lealtad
   Cohorte = mes de primera compra. Retencion = clientes que regresaron en el mes relativo.
*/
WITH loyalty_tx AS (
  SELECT
    customer_id,
    transaction_id,
    DATEFROMPARTS(YEAR(transaction_date), MONTH(transaction_date), 1) AS mes_compra,
    total_amount
  FROM dbo.transactions
  WHERE loyalty_card = 1
    AND customer_id IS NOT NULL
    AND status = 'COMPLETED'
),
first_purchase AS (
  SELECT customer_id, MIN(mes_compra) AS mes_cohorte
  FROM loyalty_tx
  GROUP BY customer_id
),
activity AS (
  SELECT
    f.mes_cohorte,
    DATEDIFF(MONTH, f.mes_cohorte, l.mes_compra) AS mes_relativo,
    l.customer_id,
    l.total_amount
  FROM loyalty_tx l
  JOIN first_purchase f ON f.customer_id = l.customer_id
),
cohort_size AS (
  SELECT mes_cohorte, COUNT(DISTINCT customer_id) AS clientes_cohorte
  FROM first_purchase
  GROUP BY mes_cohorte
),
metrics AS (
  SELECT
    a.mes_cohorte,
    a.mes_relativo,
    COUNT(DISTINCT a.customer_id) AS clientes_activos,
    AVG(a.total_amount) AS ticket_promedio,
    MAX(cs.clientes_cohorte) AS clientes_cohorte,
    COUNT(DISTINCT a.customer_id) * 1.0 / NULLIF(MAX(cs.clientes_cohorte), 0) AS tasa_retencion
  FROM activity a
  JOIN cohort_size cs ON cs.mes_cohorte = a.mes_cohorte
  WHERE a.mes_relativo IN (0, 1, 2, 3, 6)
  GROUP BY a.mes_cohorte, a.mes_relativo
)
SELECT
  mes_cohorte,
  MAX(clientes_cohorte) AS clientes_cohorte,
  MAX(CASE WHEN mes_relativo = 0 THEN tasa_retencion END) AS retencion_mes_0,
  MAX(CASE WHEN mes_relativo = 1 THEN tasa_retencion END) AS retencion_mes_1,
  MAX(CASE WHEN mes_relativo = 2 THEN tasa_retencion END) AS retencion_mes_2,
  MAX(CASE WHEN mes_relativo = 3 THEN tasa_retencion END) AS retencion_mes_3,
  MAX(CASE WHEN mes_relativo = 6 THEN tasa_retencion END) AS retencion_mes_6,
  MAX(CASE WHEN mes_relativo = 0 THEN ticket_promedio END) AS ticket_promedio_mes_0,
  MAX(CASE WHEN mes_relativo = 1 THEN ticket_promedio END) AS ticket_promedio_mes_1,
  MAX(CASE WHEN mes_relativo = 2 THEN ticket_promedio END) AS ticket_promedio_mes_2,
  MAX(CASE WHEN mes_relativo = 3 THEN ticket_promedio END) AS ticket_promedio_mes_3,
  MAX(CASE WHEN mes_relativo = 6 THEN ticket_promedio END) AS ticket_promedio_mes_6,
  CASE
    WHEN MAX(CASE WHEN mes_relativo = 6 THEN ticket_promedio END) > MAX(CASE WHEN mes_relativo = 0 THEN ticket_promedio END) THEN 'CRECE'
    WHEN MAX(CASE WHEN mes_relativo = 6 THEN ticket_promedio END) < MAX(CASE WHEN mes_relativo = 0 THEN ticket_promedio END) THEN 'DECRECE'
    ELSE 'SIN_DATOS'
  END AS tendencia_ticket_mes_0_a_mes_6
FROM metrics
GROUP BY mes_cohorte
ORDER BY mes_cohorte;
GO

/* Query 4: Retorno de margen bruto sobre inversion por proveedor y categoria */
WITH item_sales AS (
  SELECT
    p.vendor_id,
    COALESCE(v.vendor_name, 'SIN_VENDOR') AS vendor_name,
    p.category,
    ti.item_id,
    t.transaction_date AS fecha_venta,
    ti.quantity,
    ti.quantity * ti.unit_price AS ventas,
    ti.quantity * p.cost AS costo_total
  FROM dbo.transaction_items ti
  JOIN dbo.transactions t ON t.transaction_id = ti.transaction_id
  JOIN dbo.products p ON p.item_id = ti.item_id
  LEFT JOIN dbo.vendors v ON v.vendor_id = p.vendor_id
  WHERE t.status = 'COMPLETED'
)
SELECT
  vendor_id,
  vendor_name,
  category,
  SUM(ventas) AS ventas,
  SUM(costo_total) AS costo_total,
  SUM(ventas) - SUM(costo_total) AS margen_bruto,
  (SUM(ventas) - SUM(costo_total)) / NULLIF(SUM(costo_total), 0) AS retorno_margen_sobre_costo,
  COUNT(DISTINCT item_id) AS productos_activos,
  SUM(quantity) * 1.0 / NULLIF(DATEDIFF(DAY, MIN(fecha_venta), MAX(fecha_venta)) + 1, 0) AS velocidad_unidades_por_dia,
  CASE
    WHEN (SUM(ventas) - SUM(costo_total)) / NULLIF(SUM(costo_total), 0) < 1 THEN 'RETORNO_BAJO_1'
    ELSE 'OK'
  END AS alerta_retorno
FROM item_sales
GROUP BY vendor_id, vendor_name, category
ORDER BY retorno_margen_sobre_costo ASC;
GO

/* Query 5: Deteccion de posibles quiebres de stock
   Genera una columna diaria por tienda-producto y busca rachas de 3+ dias sin venta.
*/
DECLARE @max_date DATE = '2025-06-30';

WITH daily_sales AS (
  SELECT
    t.store_id,
    ti.item_id,
    CAST(t.transaction_date AS DATE) AS sale_date,
    SUM(ti.quantity) AS unidades,
    SUM(ti.quantity * ti.unit_price) AS ventas
  FROM dbo.transaction_items ti
  JOIN dbo.transactions t ON t.transaction_id = ti.transaction_id
  WHERE t.status = 'COMPLETED'
  GROUP BY t.store_id, ti.item_id, CAST(t.transaction_date AS DATE)
),
store_item_bounds AS (
  SELECT store_id, item_id, MIN(sale_date) AS first_sale_date, @max_date AS max_date
  FROM daily_sales
  GROUP BY store_id, item_id
),
numbers AS (
  SELECT TOP (700) ROW_NUMBER() OVER (ORDER BY (SELECT NULL)) - 1 AS n
  FROM sys.all_objects a
  CROSS JOIN sys.all_objects b
),
spine AS (
  SELECT
    b.store_id,
    b.item_id,
    DATEADD(DAY, n.n, b.first_sale_date) AS calendar_date
  FROM store_item_bounds b
  JOIN numbers n ON n.n <= DATEDIFF(DAY, b.first_sale_date, b.max_date)
),
missing_days AS (
  SELECT
    s.store_id,
    s.item_id,
    s.calendar_date,
    DATEADD(DAY, -ROW_NUMBER() OVER (PARTITION BY s.store_id, s.item_id ORDER BY s.calendar_date), s.calendar_date) AS island_key
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
      SELECT SUM(d.ventas) / 14.0
      FROM daily_sales d
      WHERE d.store_id = g.store_id
        AND d.item_id = g.item_id
        AND d.sale_date BETWEEN DATEADD(DAY, -14, g.gap_start) AND DATEADD(DAY, -1, g.gap_start)
    ) AS ventas_promedio_diarias_previas
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
  s.ventas_promedio_diarias_previas,
  s.ventas_promedio_diarias_previas * s.gap_days AS ventas_estimadas_perdidas
FROM scored s
JOIN dbo.stores st ON st.store_id = s.store_id
JOIN dbo.products p ON p.item_id = s.item_id
LEFT JOIN dbo.vendors v ON v.vendor_id = p.vendor_id
ORDER BY ventas_estimadas_perdidas DESC;
GO

/* Query 6: Impacto de promociones en ticket y volumen */
WITH tx_category AS (
  SELECT
    t.transaction_id,
    p.category,
    MAX(CASE WHEN ti.was_on_promo = 1 THEN 1 ELSE 0 END) AS tiene_item_en_promocion,
    SUM(ti.quantity) AS unidades_categoria,
    SUM(ti.quantity * ti.unit_price) AS ventas_categoria,
    MAX(t.total_amount) AS ticket_transaccion
  FROM dbo.transactions t
  JOIN dbo.transaction_items ti ON ti.transaction_id = t.transaction_id
  JOIN dbo.products p ON p.item_id = ti.item_id
  WHERE t.status = 'COMPLETED'
  GROUP BY t.transaction_id, p.category
)
SELECT
  category,
  tiene_item_en_promocion,
  COUNT(DISTINCT transaction_id) AS transacciones,
  AVG(ticket_transaccion) AS ticket_promedio,
  AVG(unidades_categoria * 1.0) AS unidades_promedio,
  AVG(ventas_categoria) AS ventas_promedio_categoria
FROM tx_category
GROUP BY category, tiene_item_en_promocion
ORDER BY category, tiene_item_en_promocion;
GO

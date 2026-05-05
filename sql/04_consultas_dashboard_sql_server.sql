/*
  Consultas del dashboard operativo.
  Estas consultas corresponden a los componentes visibles en bloque5_dashboard.html.

  Puedes ejecutarlas por partes en VS Code para explicar de donde sale cada grafico.
*/

USE RetailPruebaTecnica;
GO

SET DATEFIRST 1; -- lunes como primer dia de la semana

DECLARE @fecha_inicial DATE = '2025-06-24';
DECLARE @fecha_final DATE = '2025-06-30';
DECLARE @pais NVARCHAR(10) = NULL;
DECLARE @formato NVARCHAR(40) = NULL;
DECLARE @region NVARCHAR(80) = NULL;

/* 1. Indicadores principales */
WITH ventas_por_tienda AS (
  SELECT
    s.store_id,
    s.size_sqm,
    SUM(CASE WHEN t.status = 'RETURNED' THEN -t.total_amount ELSE t.total_amount END) AS ventas_netas,
    COUNT(DISTINCT t.transaction_id) AS transacciones
  FROM dbo.transactions t
  JOIN dbo.stores s ON s.store_id = t.store_id
  WHERE t.transaction_date BETWEEN @fecha_inicial AND @fecha_final
    AND (@pais IS NULL OR s.country = @pais)
    AND (@formato IS NULL OR s.format = @formato)
    AND (@region IS NULL OR s.region = @region)
  GROUP BY s.store_id, s.size_sqm
)
SELECT
  SUM(ventas_netas) AS ventas_netas,
  SUM(transacciones) AS transacciones,
  SUM(ventas_netas) / NULLIF(SUM(transacciones), 0) AS ticket_promedio,
  SUM(ventas_netas) / NULLIF(SUM(size_sqm), 0) AS ventas_netas_por_metro_cuadrado
FROM ventas_por_tienda;

/* 2. Tendencia semanal por formato */
SELECT
  DATEADD(day, 1 - DATEPART(weekday, CAST(t.transaction_date AS date)), CAST(t.transaction_date AS date)) AS semana,
  s.format AS formato,
  SUM(CASE WHEN t.status = 'RETURNED' THEN -t.total_amount ELSE t.total_amount END) AS ventas_netas
FROM dbo.transactions t
JOIN dbo.stores s ON s.store_id = t.store_id
WHERE t.transaction_date BETWEEN @fecha_inicial AND @fecha_final
  AND (@pais IS NULL OR s.country = @pais)
  AND (@formato IS NULL OR s.format = @formato)
  AND (@region IS NULL OR s.region = @region)
GROUP BY DATEADD(day, 1 - DATEPART(weekday, CAST(t.transaction_date AS date)), CAST(t.transaction_date AS date)), s.format
ORDER BY semana, formato;

/* 3. Ranking de tiendas por formato y alerta de bajo rendimiento */
WITH ventas_tienda AS (
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
  WHERE t.transaction_date BETWEEN @fecha_inicial AND @fecha_final
    AND (@pais IS NULL OR s.country = @pais)
    AND (@formato IS NULL OR s.format = @formato)
    AND (@region IS NULL OR s.region = @region)
  GROUP BY s.store_id, s.store_name, s.country, s.format, s.region, s.size_sqm
),
scored AS (
  SELECT
    *,
    ventas_netas / NULLIF(size_sqm, 0) AS ventas_netas_por_metro_cuadrado,
    ventas_netas / NULLIF(transacciones, 0) AS ticket_promedio,
    PERCENTILE_CONT(0.25) WITHIN GROUP (ORDER BY ventas_netas / NULLIF(size_sqm, 0))
      OVER (PARTITION BY format) AS percentil_25_formato
  FROM ventas_tienda
)
SELECT TOP 20
  store_id,
  store_name,
  country,
  format,
  region,
  ventas_netas,
  ventas_netas_por_metro_cuadrado,
  ticket_promedio,
  CASE WHEN ventas_netas_por_metro_cuadrado < percentil_25_formato THEN 'BAJO_RENDIMIENTO' ELSE 'OK' END AS alerta
FROM scored
ORDER BY ventas_netas_por_metro_cuadrado DESC;

/* 4. Retencion por cohorte de lealtad */
WITH ventas_lealtad AS (
  SELECT
    customer_id,
    DATEFROMPARTS(YEAR(transaction_date), MONTH(transaction_date), 1) AS mes_compra,
    total_amount
  FROM dbo.transactions
  WHERE loyalty_card = 1 AND customer_id IS NOT NULL AND status = 'COMPLETED'
),
primera_compra AS (
  SELECT customer_id, MIN(mes_compra) AS mes_cohorte
  FROM ventas_lealtad
  GROUP BY customer_id
),
actividad AS (
  SELECT
    p.mes_cohorte,
    DATEDIFF(month, p.mes_cohorte, v.mes_compra) AS mes_relativo,
    v.customer_id,
    v.total_amount
  FROM ventas_lealtad v
  JOIN primera_compra p ON p.customer_id = v.customer_id
)
SELECT
  mes_cohorte,
  COUNT(DISTINCT CASE WHEN mes_relativo = 0 THEN customer_id END) AS clientes_cohorte,
  COUNT(DISTINCT CASE WHEN mes_relativo = 1 THEN customer_id END) * 1.0
    / NULLIF(COUNT(DISTINCT CASE WHEN mes_relativo = 0 THEN customer_id END), 0) AS retencion_mes_1,
  COUNT(DISTINCT CASE WHEN mes_relativo = 2 THEN customer_id END) * 1.0
    / NULLIF(COUNT(DISTINCT CASE WHEN mes_relativo = 0 THEN customer_id END), 0) AS retencion_mes_2,
  COUNT(DISTINCT CASE WHEN mes_relativo = 3 THEN customer_id END) * 1.0
    / NULLIF(COUNT(DISTINCT CASE WHEN mes_relativo = 0 THEN customer_id END), 0) AS retencion_mes_3,
  COUNT(DISTINCT CASE WHEN mes_relativo = 6 THEN customer_id END) * 1.0
    / NULLIF(COUNT(DISTINCT CASE WHEN mes_relativo = 0 THEN customer_id END), 0) AS retencion_mes_6
FROM actividad
GROUP BY mes_cohorte
ORDER BY mes_cohorte;

/* 5. Quiebres activos de venta */
WITH ventas_diarias AS (
  SELECT
    t.store_id,
    ti.item_id,
    CAST(t.transaction_date AS date) AS fecha,
    SUM(ti.quantity * ti.unit_price) AS ventas
  FROM dbo.transaction_items ti
  JOIN dbo.transactions t ON t.transaction_id = ti.transaction_id
  WHERE t.status = 'COMPLETED'
  GROUP BY t.store_id, ti.item_id, CAST(t.transaction_date AS date)
),
gaps_priorizados AS (
  SELECT
    store_id,
    item_id,
    MAX(fecha) AS ultima_fecha_con_venta,
    DATEDIFF(day, MAX(fecha), '2025-06-30') AS dias_sin_venta
  FROM ventas_diarias
  GROUP BY store_id, item_id
  HAVING DATEDIFF(day, MAX(fecha), '2025-06-30') >= 3
)
SELECT TOP 20
  g.store_id,
  s.store_name,
  g.item_id,
  p.item_name,
  p.category,
  g.dias_sin_venta,
  (SELECT SUM(v.ventas) / 14.0
   FROM ventas_diarias v
   WHERE v.store_id = g.store_id
     AND v.item_id = g.item_id
     AND v.fecha BETWEEN DATEADD(day, -14, DATEADD(day, 1, g.ultima_fecha_con_venta)) AND g.ultima_fecha_con_venta)
   * g.dias_sin_venta AS ventas_estimadas_perdidas
FROM gaps_priorizados g
JOIN dbo.stores s ON s.store_id = g.store_id
JOIN dbo.products p ON p.item_id = g.item_id
WHERE (@pais IS NULL OR s.country = @pais)
  AND (@formato IS NULL OR s.format = @formato)
  AND (@region IS NULL OR s.region = @region)
ORDER BY ventas_estimadas_perdidas DESC;
GO

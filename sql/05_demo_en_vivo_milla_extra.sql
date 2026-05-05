/*
  Milla extra - Demo en vivo para la entrevista
  Objetivo: tener consultas cortas, claras y explicables para ejecutar en VS Code.

  Orden sugerido:
  1. Ejecuta "Chequeo de salud".
  2. Ejecuta "Ventas netas por formato".
  3. Ejecuta "Productividad por tienda".
  4. Ejecuta "Asignaciones A/B ambiguas".
  5. Ejecuta "Recomendacion priorizada".
*/

USE RetailPruebaTecnica;
GO

/* 1. Chequeo de salud del dataset */
SELECT
  'transactions' AS tabla,
  COUNT(*) AS filas,
  MIN(transaction_date) AS fecha_minima,
  MAX(transaction_date) AS fecha_maxima
FROM dbo.transactions
UNION ALL
SELECT
  'transaction_items',
  COUNT(*),
  NULL,
  NULL
FROM dbo.transaction_items
UNION ALL
SELECT
  'stores',
  COUNT(*),
  NULL,
  NULL
FROM dbo.stores
UNION ALL
SELECT
  'products',
  COUNT(*),
  NULL,
  NULL
FROM dbo.products;
GO

/* 2. Ventas netas por formato
   Logica: ventas completadas suman, devoluciones restan.
*/
SELECT
  s.format AS formato,
  SUM(CASE WHEN t.status = 'RETURNED' THEN -t.total_amount ELSE t.total_amount END) AS ventas_netas,
  COUNT(DISTINCT t.transaction_id) AS transacciones,
  SUM(CASE WHEN t.status = 'RETURNED' THEN -t.total_amount ELSE t.total_amount END)
    / NULLIF(COUNT(DISTINCT t.transaction_id), 0) AS ticket_promedio
FROM dbo.transactions t
JOIN dbo.stores s ON s.store_id = t.store_id
GROUP BY s.format
ORDER BY ventas_netas DESC;
GO

/* 3. Productividad por tienda en el ultimo trimestre
   Esto replica el criterio visual del dashboard: ventas netas por metro cuadrado
   y alerta contra percentil 25 dentro de cada formato.
*/
DECLARE @fecha_inicial DATE = '2025-04-01';
DECLARE @fecha_final DATE = '2025-06-30';

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
SELECT TOP 12
  store_id,
  store_name,
  country,
  format,
  region,
  ventas_netas,
  ventas_netas_por_metro_cuadrado,
  ticket_promedio,
  CASE
    WHEN ventas_netas_por_metro_cuadrado < percentil_25_formato THEN 'BAJO_RENDIMIENTO'
    ELSE 'OK'
  END AS alerta
FROM scored
ORDER BY ventas_netas_por_metro_cuadrado ASC;
GO

/* 4. Calidad experimental: tiendas asignadas a ambos grupos */
SELECT
  store_id,
  COUNT(DISTINCT variant) AS variantes_distintas,
  STRING_AGG(variant, ', ') AS variantes_detectadas
FROM dbo.store_promotions
GROUP BY store_id
HAVING COUNT(DISTINCT variant) > 1;
GO

/* 5. Recomendacion priorizada: categorias donde conviene actuar primero
   Combina concentracion de ventas con senales de quiebre activo.
*/
WITH ventas_categoria AS (
  SELECT
    p.category,
    SUM(ti.quantity * ti.unit_price) AS ventas_brutas_categoria
  FROM dbo.transaction_items ti
  JOIN dbo.transactions t ON t.transaction_id = ti.transaction_id
  JOIN dbo.products p ON p.item_id = ti.item_id
  WHERE t.status = 'COMPLETED'
  GROUP BY p.category
),
ultima_venta AS (
  SELECT
    t.store_id,
    ti.item_id,
    MAX(CAST(t.transaction_date AS date)) AS ultima_fecha_venta
  FROM dbo.transaction_items ti
  JOIN dbo.transactions t ON t.transaction_id = ti.transaction_id
  WHERE t.status = 'COMPLETED'
  GROUP BY t.store_id, ti.item_id
),
gaps_activos AS (
  SELECT
    p.category,
    COUNT(*) AS productos_tienda_con_gap_activo
  FROM ultima_venta u
  JOIN dbo.products p ON p.item_id = u.item_id
  WHERE DATEDIFF(day, u.ultima_fecha_venta, '2025-06-30') >= 3
  GROUP BY p.category
)
SELECT
  v.category,
  v.ventas_brutas_categoria,
  v.ventas_brutas_categoria * 100.0 / SUM(v.ventas_brutas_categoria) OVER () AS participacion_ventas,
  COALESCE(g.productos_tienda_con_gap_activo, 0) AS productos_tienda_con_gap_activo,
  CASE
    WHEN v.ventas_brutas_categoria * 1.0 / SUM(v.ventas_brutas_categoria) OVER () >= 0.20
      AND COALESCE(g.productos_tienda_con_gap_activo, 0) > 0
      THEN 'PRIORIDAD_ALTA'
    WHEN COALESCE(g.productos_tienda_con_gap_activo, 0) > 0 THEN 'PRIORIDAD_MEDIA'
    ELSE 'MONITOREO'
  END AS recomendacion
FROM ventas_categoria v
LEFT JOIN gaps_activos g ON g.category = v.category
ORDER BY participacion_ventas DESC;
GO

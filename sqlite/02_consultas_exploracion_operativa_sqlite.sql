-- Consultas de exploracion operativa en SQLite

-- 1. Ventas netas por formato.
SELECT
  s.format AS formato,
  ROUND(SUM(v.ventas_netas), 2) AS ventas_netas,
  COUNT(DISTINCT v.transaction_id) AS transacciones,
  ROUND(SUM(v.ventas_netas) / NULLIF(COUNT(DISTINCT v.transaction_id), 0), 2) AS ticket_promedio
FROM v_transacciones_ventas_netas v
JOIN stores s ON s.store_id = v.store_id
GROUP BY s.format
ORDER BY ventas_netas DESC;

-- 2. Productividad por tienda en el ultimo trimestre.
WITH ventas_tienda AS (
  SELECT
    s.store_id,
    s.store_name,
    s.country,
    s.format,
    s.region,
    s.size_sqm,
    SUM(v.ventas_netas) AS ventas_netas,
    COUNT(DISTINCT v.transaction_id) AS transacciones
  FROM v_transacciones_ventas_netas v
  JOIN stores s ON s.store_id = v.store_id
  WHERE DATE(v.transaction_date) BETWEEN DATE('2025-04-01') AND DATE('2025-06-30')
  GROUP BY s.store_id, s.store_name, s.country, s.format, s.region, s.size_sqm
),
scored AS (
  SELECT
    *,
    ventas_netas / NULLIF(size_sqm, 0) AS ventas_netas_por_metro_cuadrado,
    ventas_netas / NULLIF(transacciones, 0) AS ticket_promedio
  FROM ventas_tienda
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
    END) AS percentil_25_formato
  FROM ordenado
  GROUP BY format
)
SELECT
  o.store_id,
  o.store_name,
  o.country,
  o.format,
  o.region,
  ROUND(o.ventas_netas, 2) AS ventas_netas,
  ROUND(o.ventas_netas_por_metro_cuadrado, 2) AS ventas_netas_por_metro_cuadrado,
  ROUND(o.ticket_promedio, 2) AS ticket_promedio,
  CASE
    WHEN o.ventas_netas_por_metro_cuadrado < p.percentil_25_formato THEN 'BAJO_RENDIMIENTO'
    ELSE 'OK'
  END AS alerta
FROM ordenado o
JOIN percentil p ON p.format = o.format
ORDER BY o.ventas_netas_por_metro_cuadrado ASC
LIMIT 12;

-- 3. Calidad experimental: tiendas asignadas a ambos grupos.
SELECT
  store_id,
  COUNT(DISTINCT variant) AS variantes_distintas,
  GROUP_CONCAT(DISTINCT variant) AS variantes_detectadas
FROM store_promotions
GROUP BY store_id
HAVING COUNT(DISTINCT variant) > 1;

-- 4. Recomendacion priorizada por categoria.
WITH ventas_categoria AS (
  SELECT
    p.category,
    SUM(ti.quantity * ti.unit_price) AS ventas_brutas_categoria
  FROM transaction_items ti
  JOIN transactions t ON t.transaction_id = ti.transaction_id
  JOIN products p ON p.item_id = ti.item_id
  WHERE t.status = 'COMPLETED'
  GROUP BY p.category
),
ultima_venta AS (
  SELECT
    t.store_id,
    ti.item_id,
    MAX(DATE(t.transaction_date)) AS ultima_fecha_venta
  FROM transaction_items ti
  JOIN transactions t ON t.transaction_id = ti.transaction_id
  WHERE t.status = 'COMPLETED'
  GROUP BY t.store_id, ti.item_id
),
gaps_activos AS (
  SELECT
    p.category,
    COUNT(*) AS productos_tienda_con_gap_activo
  FROM ultima_venta u
  JOIN products p ON p.item_id = u.item_id
  WHERE JULIANDAY('2025-06-30') - JULIANDAY(u.ultima_fecha_venta) >= 3
  GROUP BY p.category
),
total AS (
  SELECT SUM(ventas_brutas_categoria) AS ventas_totales
  FROM ventas_categoria
)
SELECT
  v.category,
  ROUND(v.ventas_brutas_categoria, 2) AS ventas_brutas_categoria,
  ROUND(v.ventas_brutas_categoria * 100.0 / t.ventas_totales, 2) AS participacion_ventas,
  COALESCE(g.productos_tienda_con_gap_activo, 0) AS productos_tienda_con_gap_activo,
  CASE
    WHEN v.ventas_brutas_categoria * 1.0 / t.ventas_totales >= 0.20
      AND COALESCE(g.productos_tienda_con_gap_activo, 0) > 0
      THEN 'PRIORIDAD_ALTA'
    WHEN COALESCE(g.productos_tienda_con_gap_activo, 0) > 0 THEN 'PRIORIDAD_MEDIA'
    ELSE 'MONITOREO'
  END AS recomendacion
FROM ventas_categoria v
CROSS JOIN total t
LEFT JOIN gaps_activos g ON g.category = v.category
ORDER BY participacion_ventas DESC;

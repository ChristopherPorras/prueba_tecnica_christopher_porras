-- Consultas SQLite para pruebas en vivo.
-- Se pueden copiar y ejecutar con scripts/query_sqlite.py.

-- 1. Ver tablas disponibles.
SELECT
  type AS tipo,
  name AS nombre
FROM sqlite_master
WHERE type IN ('table', 'view')
  AND name NOT LIKE 'sqlite_%'
ORDER BY type, name;

-- 2. Conteo general de tablas base.
SELECT 'transactions' AS tabla, COUNT(*) AS filas FROM transactions
UNION ALL SELECT 'transaction_items', COUNT(*) FROM transaction_items
UNION ALL SELECT 'stores', COUNT(*) FROM stores
UNION ALL SELECT 'products', COUNT(*) FROM products
UNION ALL SELECT 'vendors', COUNT(*) FROM vendors
UNION ALL SELECT 'store_promotions', COUNT(*) FROM store_promotions;

-- 3. Ventas netas totales.
SELECT
  ROUND(SUM(ventas_netas), 2) AS ventas_netas
FROM v_transacciones_ventas_netas;

-- 4. Ventas netas por pais y formato.
SELECT
  s.country AS pais,
  s.format AS formato,
  ROUND(SUM(v.ventas_netas), 2) AS ventas_netas,
  COUNT(DISTINCT v.transaction_id) AS transacciones,
  ROUND(SUM(v.ventas_netas) / NULLIF(COUNT(DISTINCT v.transaction_id), 0), 2) AS ticket_promedio
FROM v_transacciones_ventas_netas v
JOIN stores s ON s.store_id = v.store_id
GROUP BY s.country, s.format
ORDER BY ventas_netas DESC;

-- 5. Top 10 tiendas por ventas netas.
SELECT
  s.store_id,
  s.store_name,
  s.country,
  s.format,
  ROUND(SUM(v.ventas_netas), 2) AS ventas_netas
FROM v_transacciones_ventas_netas v
JOIN stores s ON s.store_id = v.store_id
GROUP BY s.store_id, s.store_name, s.country, s.format
ORDER BY ventas_netas DESC
LIMIT 10;

-- 6. Ventas por categoria.
SELECT
  p.category,
  ROUND(SUM(ti.quantity * ti.unit_price), 2) AS ventas_brutas,
  SUM(ti.quantity) AS unidades
FROM transaction_items ti
JOIN transactions t ON t.transaction_id = ti.transaction_id
JOIN products p ON p.item_id = ti.item_id
WHERE t.status = 'COMPLETED'
GROUP BY p.category
ORDER BY ventas_brutas DESC;

-- 7. Devoluciones por formato.
SELECT
  s.format,
  COUNT(*) AS transacciones_devueltas,
  ROUND(SUM(t.total_amount), 2) AS monto_devuelto
FROM transactions t
JOIN stores s ON s.store_id = t.store_id
WHERE t.status = 'RETURNED'
GROUP BY s.format
ORDER BY monto_devuelto DESC;

-- 8. Calidad de clientes identificados.
SELECT
  loyalty_card,
  CASE WHEN customer_id IS NULL THEN 'SIN_CLIENTE' ELSE 'CON_CLIENTE' END AS estado_cliente,
  COUNT(*) AS transacciones
FROM transactions
GROUP BY loyalty_card, estado_cliente
ORDER BY loyalty_card, estado_cliente;

-- 9. Productos con proveedor inexistente.
SELECT
  p.item_id,
  p.item_name,
  p.vendor_id,
  p.category
FROM products p
LEFT JOIN vendors v ON v.vendor_id = p.vendor_id
WHERE v.vendor_id IS NULL
ORDER BY p.item_id;

-- 10. Tiendas con doble asignacion A/B.
SELECT
  store_id,
  COUNT(DISTINCT variant) AS variantes_distintas,
  GROUP_CONCAT(DISTINCT variant) AS variantes_detectadas
FROM store_promotions
GROUP BY store_id
HAVING COUNT(DISTINCT variant) > 1;

-- 11. Productividad por tienda usando tabla del Bloque 1.
-- Primero ejecutar: py scripts\run_sqlite_block1.py
SELECT
  store_id,
  store_name,
  country,
  format,
  ventas_netas,
  ventas_netas_por_metro_cuadrado,
  alerta_rendimiento
FROM bloque1_q2_productividad_tienda
ORDER BY ventas_netas_por_metro_cuadrado ASC
LIMIT 20;

-- 12. Guardar una prueba en vivo como tabla.
-- Ejemplo de comando:
-- py scripts\query_sqlite.py "SELECT format, COUNT(*) AS tiendas FROM stores GROUP BY format;" --save prueba_tiendas_por_formato

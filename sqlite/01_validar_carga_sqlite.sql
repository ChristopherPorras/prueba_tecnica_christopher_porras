-- Validacion de carga en SQLite

SELECT
  'transactions' AS tabla,
  COUNT(*) AS filas,
  MIN(transaction_date) AS fecha_minima,
  MAX(transaction_date) AS fecha_maxima
FROM transactions
UNION ALL
SELECT 'transaction_items', COUNT(*), NULL, NULL FROM transaction_items
UNION ALL
SELECT 'stores', COUNT(*), NULL, NULL FROM stores
UNION ALL
SELECT 'products', COUNT(*), NULL, NULL FROM products
UNION ALL
SELECT 'vendors', COUNT(*), NULL, NULL FROM vendors
UNION ALL
SELECT 'store_promotions', COUNT(*), NULL, NULL FROM store_promotions;

-- Transacciones donde el total no coincide con la suma de items.
WITH suma_items AS (
  SELECT
    transaction_id,
    SUM(quantity * unit_price) AS total_items
  FROM transaction_items
  GROUP BY transaction_id
)
SELECT
  COUNT(*) AS transacciones_con_diferencia,
  ROUND(MAX(ABS(t.total_amount - s.total_items)), 2) AS diferencia_maxima
FROM transactions t
JOIN suma_items s ON s.transaction_id = t.transaction_id
WHERE ABS(t.total_amount - s.total_items) > 0.01;

-- Productos con proveedor inexistente.
SELECT
  COUNT(*) AS productos_con_vendor_inexistente
FROM products p
LEFT JOIN vendors v ON v.vendor_id = p.vendor_id
WHERE v.vendor_id IS NULL;

-- Tiendas asignadas a mas de una variante experimental.
SELECT
  store_id,
  COUNT(DISTINCT variant) AS variantes_distintas,
  GROUP_CONCAT(DISTINCT variant) AS variantes_detectadas
FROM store_promotions
GROUP BY store_id
HAVING COUNT(DISTINCT variant) > 1;

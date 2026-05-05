/*
  Prueba tecnica retail - Paso 02
  Validaciones rapidas despues de cargar CSV.
*/

USE RetailPruebaTecnica;
GO

SELECT 'vendors' AS tabla, COUNT(*) AS filas FROM dbo.vendors
UNION ALL SELECT 'products', COUNT(*) FROM dbo.products
UNION ALL SELECT 'stores', COUNT(*) FROM dbo.stores
UNION ALL SELECT 'store_promotions', COUNT(*) FROM dbo.store_promotions
UNION ALL SELECT 'transactions', COUNT(*) FROM dbo.transactions
UNION ALL SELECT 'transaction_items', COUNT(*) FROM dbo.transaction_items;

SELECT
  MIN(transaction_date) AS fecha_minima,
  MAX(transaction_date) AS fecha_maxima,
  COUNT(*) AS transacciones,
  SUM(CASE WHEN status = 'COMPLETED' THEN 1 ELSE 0 END) AS transacciones_completadas,
  SUM(CASE WHEN status = 'RETURNED' THEN 1 ELSE 0 END) AS devoluciones
FROM dbo.transactions;

SELECT
  COUNT(*) AS transacciones_sin_cliente,
  COUNT(*) * 100.0 / NULLIF((SELECT COUNT(*) FROM dbo.transactions), 0) AS porcentaje_sin_cliente
FROM dbo.transactions
WHERE customer_id IS NULL;

SELECT
  SUM(CASE WHEN p.vendor_id IS NOT NULL AND v.vendor_id IS NULL THEN 1 ELSE 0 END) AS productos_con_proveedor_inexistente
FROM dbo.products p
LEFT JOIN dbo.vendors v ON v.vendor_id = p.vendor_id;

WITH suma_items AS (
  SELECT transaction_id, SUM(quantity * unit_price) AS total_items
  FROM dbo.transaction_items
  GROUP BY transaction_id
)
SELECT
  COUNT(*) AS transacciones_con_diferencia,
  MAX(ABS(t.total_amount - s.total_items)) AS diferencia_maxima
FROM dbo.transactions t
JOIN suma_items s ON s.transaction_id = t.transaction_id
WHERE ABS(t.total_amount - s.total_items) > 0.01;

SELECT
  sp.store_id,
  COUNT(DISTINCT sp.variant) AS variantes_asignadas,
  STRING_AGG(sp.variant, ', ') AS variantes
FROM dbo.store_promotions sp
GROUP BY sp.store_id
HAVING COUNT(DISTINCT sp.variant) > 1;
GO

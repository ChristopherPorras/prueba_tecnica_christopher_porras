-- Bloque 1 - SQL avanzado
-- Dialecto: BigQuery Standard SQL.
-- Supuesto: los CSV fueron cargados como tablas transactions, transaction_items, stores, products, vendors y store_promotions.
-- Ventas netas: COMPLETED suma positivo y RETURNED resta.

-- Query 1: Ventas comparables
DECLARE current_start DATE DEFAULT DATE '2025-01-01';
DECLARE current_end DATE DEFAULT DATE '2025-06-30';
DECLARE previous_start DATE DEFAULT DATE_SUB(current_start, INTERVAL 1 YEAR);
DECLARE previous_end DATE DEFAULT DATE_SUB(current_end, INTERVAL 1 YEAR);

WITH transacciones_base AS (
  SELECT
    t.transaction_id,
    DATE(t.transaction_date) AS fecha_transaccion,
    t.store_id,
    CASE WHEN t.status = 'RETURNED' THEN -t.total_amount ELSE t.total_amount END AS ventas_netas
  FROM transactions t
),
tiendas_comparables AS (
  SELECT store_id, store_name, country, format
  FROM stores
  WHERE DATE(opening_date) <= previous_start
),
ventas AS (
  SELECT
    s.country,
    s.format,
    s.store_id,
    s.store_name,
    SUM(IF(t.fecha_transaccion BETWEEN current_start AND current_end, t.ventas_netas, 0)) AS ventas_netas_periodo_actual,
    SUM(IF(t.fecha_transaccion BETWEEN previous_start AND previous_end, t.ventas_netas, 0)) AS ventas_netas_periodo_anterior
  FROM transacciones_base t
  JOIN tiendas_comparables s USING (store_id)
  WHERE t.fecha_transaccion BETWEEN previous_start AND current_end
  GROUP BY 1, 2, 3, 4
)
SELECT
  country,
  format,
  store_id,
  store_name,
  ventas_netas_periodo_actual,
  ventas_netas_periodo_anterior,
  SAFE_DIVIDE(ventas_netas_periodo_actual, ventas_netas_periodo_anterior) - 1 AS crecimiento_ventas_comparables_pct,
  DENSE_RANK() OVER (
    PARTITION BY format
    ORDER BY SAFE_DIVIDE(ventas_netas_periodo_actual, ventas_netas_periodo_anterior) - 1 DESC
  ) AS ranking_crecimiento_tienda_formato
FROM ventas
WHERE ventas_netas_periodo_actual <> 0
  AND ventas_netas_periodo_anterior <> 0
ORDER BY format, ranking_crecimiento_tienda_formato;

-- Query 2: Productividad por metro cuadrado
WITH parametros AS (
  SELECT DATE '2025-04-01' AS fecha_inicio_trimestre, DATE '2025-06-30' AS fecha_fin_trimestre
),
ventas_tienda AS (
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
  JOIN stores s USING (store_id)
  CROSS JOIN parametros p
  WHERE DATE(t.transaction_date) BETWEEN p.fecha_inicio_trimestre AND p.fecha_fin_trimestre
  GROUP BY 1, 2, 3, 4, 5, 6
),
tiendas_calculadas AS (
  SELECT
    *,
    SAFE_DIVIDE(ventas_netas, size_sqm) AS ventas_netas_por_metro_cuadrado,
    SAFE_DIVIDE(transacciones, size_sqm) AS transacciones_por_metro_cuadrado,
    SAFE_DIVIDE(ventas_netas, transacciones) AS ticket_promedio,
    PERCENTILE_CONT(SAFE_DIVIDE(ventas_netas, size_sqm), 0.25) OVER (PARTITION BY format) AS percentil_25_ventas_por_metro_cuadrado
  FROM ventas_tienda
)
SELECT
  *,
  DENSE_RANK() OVER (PARTITION BY format ORDER BY ventas_netas_por_metro_cuadrado DESC) AS ranking_en_formato,
  IF(ventas_netas_por_metro_cuadrado < percentil_25_ventas_por_metro_cuadrado, 'BAJO_RENDIMIENTO', 'OK') AS alerta_rendimiento
FROM tiendas_calculadas
ORDER BY format, ranking_en_formato;

-- Query 3: Cohortes de clientes con tarjeta de lealtad
WITH transacciones_lealtad AS (
  SELECT
    customer_id,
    transaction_id,
    DATE_TRUNC(DATE(transaction_date), MONTH) AS mes_compra,
    total_amount
  FROM transactions
  WHERE loyalty_card = TRUE
    AND customer_id IS NOT NULL
    AND status = 'COMPLETED'
),
primera_compra AS (
  SELECT customer_id, MIN(mes_compra) AS mes_cohorte
  FROM transacciones_lealtad
  GROUP BY 1
),
actividad AS (
  SELECT
    p.mes_cohorte,
    DATE_DIFF(t.mes_compra, p.mes_cohorte, MONTH) AS mes_relativo,
    t.customer_id,
    t.total_amount
  FROM transacciones_lealtad t
  JOIN primera_compra p USING (customer_id)
),
tamano_cohorte AS (
  SELECT mes_cohorte, COUNT(DISTINCT customer_id) AS clientes_cohorte
  FROM primera_compra
  GROUP BY 1
),
metricas AS (
  SELECT
    a.mes_cohorte,
    a.mes_relativo,
    COUNT(DISTINCT a.customer_id) AS clientes_activos,
    AVG(a.total_amount) AS ticket_promedio,
    ANY_VALUE(tc.clientes_cohorte) AS clientes_cohorte,
    SAFE_DIVIDE(COUNT(DISTINCT a.customer_id), ANY_VALUE(tc.clientes_cohorte)) AS tasa_retencion
  FROM actividad a
  JOIN tamano_cohorte tc USING (mes_cohorte)
  WHERE mes_relativo IN (0, 1, 2, 3, 6)
  GROUP BY 1, 2
)
SELECT
  mes_cohorte,
  MAX(clientes_cohorte) AS clientes_cohorte,
  MAX(IF(mes_relativo = 0, tasa_retencion, NULL)) AS retencion_mes_0,
  MAX(IF(mes_relativo = 1, tasa_retencion, NULL)) AS retencion_mes_1,
  MAX(IF(mes_relativo = 2, tasa_retencion, NULL)) AS retencion_mes_2,
  MAX(IF(mes_relativo = 3, tasa_retencion, NULL)) AS retencion_mes_3,
  MAX(IF(mes_relativo = 6, tasa_retencion, NULL)) AS retencion_mes_6,
  MAX(IF(mes_relativo = 0, ticket_promedio, NULL)) AS ticket_promedio_mes_0,
  MAX(IF(mes_relativo = 1, ticket_promedio, NULL)) AS ticket_promedio_mes_1,
  MAX(IF(mes_relativo = 2, ticket_promedio, NULL)) AS ticket_promedio_mes_2,
  MAX(IF(mes_relativo = 3, ticket_promedio, NULL)) AS ticket_promedio_mes_3,
  MAX(IF(mes_relativo = 6, ticket_promedio, NULL)) AS ticket_promedio_mes_6,
  CASE
    WHEN MAX(IF(mes_relativo = 6, ticket_promedio, NULL)) > MAX(IF(mes_relativo = 0, ticket_promedio, NULL)) THEN 'CRECE'
    WHEN MAX(IF(mes_relativo = 6, ticket_promedio, NULL)) < MAX(IF(mes_relativo = 0, ticket_promedio, NULL)) THEN 'DECRECE'
    ELSE 'SIN_DATOS'
  END AS tendencia_ticket_mes_0_a_mes_6
FROM metricas
GROUP BY mes_cohorte
ORDER BY mes_cohorte;

-- Query 4: Retorno de margen bruto sobre inversion por proveedor y categoria
WITH ventas_item AS (
  SELECT
    p.vendor_id,
    COALESCE(v.vendor_name, 'SIN_VENDOR') AS vendor_name,
    p.category,
    ti.item_id,
    DATE(t.transaction_date) AS fecha_venta,
    ti.quantity,
    ti.quantity * ti.unit_price AS ventas_brutas_item,
    ti.quantity * p.cost AS costo_total
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
  SUM(ventas_brutas_item) AS ventas_brutas_items,
  SUM(costo_total) AS costo_total,
  SUM(ventas_brutas_item) - SUM(costo_total) AS margen_bruto,
  SAFE_DIVIDE(SUM(ventas_brutas_item) - SUM(costo_total), SUM(costo_total)) AS retorno_margen_bruto_sobre_costo,
  COUNT(DISTINCT item_id) AS items_activos,
  SAFE_DIVIDE(SUM(quantity), DATE_DIFF(MAX(fecha_venta), MIN(fecha_venta), DAY) + 1) AS velocidad_unidades_por_dia,
  IF(SAFE_DIVIDE(SUM(ventas_brutas_item) - SUM(costo_total), SUM(costo_total)) < 1, 'RETORNO_MARGEN_BAJO_1', 'OK') AS alerta_retorno_margen
FROM ventas_item
GROUP BY 1, 2, 3
ORDER BY retorno_margen_bruto_sobre_costo ASC;

-- Query 5: Deteccion de posibles quiebres de stock
WITH parametros AS (SELECT DATE '2025-06-30' AS fecha_maxima),
ventas_diarias AS (
  SELECT
    t.store_id,
    ti.item_id,
    DATE(t.transaction_date) AS fecha_venta,
    SUM(ti.quantity) AS unidades,
    SUM(ti.quantity * ti.unit_price) AS ventas_brutas
  FROM transaction_items ti
  JOIN transactions t USING (transaction_id)
  WHERE t.status = 'COMPLETED'
  GROUP BY 1, 2, 3
),
limites_tienda_item AS (
  SELECT store_id, item_id, MIN(fecha_venta) AS primera_fecha_venta, (SELECT fecha_maxima FROM parametros) AS fecha_maxima
  FROM ventas_diarias
  GROUP BY 1, 2
),
calendario AS (
  SELECT l.store_id, l.item_id, dia AS fecha_calendario
  FROM limites_tienda_item l, UNNEST(GENERATE_DATE_ARRAY(l.primera_fecha_venta, l.fecha_maxima)) AS dia
),
dias_sin_venta AS (
  SELECT
    c.store_id,
    c.item_id,
    c.fecha_calendario,
    DATE_SUB(c.fecha_calendario, INTERVAL ROW_NUMBER() OVER (PARTITION BY c.store_id, c.item_id ORDER BY c.fecha_calendario) DAY) AS clave_grupo
  FROM calendario c
  LEFT JOIN ventas_diarias v
    ON v.store_id = c.store_id
   AND v.item_id = c.item_id
   AND v.fecha_venta = c.fecha_calendario
  WHERE v.fecha_venta IS NULL
),
ausencias AS (
  SELECT
    store_id,
    item_id,
    MIN(fecha_calendario) AS fecha_inicio_ausencia,
    MAX(fecha_calendario) AS fecha_fin_ausencia,
    COUNT(*) AS dias_sin_venta
  FROM dias_sin_venta
  GROUP BY 1, 2, clave_grupo
  HAVING COUNT(*) >= 3
),
ausencias_priorizadas AS (
  SELECT
    a.*,
    SAFE_DIVIDE((
      SELECT SUM(v.ventas_brutas)
      FROM ventas_diarias v
      WHERE v.store_id = a.store_id
        AND v.item_id = a.item_id
        AND v.fecha_venta BETWEEN DATE_SUB(a.fecha_inicio_ausencia, INTERVAL 14 DAY) AND DATE_SUB(a.fecha_inicio_ausencia, INTERVAL 1 DAY)
    ), 14) AS venta_diaria_promedio_previa
  FROM ausencias a
)
SELECT
  a.store_id,
  s.store_name,
  a.item_id,
  p.item_name,
  p.category,
  COALESCE(v.vendor_name, 'SIN_VENDOR') AS vendor_name,
  a.fecha_inicio_ausencia,
  a.fecha_fin_ausencia,
  a.dias_sin_venta,
  a.venta_diaria_promedio_previa,
  a.venta_diaria_promedio_previa * a.dias_sin_venta AS venta_estimada_perdida
FROM ausencias_priorizadas a
JOIN stores s USING (store_id)
JOIN products p USING (item_id)
LEFT JOIN vendors v USING (vendor_id)
ORDER BY venta_estimada_perdida DESC;

-- Query 6: Impacto de promociones en ticket y volumen
WITH transaccion_categoria AS (
  SELECT
    t.transaction_id,
    p.category,
    LOGICAL_OR(ti.was_on_promo) AS tiene_item_en_promocion,
    SUM(ti.quantity) AS unidades_categoria,
    SUM(ti.quantity * ti.unit_price) AS ventas_categoria,
    ANY_VALUE(t.total_amount) AS ticket_transaccion
  FROM transactions t
  JOIN transaction_items ti USING (transaction_id)
  JOIN products p USING (item_id)
  WHERE t.status = 'COMPLETED'
  GROUP BY 1, 2
),
agregado AS (
  SELECT
    category,
    tiene_item_en_promocion,
    COUNT(DISTINCT transaction_id) AS transacciones,
    AVG(ticket_transaccion) AS ticket_promedio,
    AVG(unidades_categoria) AS unidades_promedio,
    AVG(ventas_categoria) AS ventas_promedio_categoria
  FROM transaccion_categoria
  GROUP BY 1, 2
)
SELECT
  category,
  MAX(IF(tiene_item_en_promocion, transacciones, NULL)) AS transacciones_con_promocion,
  MAX(IF(NOT tiene_item_en_promocion, transacciones, NULL)) AS transacciones_sin_promocion,
  MAX(IF(tiene_item_en_promocion, ticket_promedio, NULL)) AS ticket_promedio_con_promocion,
  MAX(IF(NOT tiene_item_en_promocion, ticket_promedio, NULL)) AS ticket_promedio_sin_promocion,
  MAX(IF(tiene_item_en_promocion, ticket_promedio, NULL)) - MAX(IF(NOT tiene_item_en_promocion, ticket_promedio, NULL)) AS diferencia_ticket_promedio,
  MAX(IF(tiene_item_en_promocion, unidades_promedio, NULL)) AS unidades_promedio_con_promocion,
  MAX(IF(NOT tiene_item_en_promocion, unidades_promedio, NULL)) AS unidades_promedio_sin_promocion,
  MAX(IF(tiene_item_en_promocion, unidades_promedio, NULL)) - MAX(IF(NOT tiene_item_en_promocion, unidades_promedio, NULL)) AS diferencia_unidades_promedio,
  MAX(IF(tiene_item_en_promocion, ventas_promedio_categoria, NULL)) - MAX(IF(NOT tiene_item_en_promocion, ventas_promedio_categoria, NULL)) AS diferencia_ventas_categoria_promedio,
  CASE
    WHEN MAX(IF(tiene_item_en_promocion, unidades_promedio, NULL)) > MAX(IF(NOT tiene_item_en_promocion, unidades_promedio, NULL))
     AND MAX(IF(tiene_item_en_promocion, ticket_promedio, NULL)) >= MAX(IF(NOT tiene_item_en_promocion, ticket_promedio, NULL))
    THEN 'UPLIFT_REAL'
    WHEN MAX(IF(tiene_item_en_promocion, unidades_promedio, NULL)) > MAX(IF(NOT tiene_item_en_promocion, unidades_promedio, NULL))
    THEN 'MAS_UNIDADES_CON_MENOR_TICKET'
    ELSE 'SIN_UPLIFT_CLARO'
  END AS lectura_promocion
FROM agregado
GROUP BY category
ORDER BY category;

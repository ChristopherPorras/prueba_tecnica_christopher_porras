# Bloque 2 - Modelo dimensional, pipeline y gobernanza

## A. Star schema propuesto para BigQuery

Grano principal: una fila por item vendido dentro de una transaccion (`fact_sales_item`). Este grano soporta retorno de margen bruto sobre inversion, promociones, categorias, proveedores y composicion del basket. Para indicadores de tienda se agrega a `fact_store_day` como tabla derivada/materializada.

### Hechos

| Tabla | Grano | Campos clave |
| --- | --- | --- |
| `fact_sales_item` | Item por transaccion | transaction_item_id, transaction_id, date_key, store_key, product_key, customer_key nullable, promotion_key nullable, quantity, unit_price, gross_gmv, net_gmv, unit_cost, gross_margin |
| `fact_transaction` | Transaccion | transaction_id, date_key, store_key, customer_key nullable, payment_method, status, total_amount, net_gmv, loyalty_card |
| `fact_store_day` | Tienda-dia | date_key, store_key, net_gmv, transactions, avg_ticket, gmv_per_sqm, returned_amount |
| `fact_stock_gap` | Gap tienda-producto | store_key, product_key, gap_start_date_key, gap_end_date_key, gap_days, avg_daily_gmv_before_gap, estimated_lost_gmv |
| `fact_cohort_month` | Cohorte-mes | cohort_month_key, month_n, active_customers, retention_rate, avg_ticket |

### Dimensiones

| Tabla | Campos |
| --- | --- |
| `dim_date` | date_key, date, week_start, month, quarter, year, fiscal_week |
| `dim_store` | store_key, store_id, store_name, country, city, format, size_sqm, opening_date, region |
| `dim_product` | product_key, item_id, item_name, brand, vendor_key, category, department, cost |
| `dim_vendor` | vendor_key, vendor_id, vendor_name, country, tier, is_shared_catalog |
| `dim_customer` | customer_key, customer_hash, loyalty_segment, first_purchase_month. Para compradores anonimos usar customer_key = -1 |
| `dim_promotion` | promotion_key, promo_name, variant, start_date, end_date, promo_type |

## Decisiones de diseno

1. `customer_id` nulo se modela como comprador anonimo. El 59.8% de transacciones no tiene cliente identificado; forzar un customer_id falso inflaria retencion. Para cohortes solo se usa `loyalty_card = TRUE`.
2. Se separa `fact_sales_item` de `fact_transaction`. La auditoria muestra 1,745 diferencias entre total de transaccion y suma de items; tienda y ticket deben usar el total reportado, mientras categoria/proveedor necesita el item.
3. `fact_store_day` es una tabla derivada. Comp Sales, productividad y dashboard diario necesitan respuestas rapidas por tienda/dia sin recalcular 542k lineas cada vez.
4. `dim_promotion` queda en una dimension separada porque una tienda puede tener experimentos por ventana temporal. Las asignaciones ambiguas se auditan y no se sobreescriben silenciosamente.
5. `fact_stock_gap` es una tabla operacional derivada. No representa inventario real; representa senales de ausencia de venta y debe cruzarse con inventario/ordenes cuando existan.

## B. Pipeline ETL/ELT

1. Ingesta raw cada hora a `raw_*` con particion por fecha de llegada y hash de archivo.
2. Staging valida tipos, llaves, duplicados y montos. Los errores se escriben en `dq_findings`.
3. Carga incremental usa `transaction_id` y `transaction_item_id` como llaves naturales con `MERGE`. Si llega el mismo ID, se actualiza solo si cambia el hash de fila.
4. Para retrasos de hasta 2 horas, el pipeline reprocesa una ventana movil de 3 horas y el cierre diario reprocesa D-1 completo.
5. Para detectar tiendas sin datos, se compara cada tienda activa contra su patron esperado. Si no reporta transacciones por 2 horas en horario operativo, se emite alerta; si falta un dia completo, se bloquea certificacion del dashboard.
6. Refresh diario: staging horario, marts de BI a las 05:00 hora local con reintento a las 06:00. El dashboard consume solo tablas certificadas.

## C. Gobernanza

- `customer_id` debe hashearse con salt administrado por Data Platform. Analistas ven `customer_hash`, no PII directa.
- Data owner de transacciones: Operaciones Retail/Ventas; Data Steward tecnico: Data Engineering.
- Si dos reportes muestran ventas netas distintas, primero se revisa la definicion certificada de ventas netas, luego filtros de status/returns, granularidad item vs transaccion, timezone y fecha de actualizacion. La resolucion se documenta en un changelog de metricas.

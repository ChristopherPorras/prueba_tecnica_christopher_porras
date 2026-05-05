# Bloque 0 - Auditoria de calidad de datos

Periodo observado: 2024-01-01 a 2025-06-30. Dataset: 174,880 transacciones, 542,015 items, 40 tiendas, 200 productos.

| Dimension | Pregunta | Evidencia | Lectura | Decision |
| --- | --- | --- | --- | --- |
| Completitud | Transacciones sin customer_id | 104,632 de 174,880 (59.8%) | Es consistente: no hay customer_id nulo con loyalty_card = TRUE ni customer_id informado con loyalty_card = FALSE. | Mantener customer_id nulo como comprador anonimo. En cohortes usar solo loyalty_card = TRUE. |
| Consistencia | total_amount vs suma de items | 1,745 transacciones (1.0%) con diferencia > $0.01; delta maximo $202.68. | La mayoria de diferencias son negativas: el total reportado es menor que la suma de items. | Para indicadores de ventas netas usar total_amount a nivel transaccion; para categoria/proveedor usar line_gmv y documentar la diferencia. |
| Unicidad | transaction_id duplicados | 0 | No se detectaron duplicados. | No se requiere deduplicacion para esta version. |
| Validez | Montos cero/negativos y precios cero | 3 transacciones con total_amount <= 0; 231 items con unit_price = 0 sin promo. | Hay ventas completadas con monto cero y precios cero que no estan explicados por promocion. | Excluir transacciones con total_amount <= 0 de tickets promedio; marcar items con precio cero como alerta de pricing/master data. |
| Integridad referencial | FKs contra dimensiones | 0 store_id invalidos; 0 item_id invalidos; 5 productos con vendor_id inexistente. | Cinco productos apuntan a VND_031, que no existe en vendors. | Mantener esos productos con vendor 'SIN_VENDOR' en analisis de categoria y levantar incidente de master data. |
| Frescura | Gaps diarios por tienda | 2 tiendas con gaps. Maximos: TIENDA_037 135 dias, TIENDA_012 7 dias | TIENDA_037 tiene 135 dias sin venta antes de iniciar actividad; TIENDA_012 tiene 7 dias sin datos en septiembre 2024. | Tratar TIENDA_037 como gap esperado por apertura; revisar TIENDA_012 como alerta operativa. |
| Integridad temporal | Ventas antes de opening_date | 50 transacciones, todas en TIENDA_037 entre 2024-05-15 y 2024-05-31. | La tienda tiene opening_date 2024-06-01 pero ventas desde 2024-05-15. | No excluir del analisis historico, pero corregir opening_date o confirmar soft-opening. |
| A/B Test | Tiendas en CONTROL y TREATMENT | 2 tiendas: TIENDA_008, TIENDA_037 | TIENDA_008 y TIENDA_037 aparecen asignadas a ambos grupos. | Excluir estas tiendas del A/B test primario y reportarlas como falla de diseno experimental. |

## Notas de uso en bloques siguientes

- Ventas netas: `COMPLETED` suma positivo y `RETURNED` resta. Para el A/B test se usan solo transacciones completadas.
- Los analisis por proveedor mantienen productos con vendor faltante como `SIN_VENDOR` cuando aplica.
- Las tiendas con doble asignacion experimental se excluyen del resultado estadistico principal.
- Los gaps de stock son senales operativas, no prueba definitiva de quiebre: se priorizan por ventas estimadas perdidas y velocidad previa.
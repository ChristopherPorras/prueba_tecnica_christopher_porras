# Bloque 4 - Framework de KPIs para productividad de tiendas

| KPI | Definicion exacta | Formula | Frecuencia | Fuente de datos | Target sugerido | Como detectas si el dato esta mal |
| --- | --- | --- | --- | --- | --- | --- |
| GMV/m2 | GMV neto por metro cuadrado | GMV neto / size_sqm | Semanal | fact_store_day + dim_store | >= p50 del formato | size_sqm nulo/cero, GMV negativo sin returns |
| Transacciones/m2 | Cantidad de tickets por area | transactions / size_sqm | Semanal | fact_store_day | >= p50 del formato | Caida >30% vs media movil sin alerta de cierre |
| Ticket promedio neto | Venta neta por transaccion | GMV neto / transacciones | Diario | fact_transaction | +3% YoY comparable | Total <=0 o transacciones duplicadas |
| Conversion de lealtad | Participacion de tickets identificados | tx con loyalty_card / tx totales | Semanal | fact_transaction | 45% en 6 meses | customer_id nulo con loyalty_card TRUE |
| Retencion M1 | Clientes de cohorte que vuelven al mes 1 | clientes activos M1 / tamano cohorte | Mensual | fact_cohort_month | >=70% | Cohorte sin customer_hash o month_n negativo |
| Indice de quiebre | GMV perdido estimado por falta de venta | estimated_lost_gmv / GMV neto | Diario | fact_stock_gap + fact_store_day | <2% del GMV | Gap en producto sin ventas historicas |
| GMROI | Retorno de margen sobre costo | (GMV - costo) / costo | Mensual | fact_sales_item + dim_product | >1.5 por vendor-categoria | Costo nulo/cero o vendor inexistente |
| Fill-rate proxy | Leading indicator de abastecimiento | 1 - items activos con gap 3+ dias / items activos | Diario | fact_stock_gap | >=97% | Item marcado activo sin ventas ultimos 180 dias |
| Productivity Health Score | KPI compuesto de productividad | 0.4 GMV/m2 + 0.25 tx/m2 + 0.2 ticket + 0.15 fill-rate normalizados | Semanal | Marts certificados | >=75/100 | Alguna metrica base faltante o fuera de rango |

## North Star Metric

**Productivity Health Score** es la North Star Metric del programa. Combina resultado financiero (GMV/m2), actividad operativa (transacciones/m2), experiencia/comportamiento de cliente (ticket y retencion via componentes) y disponibilidad (fill-rate proxy). Es mejor que usar solo GMV porque evita premiar tiendas grandes que venden mucho pero son ineficientes o tienen problemas de stock.

## Leading indicator

El **Fill-rate proxy** funciona como indicador predictivo: si empiezan gaps de venta en productos activos, el GMV futuro probablemente caera antes de que el cierre mensual lo muestre.
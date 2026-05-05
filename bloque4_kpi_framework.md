# Bloque 4 - Framework de indicadores para productividad de tiendas

| Indicador | Definicion exacta | Formula | Frecuencia | Fuente de datos | Objetivo sugerido | Como detectas si el dato esta mal |
| --- | --- | --- | --- | --- | --- | --- |
| Ventas netas por metro cuadrado | Ventas netas por cada metro cuadrado de tienda | Ventas netas / metros cuadrados de tienda | Semanal | fact_store_day + dim_store | >= p50 del formato | Metros cuadrados nulos/cero, ventas negativas sin devoluciones |
| Transacciones por metro cuadrado | Cantidad de tickets por cada metro cuadrado | Transacciones / metros cuadrados de tienda | Semanal | fact_store_day | >= p50 del formato | Caida >30% vs media movil sin alerta de cierre |
| Ticket promedio neto | Venta neta por transaccion | Ventas netas / transacciones | Diario | fact_transaction | +3% contra el mismo periodo del ano anterior | Total <=0 o transacciones duplicadas |
| Conversion de lealtad | Participacion de tickets identificados | Transacciones con loyalty_card / transacciones totales | Semanal | fact_transaction | 45% en 6 meses | customer_id nulo con loyalty_card TRUE |
| Retencion mes 1 | Clientes de cohorte que vuelven al mes 1 | Clientes activos en mes 1 / tamano cohorte | Mensual | fact_cohort_month | >=70% | Cohorte sin customer_hash o month_n negativo |
| Indice de quiebre | Ventas estimadas perdidas por falta de venta | Ventas estimadas perdidas / ventas netas | Diario | fact_stock_gap + fact_store_day | <2% de ventas netas | Gap en producto sin ventas historicas |
| Retorno de margen bruto sobre inversion | Retorno de margen sobre costo | (Ventas - costo) / costo | Mensual | fact_sales_item + dim_product | >1.5 por proveedor-categoria | Costo nulo/cero o proveedor inexistente |
| Indice estimado de disponibilidad | Indicador anticipado de abastecimiento | 1 - items activos con ausencia de venta 3+ dias / items activos | Diario | fact_stock_gap | >=97% | Item marcado activo sin ventas ultimos 180 dias |
| Puntaje de salud de productividad | Indicador compuesto de productividad | 0.4 ventas netas por metro cuadrado + 0.25 transacciones por metro cuadrado + 0.2 ticket + 0.15 disponibilidad normalizados | Semanal | Marts certificados | >=75/100 | Alguna metrica base faltante o fuera de rango |

## Metrica principal

**Puntaje de salud de productividad** es la metrica principal del programa. Combina resultado financiero (ventas netas por metro cuadrado), actividad operativa (transacciones por metro cuadrado), experiencia/comportamiento de cliente (ticket y retencion via componentes) y disponibilidad estimada. Es mejor que usar solo ventas porque evita premiar tiendas grandes que venden mucho pero son ineficientes o tienen problemas de stock.

## Indicador anticipado

El **indice estimado de disponibilidad** funciona como indicador predictivo: si empiezan ausencias de venta en productos activos, las ventas netas futuras probablemente caeran antes de que el cierre mensual lo muestre.
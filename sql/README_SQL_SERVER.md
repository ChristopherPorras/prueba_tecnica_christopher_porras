# SQL Server desde VS Code

La prueba permite SQL estandar o BigQuery SQL; `bloque1_queries.sql` esta escrito en BigQuery Standard SQL por legibilidad y funciones analiticas.

Si durante la entrevista quieren verlo en SQL Server:

1. Conecta la extension MSSQL de VS Code a un servidor SQL Server disponible.
2. Crea tablas equivalentes a los CSV.
3. Importa los CSV desde el servidor o usa el asistente de importacion disponible en tu entorno.
4. Traduce funciones puntuales:
   - `DATE_TRUNC(..., MONTH)` -> `DATEFROMPARTS(YEAR(fecha), MONTH(fecha), 1)`
   - `DATE_DIFF(a,b,MONTH)` -> `DATEDIFF(MONTH,b,a)`
   - `SAFE_DIVIDE(x,y)` -> `x / NULLIF(y,0)`
   - `LOGICAL_OR` -> `MAX(CASE WHEN condicion THEN 1 ELSE 0 END)`

No se incluye dependencia a MSSQL local porque la computadora de trabajo no permite instalarlo.

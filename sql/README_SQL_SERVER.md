# SQL Server desde VS Code

Esta carpeta permite demostrar la prueba tecnica como trabajo de base de datos usando la extension MSSQL de VS Code.

## Requisito

La extension MSSQL de VS Code es solo el cliente. Necesitas conectarte a un SQL Server existente: servidor de la empresa, Azure SQL, una maquina remota o un SQL Server ya instalado por TI. No necesitas instalar SQL Server localmente en tu computadora de trabajo.

## Orden recomendado

1. Abre VS Code en la carpeta del repo.
2. Instala o abre la extension **SQL Server (MSSQL)**.
3. Crea una conexion a tu servidor desde el panel de la extension.
4. Ejecuta los archivos en este orden:

| Orden | Archivo | Que hace |
| --- | --- | --- |
| 1 | `00_crear_tablas_sql_server.sql` | Crea la base `RetailPruebaTecnica`, tablas e indices. |
| 2 | `01_cargar_csv_sql_server.sql` | Carga los CSV de `data/raw` usando staging tables. |
| 3 | `02_validar_carga_sql_server.sql` | Valida conteos, fechas, diferencias y asignaciones A/B. |
| 4 | `03_bloque1_queries_sql_server.sql` | Ejecuta las seis queries avanzadas del Bloque 1 en T-SQL. |
| 5 | `04_consultas_dashboard_sql_server.sql` | Consultas usadas para explicar cada componente del dashboard. |
| 6 | `05_demo_en_vivo_milla_extra.sql` | Consultas cortas para ejecutar durante la entrevista sin esperar procesos pesados. |

## Punto importante sobre carga de CSV

`BULK INSERT` lee archivos desde la maquina donde corre SQL Server, no desde VS Code. Si el servidor no puede leer tu carpeta local:

- usa el asistente **Import Flat File** de la extension MSSQL si esta disponible en tu entorno;
- o copia los CSV a una ruta compartida/accesible para el servidor;
- o pide una base temporal y sube los CSV con la herramienta corporativa permitida.

## Como ejecutar una query en VS Code

1. Abre un archivo `.sql`.
2. Selecciona la conexion en la parte superior del editor.
3. Selecciona la base `RetailPruebaTecnica`.
4. Ejecuta todo el archivo o selecciona una consulta especifica.
5. Revisa los resultados en el panel inferior.

## Demo recomendada para entrevista

Si tienes poco tiempo, ejecuta solo:

1. `02_validar_carga_sql_server.sql`
2. `05_demo_en_vivo_milla_extra.sql`

Con eso muestras conteos, ventas netas, productividad, calidad del A/B test y una recomendacion priorizada.

## Equivalencia con BigQuery

El archivo `bloque1_queries.sql` conserva la version BigQuery Standard SQL pedida por la prueba. El archivo `03_bloque1_queries_sql_server.sql` es la version ejecutable en SQL Server.

Traducciones principales:

- `DATE_TRUNC(..., MONTH)` -> `DATEFROMPARTS(YEAR(fecha), MONTH(fecha), 1)`
- `DATE_DIFF(a, b, MONTH)` -> `DATEDIFF(MONTH, b, a)`
- `SAFE_DIVIDE(x, y)` -> `x / NULLIF(y, 0)`
- `LOGICAL_OR` -> `MAX(CASE WHEN condicion THEN 1 ELSE 0 END)`

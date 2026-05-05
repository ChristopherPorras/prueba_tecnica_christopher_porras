# Guia rapida: SQLite en VS Code

SQLite no usa `Server name`, usuario, password ni certificado. La base es un archivo local.

## Antes de empezar: error comun con MSSQL

Si VS Code muestra errores como:

```text
Incorrect syntax near 'LIMIT'
owner: mssql
```

la consulta no esta fallando en SQLite. Lo que pasa es que la extension de SQL
Server esta validando archivos SQLite como si fueran T-SQL.

Para evitarlo:

- No ejecutes los archivos de la carpeta `sqlite/` con la extension MSSQL.
- Usa `py scripts\query_sqlite.py` para ejecutar consultas.
- Usa `py scripts\run_sqlite_block1.py --preview 5` para crear las tablas del Bloque 1.
- Abre `data/retail_prueba_tecnica.sqlite` con SQLite Viewer para ver las tablas.

El repo incluye `.vscode/settings.json` para abrir los SQL de `sqlite/` como
texto y evitar diagnosticos falsos de MSSQL.

## 1. Crear la base

Desde la carpeta del proyecto:

```bash
python scripts/create_sqlite_db.py
```

En Windows, si `python` no responde:

```powershell
py scripts\create_sqlite_db.py
```

Resultado esperado:

```text
data/retail_prueba_tecnica.sqlite
```

## 2. Conectarlo en VS Code

Opcion visual:

1. Instala una extension de SQLite para VS Code, por ejemplo `SQLite Viewer` o `SQLite`.
2. Abre el archivo `data/retail_prueba_tecnica.sqlite`.
3. Expande las tablas y vistas.

Tablas principales:

- `transactions`
- `transaction_items`
- `stores`
- `products`
- `vendors`
- `store_promotions`

Vistas utiles:

- `v_transacciones_ventas_netas`
- `v_items_ventas`

## 3. Usarlo desde terminal

Forma recomendada, sin depender de `sqlite-utils`:

```bash
python scripts/query_sqlite.py "SELECT COUNT(*) AS transacciones FROM transactions;"
python scripts/query_sqlite.py "SELECT ROUND(SUM(ventas_netas), 2) AS ventas_netas FROM v_transacciones_ventas_netas;"
python scripts/query_sqlite.py --tables
python scripts/query_sqlite.py --schema transactions
```

En Windows, si `python` no responde:

```powershell
py scripts\query_sqlite.py "SELECT COUNT(*) AS transacciones FROM transactions;"
py scripts\query_sqlite.py "SELECT ROUND(SUM(ventas_netas), 2) AS ventas_netas FROM v_transacciones_ventas_netas;"
py scripts\query_sqlite.py --tables
py scripts\query_sqlite.py --schema transactions
```

Para una consulta de varias lineas en PowerShell:

```powershell
@"
SELECT
  s.format AS formato,
  ROUND(SUM(v.ventas_netas), 2) AS ventas_netas
FROM v_transacciones_ventas_netas v
JOIN stores s ON s.store_id = v.store_id
GROUP BY s.format
ORDER BY ventas_netas DESC;
"@ | py scripts\query_sqlite.py --stdin
```

Alternativa si `sqlite-utils` esta disponible en tu terminal:

```bash
sqlite-utils tables data/retail_prueba_tecnica.sqlite
sqlite-utils query data/retail_prueba_tecnica.sqlite "SELECT COUNT(*) AS transacciones FROM transactions;" --table
sqlite-utils query data/retail_prueba_tecnica.sqlite "SELECT ROUND(SUM(ventas_netas), 2) AS ventas_netas FROM v_transacciones_ventas_netas;" --table
```

Si PowerShell dice que `sqlite-utils` no se reconoce, no es problema de la base: significa que ese comando no esta en el PATH de Windows. Usa `py scripts\query_sqlite.py` para evitar ese bloqueo.

## 4. Consultas listas para exponer

Archivos:

- `sqlite/01_validar_carga_sqlite.sql`
- `sqlite/02_consultas_exploracion_operativa_sqlite.sql`
- `sqlite/03_bloque1_queries_sqlite.sql`
- `sqlite/04_consultas_en_vivo_sqlite.sql`

Si tu extension de SQLite permite abrir archivos `.sql`, abre esos archivos y ejecuta las consultas por bloques.

Si prefieres terminal, copia una consulta del archivo y ejecutala con:

```bash
python scripts/query_sqlite.py "PEGAR_CONSULTA_AQUI"
```

Para guardar el resultado de cualquier consulta como tabla visible en SQLite Viewer:

```powershell
py scripts\query_sqlite.py "SELECT format, COUNT(*) AS tiendas FROM stores GROUP BY format;" --save prueba_tiendas_por_formato
```

Luego refresca SQLite Viewer y abre la tabla `prueba_tiendas_por_formato`.

## 5. Ejecutar todo el Bloque 1 y verlo en SQLite Viewer

Ejecuta:

```bash
python scripts/run_sqlite_block1.py
```

En Windows:

```powershell
py scripts\run_sqlite_block1.py --preview 5
```

El comando crea estas tablas dentro de `data/retail_prueba_tecnica.sqlite`:

- `bloque1_q1_ventas_comparables`
- `bloque1_q2_productividad_tienda`
- `bloque1_q3_cohortes_lealtad`
- `bloque1_q4_retorno_margen_proveedor_categoria`
- `bloque1_q5_posibles_quiebres_stock`
- `bloque1_q6_promociones_ticket_volumen`

La tabla de posibles quiebres de stock puede tardar alrededor de 30 a 60 segundos porque revisa calendario por tienda-producto. Despues de creada, abrirla desde SQLite Viewer es inmediato.

Para verlas en SQLite Viewer:

1. Abre `data/retail_prueba_tecnica.sqlite`.
2. Refresca la conexion o vuelve a abrir el archivo.
3. Expande Tables.
4. Abre cualquiera de las tablas `bloque1_q...`.

Para consultar una tabla del Bloque 1 desde terminal:

```powershell
py scripts\query_sqlite.py "SELECT * FROM bloque1_q1_ventas_comparables LIMIT 20;"
py scripts\query_sqlite.py "SELECT * FROM bloque1_q2_productividad_tienda WHERE alerta_rendimiento = 'BAJO_RENDIMIENTO';"
```

## 6. Pruebas en vivo

Para cualquier prueba que pidan:

1. Identificar columnas con `py scripts\query_sqlite.py --schema nombre_tabla`.
2. Ejecutar la consulta con `py scripts\query_sqlite.py "SELECT ..."` para verla en terminal.
3. Si quieren verla en SQLite Viewer, repetir con `--save nombre_resultado`.
4. Refrescar SQLite Viewer y abrir la tabla guardada.

Consultas listas para copiar estan en `sqlite/04_consultas_en_vivo_sqlite.sql`.

## 7. Criterio tecnico para usar SQLite

SQLite permite demostrar el trabajo de base de datos sin permisos de administrador y sin depender de un servidor local. Para la prueba local, el objetivo es mostrar modelo, carga, validacion y consultas de negocio con una base real.

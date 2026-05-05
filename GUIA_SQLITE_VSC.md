# Guia rapida: SQLite en VS Code

SQLite funciona diferente a SQL Server: no hay `Server name`, usuario, password ni certificado. La base es un archivo local.

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
```

En Windows, si `python` no responde:

```powershell
py scripts\query_sqlite.py "SELECT COUNT(*) AS transacciones FROM transactions;"
py scripts\query_sqlite.py "SELECT ROUND(SUM(ventas_netas), 2) AS ventas_netas FROM v_transacciones_ventas_netas;"
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

Si tu extension de SQLite permite abrir archivos `.sql`, abre esos archivos y ejecuta las consultas por bloques.

Si prefieres terminal, copia una consulta del archivo y ejecutala con:

```bash
python scripts/query_sqlite.py "PEGAR_CONSULTA_AQUI"
```

## 5. Criterio tecnico para usar SQLite

SQLite permite demostrar el trabajo de base de datos sin permisos de administrador y sin depender de un servidor local. Para produccion usaria SQL Server, BigQuery u otro motor corporativo; para la prueba local, el objetivo es mostrar modelo, carga, validacion y consultas de negocio con una base real.

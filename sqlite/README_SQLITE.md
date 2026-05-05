# SQLite desde VS Code

SQLite no usa servidor, usuario ni password. La base es un archivo local `.sqlite`.

## Crear la base local

Desde la carpeta del repo:

```bash
python scripts/create_sqlite_db.py
```

En Windows, si `python` no responde:

```powershell
py scripts\create_sqlite_db.py
```

Esto crea:

```text
data/retail_prueba_tecnica.sqlite
```

## Abrirlo en VS Code

Opcion visual:

1. Instala una extension de SQLite para VS Code, por ejemplo `SQLite Viewer` o `SQLite`.
2. Abre `data/retail_prueba_tecnica.sqlite`.
3. Revisa las tablas: `transactions`, `transaction_items`, `stores`, `products`, `vendors`, `store_promotions`.

Opcion terminal:

```bash
python scripts/query_sqlite.py "SELECT COUNT(*) AS transacciones FROM transactions;"
sqlite-utils tables data/retail_prueba_tecnica.sqlite
sqlite-utils query data/retail_prueba_tecnica.sqlite "SELECT COUNT(*) AS transacciones FROM transactions;" --table
```

En Windows, si `sqlite-utils` no se reconoce, usa:

```powershell
py scripts\query_sqlite.py "SELECT COUNT(*) AS transacciones FROM transactions;"
```

## Consultas preparadas

| Archivo | Uso |
| --- | --- |
| `01_validar_carga_sqlite.sql` | Valida conteos, fechas, diferencias entre transaccion e items y calidad A/B. |
| `02_consultas_exploracion_operativa_sqlite.sql` | Consultas cortas para explicar ventas netas, productividad y recomendacion operativa. |

## Diferencia contra SQL Server

La extension MSSQL de VS Code no se usa para SQLite. MSSQL pide `Server name`, autenticacion y certificado porque se conecta a un servidor. SQLite abre un archivo local, por eso la conexion es simplemente la ruta del archivo `.sqlite`.

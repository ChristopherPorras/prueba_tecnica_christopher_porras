# SQLite desde VS Code

SQLite no usa servidor, usuario ni password. La base es un archivo local `.sqlite`.

## Si aparecen errores de MSSQL en archivos SQLite

Si en VS Code ves errores como `Incorrect syntax near 'LIMIT'` con `owner: mssql`,
no significa que la consulta este mala. Significa que la extension de SQL Server
esta leyendo un archivo SQLite como si fuera T-SQL.

Para esta prueba:

- Ejecuta las consultas con `py scripts\query_sqlite.py`.
- Ejecuta todo el Bloque 1 con `py scripts\run_sqlite_block1.py --preview 5`.
- Abre `data/retail_prueba_tecnica.sqlite` con SQLite Viewer para ver tablas.
- No ejecutes los archivos de `sqlite/` con la extension MSSQL.

El proyecto incluye `.vscode/settings.json` para que los `.sql` dentro de
`sqlite/` se abran como texto y no generen diagnosticos falsos de SQL Server.

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
```

En Windows, si `python` no responde, usa:

```powershell
py scripts\query_sqlite.py "SELECT COUNT(*) AS transacciones FROM transactions;"
```

## Consultas preparadas

| Archivo | Uso |
| --- | --- |
| `01_validar_carga_sqlite.sql` | Valida conteos, fechas, diferencias entre transaccion e items y calidad A/B. |
| `02_consultas_exploracion_operativa_sqlite.sql` | Consultas cortas para explicar ventas netas, productividad y recomendacion operativa. |
| `03_bloque1_queries_sqlite.sql` | Crea las seis tablas de resultado del Bloque 1. |
| `04_consultas_en_vivo_sqlite.sql` | Consultas listas para copiar durante pruebas en vivo. |

## Bloque 1 completo

Ejecuta:

```bash
python scripts/run_sqlite_block1.py
```

En Windows:

```powershell
py scripts\run_sqlite_block1.py
```

Con vista previa:

```powershell
py scripts\run_sqlite_block1.py --preview 5
```

Despues refresca SQLite Viewer y abre estas tablas:

- `bloque1_q1_ventas_comparables`
- `bloque1_q2_productividad_tienda`
- `bloque1_q3_cohortes_lealtad`
- `bloque1_q4_retorno_margen_proveedor_categoria`
- `bloque1_q5_posibles_quiebres_stock`
- `bloque1_q6_promociones_ticket_volumen`

La consulta de posibles quiebres de stock es la mas pesada porque revisa dias sin venta por tienda-producto. Es normal que tarde mas que las demas al crear la tabla.

## Guardar cualquier resultado para SQLite Viewer

```powershell
py scripts\query_sqlite.py "SELECT format, COUNT(*) AS tiendas FROM stores GROUP BY format;" --save prueba_tiendas_por_formato
```

Luego refresca SQLite Viewer y abre la tabla creada.

## Conexion

SQLite abre directamente el archivo local `.sqlite`; no necesita servidor, autenticacion ni certificado.

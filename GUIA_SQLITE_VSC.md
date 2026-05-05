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

Como ya tienes `sqlite-utils`, puedes consultar asi:

```bash
sqlite-utils tables data/retail_prueba_tecnica.sqlite
sqlite-utils query data/retail_prueba_tecnica.sqlite "SELECT COUNT(*) AS transacciones FROM transactions;" --table
sqlite-utils query data/retail_prueba_tecnica.sqlite "SELECT ROUND(SUM(ventas_netas), 2) AS ventas_netas FROM v_transacciones_ventas_netas;" --table
```

## 4. Consultas listas para exponer

Archivos:

- `sqlite/01_validar_carga_sqlite.sql`
- `sqlite/02_consultas_exploracion_operativa_sqlite.sql`

Si tu extension de SQLite permite abrir archivos `.sql`, abre esos archivos y ejecuta las consultas por bloques.

Si prefieres terminal, copia una consulta del archivo y ejecutala con:

```bash
sqlite-utils query data/retail_prueba_tecnica.sqlite "PEGAR_CONSULTA_AQUI" --table
```

## 5. Criterio tecnico para usar SQLite

SQLite permite demostrar el trabajo de base de datos sin permisos de administrador y sin depender de un servidor local. Para produccion usaria SQL Server, BigQuery u otro motor corporativo; para la prueba local, el objetivo es mostrar modelo, carga, validacion y consultas de negocio con una base real.

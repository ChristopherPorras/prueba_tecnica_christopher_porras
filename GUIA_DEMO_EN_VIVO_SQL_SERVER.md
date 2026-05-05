# Guia rapida: SQL Server en VS Code y demo en vivo

## 1. Que necesitas

Necesitas tres cosas:

1. VS Code.
2. Extension **SQL Server (MSSQL)**.
3. Acceso a un SQL Server existente: servidor corporativo, Azure SQL, maquina remota o una instancia ya instalada por TI.

La extension MSSQL no es el motor de base de datos; es el cliente para conectarte y ejecutar T-SQL.

## 2. Como hacer que SQL Server se vea en VS Code

1. Abre VS Code.
2. Ve a Extensions.
3. Busca `mssql`.
4. Instala **SQL Server (mssql)** de Microsoft.
5. Abre el icono de SQL Server en la barra izquierda. Tambien puedes usar `Ctrl+Alt+D`.
6. Selecciona **Add Connection** o **Create Connection Profile**.
7. Completa:
   - Server name: servidor o IP. Si tiene puerto: `servidor,1433`.
   - Authentication type: lo que te den, por ejemplo SQL Login, Windows Authentication o Microsoft Entra ID.
   - User y Password si aplica.
   - Trust server certificate: normalmente activado para pruebas internas.
   - Database: puedes dejar default al inicio.
8. Cuando conecte, abre el Object Explorer y expande:
   - Databases
   - RetailPruebaTecnica
   - Tables

Si no ves tablas despues de crearlas, presiona refresh en Object Explorer.

## 3. Como ejecutar los scripts del repo

Ejecuta estos archivos en orden:

1. `sql/00_crear_tablas_sql_server.sql`
2. `sql/01_cargar_csv_sql_server.sql`
3. `sql/02_validar_carga_sql_server.sql`
4. `sql/03_bloque1_queries_sql_server.sql`
5. `sql/04_consultas_dashboard_sql_server.sql`
6. `sql/05_demo_en_vivo_milla_extra.sql`

En `01_cargar_csv_sql_server.sql` cambia esta linea:

```sql
DECLARE @data_path NVARCHAR(4000) = N'C:\CAMBIA_ESTA_RUTA\prueba_tecnica_christopher_porras\data\raw\';
```

por la ruta real de tu carpeta `data/raw`.

## 4. Si BULK INSERT no funciona

Esto es normal en ambientes corporativos. `BULK INSERT` lee archivos desde donde corre SQL Server, no desde tu VS Code.

Opciones:

- Usa **Import Flat File** en la extension MSSQL.
- Copia los CSV a una carpeta accesible por el servidor.
- Pide una base temporal y una ruta de carga permitida.
- Si solo necesitas demo, ejecuta `02_validar_carga` y `05_demo_en_vivo` sobre una base ya cargada.

## 5. Guion para impresionar en vivo

Di esto mientras ejecutas:

1. “Primero valido carga y calidad, porque no confio en un dashboard si no entiendo la base.”
2. Ejecuta `02_validar_carga_sql_server.sql`.
3. “Ahora muestro la metrica central: ventas netas. Las devoluciones restan.”
4. Ejecuta la consulta 2 de `05_demo_en_vivo_milla_extra.sql`.
5. “Aqui convierto ventas en productividad operativa, normalizando por tamano de tienda.”
6. Ejecuta la consulta 3.
7. “Y cierro con una decision: no escalaria el A/B test porque el diseno tiene dos tiendas contaminadas.”
8. Ejecuta la consulta 4.

## 6. Frase de cierre

“No solo arme graficas. Arme un flujo defendible: carga, auditoria, metricas, modelo, decision y recomendaciones operativas.”

## Referencias oficiales

- [Microsoft Learn: MSSQL extension para VS Code](https://learn.microsoft.com/en-us/sql/tools/visual-studio-code-extensions/mssql/mssql-extension-visual-studio-code?view=sql-server-ver16).
- [Microsoft Learn: Quickstart para conectar y consultar una base desde VS Code](https://learn.microsoft.com/en-us/sql/tools/visual-studio-code-extensions/mssql/connect-database-visual-studio-code?view=sql-server-ver16).

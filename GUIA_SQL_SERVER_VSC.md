# Guia rapida: SQL Server en VS Code

## 1. Que necesitas

Necesitas tres cosas:

1. VS Code.
2. Extension **SQL Server (MSSQL)**.
3. Acceso a un SQL Server existente: servidor corporativo, Azure SQL, maquina remota o una instancia ya instalada por TI.

La extension MSSQL no es el motor de base de datos; es el cliente para conectarte y ejecutar T-SQL.

## 2. Que poner en cada campo de conexion

| Campo | Que poner | Como conseguirlo |
| --- | --- | --- |
| Profile Name | Un nombre local para identificar la conexion, por ejemplo `RetailPruebaTecnica - Trabajo`. | Lo defines tu. Solo sirve para reconocer la conexion en VS Code. |
| Connection Group | `<Default>`. | Dejalo asi, salvo que quieras agrupar conexiones por proyecto. |
| Input type | `Parameters`. | Es la opcion mas practica porque llenas campo por campo. Usa `Load from Connection String` solo si TI te entrega una cadena completa. |
| Server name | El servidor real de SQL Server. Ejemplos: `SERVIDOR`, `SERVIDOR,1433`, `SERVIDOR\INSTANCIA` o `miservidor.database.windows.net`. | Te lo da TI/DBA, Azure Portal, Fabric o las propiedades de una conexion ya existente en SSMS/VS Code. |
| Trust server certificate | Activado si es un servidor interno o si aparece error de certificado. | En ambientes corporativos es comun por certificados internos. Si TI indica otra politica, sigue esa indicacion. |
| Authentication type | El metodo que te asignen: `SQL Login`, `Windows Authentication` o `Microsoft Entra ID`. | Lo define TI/DBA. Si la pantalla esta en `SQL Login`, necesitas usuario y clave de SQL Server. |
| User name | Usuario de SQL Server. | Te lo entrega TI/DBA. No es tu usuario de GitHub. Solo es tu usuario de Windows si TI indica autenticacion integrada. |
| Password | Clave del usuario SQL. | Te la entrega TI/DBA o el portal corporativo de credenciales. |
| Save Password | Opcional. | Activarlo solo si la computadora es segura y la politica de la empresa lo permite. |
| Database name | `RetailPruebaTecnica` cuando la base ya exista. Si todavia no existe, dejalo vacio o usa `master` para ejecutar el script de creacion. | El script `sql/00_crear_tablas_sql_server.sql` crea `RetailPruebaTecnica`. |
| Encrypt | `Mandatory` si VS Code lo exige. | Mantenerlo asi. Si falla por certificado, activa `Trust server certificate`. |

Punto clave: si no tienes `Server name`, `Authentication type`, `User name` y `Password`, no puedes conectarte todavia. La extension de VS Code no crea el servidor; solo se conecta a uno existente.

## 3. Como hacer que SQL Server se vea en VS Code

1. Abre VS Code.
2. Ve a Extensions.
3. Busca `mssql`.
4. Instala **SQL Server (mssql)** de Microsoft.
5. Abre el icono de SQL Server en la barra izquierda. Tambien puedes usar `Ctrl+Alt+D`.
6. Selecciona **Add Connection** o **Create Connection Profile**.
7. Completa los campos segun la tabla anterior.
8. Cuando conecte, abre el Object Explorer y expande:
   - Databases
   - RetailPruebaTecnica
   - Tables

Si no ves tablas despues de crearlas, presiona refresh en Object Explorer.

## 4. Como obtener los datos de conexion

Normalmente salen de uno de estos lugares:

- Correo, ticket o documentacion de TI con el servidor, puerto, base, usuario y tipo de autenticacion.
- Azure Portal, si la base esta en Azure SQL: busca el SQL server y copia el `Server name`.
- Microsoft Fabric, si el entorno usa Warehouse/Lakehouse con endpoint SQL.
- Una conexion existente de un companero en SSMS o Azure Data Studio: revisar propiedades de conexion.
- Un DBA o lider tecnico: pedir servidor, base temporal, usuario SQL y permisos de lectura/escritura.

Si solo te entregan una connection string, cambia `Input type` a `Load from Connection String` y pegala completa.

## 5. Como ejecutar los scripts del repo

Ejecuta estos archivos en orden:

1. `sql/00_crear_tablas_sql_server.sql`
2. `sql/01_cargar_csv_sql_server.sql`
3. `sql/02_validar_carga_sql_server.sql`
4. `sql/03_bloque1_queries_sql_server.sql`
5. `sql/04_consultas_dashboard_sql_server.sql`
6. `sql/05_consultas_exploracion_operativa.sql`

En `01_cargar_csv_sql_server.sql` cambia esta linea:

```sql
DECLARE @data_path NVARCHAR(4000) = N'C:\CAMBIA_ESTA_RUTA\prueba_tecnica_christopher_porras\data\raw\';
```

por la ruta real de tu carpeta `data/raw`.

## 6. Si BULK INSERT no funciona

Esto es normal en ambientes corporativos. `BULK INSERT` lee archivos desde donde corre SQL Server, no desde tu VS Code.

Opciones:

- Usa **Import Flat File** en la extension MSSQL.
- Copia los CSV a una carpeta accesible por el servidor.
- Pide una base temporal y una ruta de carga permitida.
- Si la base ya esta cargada, ejecuta `02_validar_carga_sql_server.sql` y `05_consultas_exploracion_operativa.sql`.

## 7. Ruta corta de revision

Orden recomendado para revisar la solucion desde SQL Server:

1. Ejecutar `02_validar_carga_sql_server.sql` para validar conteos y calidad.
2. Ejecutar la consulta de ventas netas por formato en `05_consultas_exploracion_operativa.sql`.
3. Ejecutar productividad por tienda para explicar ventas netas por metro cuadrado.
4. Revisar asignaciones A/B ambiguas y justificar por que el experimento necesita repetirse.
5. Cerrar con la recomendacion priorizada por categoria y riesgo operativo.

## 8. Cierre tecnico

La solucion se puede defender como un flujo completo: carga, auditoria, metricas, modelo, decision y recomendaciones operativas.

## Referencias oficiales

- [Microsoft Learn: MSSQL extension para VS Code](https://learn.microsoft.com/en-us/sql/tools/visual-studio-code-extensions/mssql/mssql-extension-visual-studio-code?view=sql-server-ver16).
- [Microsoft Learn: Quickstart para conectar y consultar una base desde VS Code](https://learn.microsoft.com/en-us/sql/tools/visual-studio-code-extensions/mssql/connect-database-visual-studio-code?view=sql-server-ver16).

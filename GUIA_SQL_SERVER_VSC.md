# Guia rapida: SQL Server en VS Code

## 1. Que necesitas

Necesitas tres cosas:

1. VS Code.
2. Extension **SQL Server (MSSQL)**.
3. Un motor de SQL Server corriendo en la computadora. Puede ser `SQL Server`, `SQL Server Express` o `LocalDB`.

La extension MSSQL no es el motor de base de datos; es el cliente para conectarte y ejecutar T-SQL. Si la computadora no tiene ningun motor local, VS Code no puede crear la base por si solo.

## 2. Que poner en cada campo de conexion

| Campo | Que poner | Como conseguirlo |
| --- | --- | --- |
| Profile Name | `RetailPruebaTecnica Local`. | Lo defines tu. Solo sirve para reconocer la conexion en VS Code. |
| Connection Group | `<Default>`. | Dejalo asi, salvo que quieras agrupar conexiones por proyecto. |
| Input type | `Parameters`. | Es la opcion mas practica porque llenas campo por campo. |
| Server name | Prueba en este orden: `localhost`, `localhost\SQLEXPRESS`, `(localdb)\MSSQLLocalDB`. | Sale de las instancias locales instaladas en Windows. Abajo estan los comandos para revisarlo. |
| Trust server certificate | Activado. | Para trabajo local evita errores de certificado. |
| Authentication type | `Windows Authentication`, si esta disponible. | Es lo normal para SQL Server local o LocalDB. Si solo tienes `SQL Login`, necesitas un usuario SQL creado dentro de esa instancia. |
| User name | Dejalo vacio con `Windows Authentication`. | Solo se llena si usas `SQL Login`. |
| Password | Dejalo vacio con `Windows Authentication`. | Solo se llena si usas `SQL Login`. |
| Save Password | No hace falta con `Windows Authentication`. | Activarlo solo si usas `SQL Login` y la computadora es segura. |
| Database name | `RetailPruebaTecnica` cuando la base ya exista. Si todavia no existe, dejalo vacio o usa `master` para ejecutar el script de creacion. | El script `sql/00_crear_tablas_sql_server.sql` crea `RetailPruebaTecnica`. |
| Encrypt | `Mandatory` si VS Code lo exige. | Mantenerlo asi. Si falla por certificado, activa `Trust server certificate`. |

Punto clave: si `localhost`, `localhost\SQLEXPRESS` y `(localdb)\MSSQLLocalDB` fallan, probablemente esa computadora no tiene SQL Server local instalado. En ese caso la extension no alcanza: hace falta que exista el motor de base de datos.

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

## 4. Como saber que instancia local tienes

En la HP abre PowerShell y ejecuta:

```powershell
Get-Service | Where-Object {$_.Name -like 'MSSQL*' -or $_.Name -like 'SQLBrowser'} | Select-Object Name, Status, DisplayName
```

Interpretacion:

| Resultado | Server name en VS Code |
| --- | --- |
| `MSSQLSERVER` en estado `Running` | `localhost` |
| `MSSQL$SQLEXPRESS` en estado `Running` | `localhost\SQLEXPRESS` |
| No aparece ningun servicio SQL Server | Probar LocalDB con el siguiente comando |

Para revisar LocalDB:

```powershell
sqllocaldb info
```

Interpretacion:

| Resultado | Server name en VS Code |
| --- | --- |
| Aparece `MSSQLLocalDB` | `(localdb)\MSSQLLocalDB` |
| `sqllocaldb` no se reconoce o no lista instancias | No hay LocalDB disponible |

Si el servicio existe pero esta detenido, en una computadora con permisos suficientes se puede iniciar desde Servicios de Windows. Si no tienes permisos, ahi si necesitas que la computadora ya lo tenga iniciado.

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

`BULK INSERT` lee archivos desde donde corre SQL Server. Si el servidor es local, la ruta debe existir en esa misma computadora.

Opciones:

- Usa **Import Flat File** en la extension MSSQL.
- Copia los CSV a una ruta corta, por ejemplo `C:\Temp\prueba_tecnica\data\raw\`.
- Verifica que el usuario que ejecuta SQL Server tenga permiso de lectura sobre esa carpeta.
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

# Prueba tecnica Data Analyst - Christopher Porras

[![Python](https://img.shields.io/badge/Python-3.x-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/)
[![SQLite](https://img.shields.io/badge/SQLite-local-003B57?style=for-the-badge&logo=sqlite&logoColor=white)](https://www.sqlite.org/)
[![VS Code](https://img.shields.io/badge/VS%20Code-ready-007ACC?style=for-the-badge&logo=visualstudiocode&logoColor=white)](https://code.visualstudio.com/)
[![Pandas](https://img.shields.io/badge/Pandas-analysis-150458?style=for-the-badge&logo=pandas&logoColor=white)](https://pandas.pydata.org/)
[![ReportLab](https://img.shields.io/badge/ReportLab-PDF-C00000?style=for-the-badge&logo=adobeacrobatreader&logoColor=white)](https://www.reportlab.com/)
[![GitHub](https://img.shields.io/badge/GitHub-repository-181717?style=for-the-badge&logo=github&logoColor=white)](https://github.com/ChristopherPorras/prueba_tecnica_christopher_porras)

Solucion completa de una prueba tecnica de analisis de datos para retail multiformato en Centroamerica. El proyecto cubre auditoria de calidad, SQL avanzado, modelo dimensional, analisis exploratorio, prueba A/B, framework de indicadores, dashboard operativo regional y presentacion ejecutiva.

**Repositorio:** [https://github.com/ChristopherPorras/prueba_tecnica_christopher_porras](https://github.com/ChristopherPorras/prueba_tecnica_christopher_porras)

## Resumen ejecutivo

El objetivo fue convertir datasets transaccionales en una historia analitica defendible: que esta pasando, donde estan los riesgos, que tiendas/categorias priorizar y como explicar la logica tecnica en vivo. La solucion esta pensada para ejecutarse en VS Code sin instalar SQL Server local, usando SQLite como base portable.

| Area | Resultado |
| --- | --- |
| Datos | 174,880 transacciones, 542,015 items, 40 tiendas, 200 productos |
| Periodo | 2024-01-01 a 2025-06-30 |
| Base local | `data/retail_prueba_tecnica.sqlite` |
| Dashboard | `bloque5_dashboard.html` con filtros desplegables por país, formato, región, tienda y rango de fechas |
| Presentacion | `bloque5_presentacion_EN.pdf` |
| SQL ejecutable | `sqlite/03_bloque1_queries_sqlite.sql` |

## Tecnologias y herramientas

| Tecnologia | Uso en el proyecto |
| --- | --- |
| Python | Orquestacion, limpieza, analisis y generacion de entregables |
| pandas / numpy | Transformaciones, metricas, cohortes, productividad y prueba A/B |
| SQLite | Base local sin servidor, usuario, password ni permisos de administrador |
| SQL | Consultas avanzadas, ventanas, cohortes, rankings, gaps y agregaciones |
| ReportLab | Presentacion ejecutiva PDF |
| HTML / SVG / JavaScript | Dashboard operativo y visualizaciones locales |
| Mermaid | Diagrama del modelo dimensional |
| VS Code | Ejecucion, lectura de SQL, terminal y vista de base local |
| Git / GitHub | Versionamiento y entrega del repositorio |

## Como revisar rapido

1. Abre el proyecto en VS Code.
2. Revisa `bloque0_auditoria.md`, `bloque2_decisiones.md` y `bloque4_kpi_framework.md`.
3. Abre `bloque3_analisis.html` y `bloque5_dashboard.html` en el navegador.
4. Abre `bloque2_modelo.pdf` y `bloque5_presentacion_EN.pdf`.
5. Ejecuta `py scripts\run_sqlite_block1.py --preview 5` para crear las tablas del Bloque 1.
6. Abre `data/retail_prueba_tecnica.sqlite` con SQLite Viewer y refresca las tablas.
7. Usa `apoyo_exposicion_tecnica.html` y `GUIA_SQLITE_VSC.md` para preparar la explicacion.

## SQLite en VS Code

SQLite trabaja con un archivo local. No usa `Server name`, usuario, password, certificado ni instancia de SQL Server.

### Crear o refrescar la base

```powershell
py scripts\create_sqlite_db.py
```

### Ejecutar todo el Bloque 1 y crear tablas visibles

```powershell
py scripts\run_sqlite_block1.py --preview 5
```

Este comando crea tablas dentro de `data/retail_prueba_tecnica.sqlite`:

- `bloque1_q1_ventas_comparables`
- `bloque1_q2_productividad_tienda`
- `bloque1_q3_cohortes_lealtad`
- `bloque1_q4_retorno_margen_proveedor_categoria`
- `bloque1_q5_posibles_quiebres_stock`
- `bloque1_q6_promociones_ticket_volumen`

### Ejecutar una consulta cualquiera

```powershell
py scripts\query_sqlite.py "SELECT * FROM bloque1_q1_ventas_comparables LIMIT 20;"
```

### Guardar una consulta como tabla para SQLite Viewer

```powershell
py scripts\query_sqlite.py "SELECT country, format, SUM(ventas_netas_periodo_actual) AS ventas_netas FROM bloque1_q1_ventas_comparables GROUP BY country, format;" --save resumen_ventas_pais_formato
```

Despues refresca SQLite Viewer y abre `resumen_ventas_pais_formato`.

### Si VS Code muestra errores de MSSQL

Si aparecen mensajes como `Incorrect syntax near 'LIMIT'` con `owner: mssql`, no es un error de SQLite. Significa que la extension de SQL Server esta leyendo el archivo como T-SQL. Para esta solucion, los archivos de `sqlite/` se ejecutan con `py scripts\query_sqlite.py` o con una extension SQLite. El repo incluye `.vscode/settings.json` para reducir esos diagnosticos falsos.

## Entregables

| Archivo | Proposito |
| --- | --- |
| `bloque0_auditoria.md` | Calidad de datos, hallazgos y decisiones de tratamiento |
| `bloque1_queries.sql` | Version SQL avanzada para motor analitico |
| `sqlite/03_bloque1_queries_sqlite.sql` | Version ejecutable en SQLite que crea tablas de resultado |
| `bloque2_modelo.pdf` | Modelo dimensional tipo estrella |
| `bloque2_decisiones.md` | Decisiones de modelado, pipeline y gobernanza |
| `bloque3_analisis.html` | Analisis exploratorio, visualizaciones y prueba A/B |
| `bloque3_visualizaciones/` | Graficos SVG usados en el analisis |
| `bloque4_kpi_framework.md` | Framework de indicadores y metrica principal |
| `bloque5_dashboard.html` | Dashboard operativo regional interactivo con selector de todas las tiendas o una tienda específica |
| `bloque5_presentacion_EN.pdf` | Presentacion ejecutiva en ingles |
| `apoyo_exposicion_tecnica.html` | Apoyo para explicar la solucion durante la entrevista |
| `GUIA_SQLITE_VSC.md` | Guia practica para SQLite en VS Code |

## Mapa contra requerimientos

| Bloque | Requerimiento | Donde esta resuelto |
| --- | --- | --- |
| 0 | Auditoria de calidad de datos | `bloque0_auditoria.md` |
| 1 | Seis queries SQL avanzadas | `bloque1_queries.sql` y `sqlite/03_bloque1_queries_sqlite.sql` |
| 2 | Modelo dimensional y decisiones | `bloque2_modelo.pdf`, `bloque2_modelo.mmd`, `bloque2_decisiones.md` |
| 3 | Analisis exploratorio y prueba A/B | `bloque3_analisis.html`, `bloque3_visualizaciones/` |
| 4 | Indicadores y metrica principal | `bloque4_kpi_framework.md` |
| 5 | Dashboard y presentacion ejecutiva | `bloque5_dashboard.html`, `bloque5_presentacion_EN.pdf` |

## Consultas del Bloque 1

Cada query del archivo SQLite incluye una explicacion breve antes de la consulta:

| Query | Tabla creada | Logica |
| --- | --- | --- |
| 1 | `bloque1_q1_ventas_comparables` | Crecimiento comparable por tienda y formato |
| 2 | `bloque1_q2_productividad_tienda` | Ventas netas por metro cuadrado y alerta bajo percentil 25 |
| 3 | `bloque1_q3_cohortes_lealtad` | Retencion y ticket por cohorte de clientes |
| 4 | `bloque1_q4_retorno_margen_proveedor_categoria` | Margen bruto y retorno por proveedor-categoria |
| 5 | `bloque1_q5_posibles_quiebres_stock` | Dias sin venta y venta estimada perdida |
| 6 | `bloque1_q6_promociones_ticket_volumen` | Comparacion de ticket y volumen con/sin promocion |

## Como regenerar todo

Los CSV originales estan en `data/raw/`. Si se reemplazan, deben conservar los mismos nombres.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python scripts/generate_all.py
```

En Windows:

```powershell
py -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
py scripts\generate_all.py
```

## Validacion realizada

- Conteos de filas contra los CSV originales.
- Revision de llaves, fechas, duplicados, proveedores faltantes y asignaciones A/B.
- Ejecucion de consultas SQLite del dashboard y del Bloque 1.
- Revision del dashboard HTML y de la presentacion PDF.
- Documentacion de supuestos: ventas netas restan devoluciones, tiendas con doble asignacion A/B se excluyen de la prueba primaria y gaps de stock son senales operativas.

<details>
<summary>Notas de criterio analitico</summary>

- Para indicadores transaccionales se usa `total_amount` con signo negativo en devoluciones.
- Para categoria, proveedor y producto se usa nivel item porque permite atribucion mas fina.
- SQLite se eligio porque permite defender la parte de base de datos sin instalar SQL Server.
- Las tablas `bloque1_q...` materializan resultados para que puedan abrirse visualmente en SQLite Viewer.

</details>

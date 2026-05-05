# Prueba tecnica Data Analyst - Retail Centroamerica

Repositorio con la solucion completa de la prueba tecnica: auditoria de calidad, SQL avanzado, modelo dimensional, analisis exploratorio, prueba A/B, framework de indicadores, dashboard operativo y presentacion ejecutiva en ingles.

## Como revisar rapido

1. Abre este proyecto en VS Code.
2. Lee `bloque0_auditoria.md`, `bloque2_decisiones.md` y `bloque4_kpi_framework.md`.
3. Abre `bloque3_analisis.html` y `bloque5_dashboard.html` en el navegador o con Live Preview de VS Code.
4. Abre `bloque2_modelo.pdf` y `bloque5_presentacion_EN.pdf`.
5. Crea la base SQLite con `python scripts/create_sqlite_db.py`.
6. Ejecuta `python scripts/run_sqlite_block1.py` para guardar los resultados del Bloque 1 como tablas.
7. Para preparar la exposicion, abre `apoyo_exposicion_tecnica.html` y `GUIA_SQLITE_VSC.md`.

## Como regenerar todo

Los CSV ya estan incluidos en `data/raw/`. Si necesitas reemplazarlos, copia los seis archivos del ZIP en esa carpeta con los mismos nombres.

```bash
python -m venv .venv
source .venv/bin/activate  # En Windows: .venv\Scripts\activate
pip install -r requirements.txt
python scripts/generate_all.py
```

En una computadora donde no puedas instalar programas, puedes revisar todos los entregables ya generados sin ejecutar nada. Para mostrar la parte de base de datos sin servidor local, usa SQLite: ejecuta `python scripts/create_sqlite_db.py`, abre `GUIA_SQLITE_VSC.md` y revisa las consultas de la carpeta `sqlite/`.

## Datos

- Periodo: 2024-01-01 a 2025-06-30
- Transacciones: 174,880
- Items: 542,015
- Tiendas: 40
- Productos: 200

## Entregables

- `bloque0_auditoria.md`: auditoria de calidad con evidencia y decisiones.
- `bloque1_queries.sql`: seis queries avanzadas comentadas.
- `bloque2_modelo.pdf`: diagrama del star schema.
- `bloque2_decisiones.md`: decisiones de modelado, ETL/ELT y gobernanza.
- `bloque3_analisis.html`: EDA, prueba A/B e interpretacion.
- `bloque3_visualizaciones/`: visualizaciones exportadas en SVG.
- `bloque4_kpi_framework.md`: tabla de indicadores y metrica principal.
- `bloque5_dashboard.html`: dashboard operativo interactivo local.
- `bloque5_presentacion_EN.pdf`: presentacion ejecutiva en ingles.
- `apoyo_exposicion_tecnica.html`: apoyo de exposicion con historia ejecutiva, ruta tecnica y criterios de defensa.
- `GUIA_SQLITE_VSC.md`: pasos para crear, consultar y abrir la base SQLite local desde VS Code.
- `sqlite/`: scripts SQLite para validar carga, ejecutar Bloque 1 y responder pruebas en vivo.
- `scripts/run_sqlite_block1.py`: ejecuta las seis consultas del Bloque 1 y guarda resultados como tablas SQLite.
- `scripts/query_sqlite.py`: ejecuta cualquier consulta SQLite desde terminal y opcionalmente guarda resultados como tablas.

## Mapa contra requerimientos

| Bloque | Requerimiento principal | Donde revisarlo |
| --- | --- | --- |
| 0 | Auditoria de completitud, consistencia, unicidad, validez, llaves, frescura, tiempo y prueba A/B | `bloque0_auditoria.md` |
| 1 | Seis consultas avanzadas comentadas | `bloque1_queries.sql` y version ejecutable local en `sqlite/03_bloque1_queries_sqlite.sql` |
| 2 | Modelo estrella, decisiones de diseno, pipeline y gobernanza | `bloque2_modelo.pdf` y `bloque2_decisiones.md` |
| 3 | Analisis exploratorio, visualizaciones y evaluacion estadistica | `bloque3_analisis.html` y `bloque3_visualizaciones/` |
| 4 | Framework de 6 a 10 indicadores, indicador anticipado, indicador compuesto y metrica principal | `bloque4_kpi_framework.md` |
| 5 | Dashboard operativo y presentacion ejecutiva en ingles | `bloque5_dashboard.html` y `bloque5_presentacion_EN.pdf` |

El dashboard se entrega como HTML interactivo para que pueda abrirse desde VS Code sin instalar Power BI, Tableau ni un servidor local. La base ejecutable para preguntas en vivo es SQLite.

## Metodologia y validacion

Trabajo realizado:

- Lectura de instrucciones y definicion de entregables.
- Estructura reproducible del proyecto.
- Scripts de analisis, visualizaciones HTML/SVG y PDFs.
- Narrativa ejecutiva y recomendaciones de negocio.

Validacion manual realizada:

- Conteos de filas contra los CSV originales.
- Reglas de calidad del Bloque 0.
- Rango de fechas, asignaciones A/B ambiguas y consistencia de llaves.
- Formulas principales de ventas netas, retorno de margen bruto sobre inversion, cohortes, prueba t y productividad.
- Apertura de los archivos HTML/PDF generados.

Modificaciones humanas/criterio aplicado:

- Se eligieron ventas netas restando devoluciones.
- Se excluyeron tiendas con doble asignacion de la prueba A/B.
- Se priorizo SQLite porque permite ejecutar base de datos local sin permisos de administrador.
- Se documento que las ausencias de venta son senales operativas, no inventario real.

## Documentacion de uso de IA

Se uso asistencia conversacional como apoyo para acelerar estructura, redaccion inicial, consultas SQL y revisiones de consistencia. Los prompts principales fueron:

- Analizar la prueba tecnica, proponer estructura de repositorio y cubrir los entregables.
- Convertir la parte de base de datos a SQLite para poder ejecutarla en una computadora sin permisos de administrador.
- Revisar el dashboard, los nombres visibles y las explicaciones tecnicas para que quedaran claros en espanol.

Validacion y criterio aplicado manualmente:

- Contraste de conteos contra los CSV originales.
- Revision de reglas de calidad y decisiones de exclusion.
- Ajuste de formulas de ventas netas, retorno de margen bruto sobre inversion, cohortes, productividad y prueba estadistica.
- Pruebas locales de la base SQLite y de las consultas del Bloque 1.

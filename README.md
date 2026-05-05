# Prueba tecnica Data Analyst - Retail Centroamerica

Repositorio con la solucion completa de la prueba tecnica: auditoria de calidad, SQL avanzado, modelo dimensional, analisis exploratorio, A/B test, framework de KPIs, dashboard operativo y presentacion ejecutiva en ingles.

## Como revisar rapido

1. Abre este proyecto en VS Code.
2. Lee `bloque0_auditoria.md`, `bloque2_decisiones.md` y `bloque4_kpi_framework.md`.
3. Abre `bloque3_analisis.html` y `bloque5_dashboard.html` en el navegador o con Live Preview de VS Code.
4. Abre `bloque2_modelo.pdf` y `bloque5_presentacion_EN.pdf`.
5. Revisa `bloque1_queries.sql` para las queries comentadas en BigQuery Standard SQL.
6. Para la entrevista, abre `milla_extra_demo_entrevista.html` y `GUIA_DEMO_EN_VIVO_SQL_SERVER.md`.

## Como regenerar todo

Los CSV ya estan incluidos en `data/raw/`. Si necesitas reemplazarlos, copia los seis archivos del ZIP en esa carpeta con los mismos nombres.

```bash
python -m venv .venv
source .venv/bin/activate  # En Windows: .venv\Scripts\activate
pip install -r requirements.txt
python scripts/generate_all.py
```

En una computadora donde no puedas instalar programas, puedes revisar todos los entregables ya generados sin ejecutar nada. Para mostrar la parte de base de datos desde VS Code, abre `sql/README_SQL_SERVER.md` y ejecuta los scripts numerados de la carpeta `sql/` con la extension MSSQL.

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
- `bloque3_analisis.html`: EDA, A/B test e interpretacion.
- `bloque3_visualizaciones/`: visualizaciones exportadas en SVG.
- `bloque4_kpi_framework.md`: tabla de KPIs y North Star Metric.
- `bloque5_dashboard.html`: dashboard operativo estatico e interactivo.
- `bloque5_presentacion_EN.pdf`: presentacion ejecutiva en ingles.
- `milla_extra_demo_entrevista.html`: modo entrevista con guion, historia ejecutiva y preguntas dificiles.
- `GUIA_DEMO_EN_VIVO_SQL_SERVER.md`: pasos para conectar SQL Server en VS Code y ejecutar queries en vivo.
- `sql/00_crear_tablas_sql_server.sql`: crea la base y tablas en SQL Server.
- `sql/01_cargar_csv_sql_server.sql`: carga los CSV a SQL Server.
- `sql/02_validar_carga_sql_server.sql`: valida conteos y reglas basicas.
- `sql/03_bloque1_queries_sql_server.sql`: version T-SQL ejecutable del Bloque 1.
- `sql/04_consultas_dashboard_sql_server.sql`: consultas que explican cada componente del dashboard.
- `sql/05_demo_en_vivo_milla_extra.sql`: consultas cortas para demostrar dominio tecnico en vivo.

## Uso de IA documentado

Use Codex/ChatGPT como asistente para:

- Extraer y resumir las instrucciones del PDF.
- Generar el esqueleto reproducible del proyecto.
- Escribir scripts de analisis, visualizaciones HTML/SVG y PDFs.
- Redactar la narrativa ejecutiva inicial.

Validacion manual realizada:

- Conteos de filas contra los CSV originales.
- Reglas de calidad del Bloque 0.
- Rango de fechas, asignaciones A/B ambiguas y consistencia de llaves.
- Formulas principales de GMV neto, GMROI, cohortes, t-test y productividad.
- Apertura de los archivos HTML/PDF generados.

Modificaciones humanas/criterio aplicado:

- Se eligio GMV neto restando devoluciones.
- Se excluyeron tiendas con doble asignacion del A/B test.
- Se trato el dashboard como HTML autocontenido porque la maquina de trabajo no puede instalar Power BI/MSSQL local.
- Se documento que los gaps de stock son senales operativas, no inventario real.

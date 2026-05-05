#!/usr/bin/env python3
"""Run the six Block 1 SQLite queries and store their outputs as tables."""

from __future__ import annotations

import argparse
import sqlite3
import time
from pathlib import Path

from query_sqlite import print_table


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB_PATH = ROOT / "data" / "retail_prueba_tecnica.sqlite"
DEFAULT_SQL_PATH = ROOT / "sqlite" / "03_bloque1_queries_sqlite.sql"

RESULT_TABLES = [
    ("bloque1_q1_ventas_comparables", "Query 1 - Ventas comparables"),
    ("bloque1_q2_productividad_tienda", "Query 2 - Productividad por tienda"),
    ("bloque1_q3_cohortes_lealtad", "Query 3 - Cohortes de lealtad"),
    ("bloque1_q4_retorno_margen_proveedor_categoria", "Query 4 - Retorno de margen por proveedor-categoria"),
    ("bloque1_q5_posibles_quiebres_stock", "Query 5 - Posibles quiebres de stock"),
    ("bloque1_q6_promociones_ticket_volumen", "Query 6 - Promociones, ticket y volumen"),
]


def ensure_db_exists(db_path: Path) -> None:
    if not db_path.exists():
        raise SystemExit(f"No existe la base: {db_path}\nPrimero ejecuta: python scripts/create_sqlite_db.py")


def table_count(conn: sqlite3.Connection, table_name: str) -> int:
    return int(conn.execute(f"SELECT COUNT(*) FROM {table_name}").fetchone()[0])


def table_preview(conn: sqlite3.Connection, table_name: str, limit: int) -> tuple[list[str], list[tuple[object, ...]]]:
    cursor = conn.execute(f"SELECT * FROM {table_name} LIMIT ?", (limit,))
    rows = cursor.fetchall()
    headers = [description[0] for description in cursor.description or []]
    return headers, rows


def main() -> None:
    parser = argparse.ArgumentParser(description="Ejecutar Bloque 1 en SQLite y crear tablas de resultado.")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH, help="Ruta de la base .sqlite.")
    parser.add_argument("--sql", type=Path, default=DEFAULT_SQL_PATH, help="Archivo SQL del Bloque 1 SQLite.")
    parser.add_argument("--preview", type=int, default=5, help="Filas de vista previa por tabla.")
    args = parser.parse_args()

    db_path = args.db.resolve()
    sql_path = args.sql.resolve()
    ensure_db_exists(db_path)

    start = time.time()
    conn = sqlite3.connect(db_path)
    try:
        conn.executescript(sql_path.read_text(encoding="utf-8"))
        conn.commit()

        print(f"Bloque 1 ejecutado sobre: {db_path}")
        print(f"Archivo SQL usado: {sql_path}")
        print(f"Tiempo: {time.time() - start:,.1f} segundos")
        print()
        print("Tablas creadas para revisar en SQLite Viewer:")

        for table_name, label in RESULT_TABLES:
            count = table_count(conn, table_name)
            print(f"- {table_name}: {count:,} filas ({label})")

        if args.preview > 0:
            for table_name, label in RESULT_TABLES:
                print()
                print(f"{label} | {table_name}")
                headers, rows = table_preview(conn, table_name, args.preview)
                print_table(headers, rows)
    finally:
        conn.close()


if __name__ == "__main__":
    main()

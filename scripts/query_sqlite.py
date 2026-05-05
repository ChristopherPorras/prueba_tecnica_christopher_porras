#!/usr/bin/env python3
"""Run a SQLite query and print the result as a terminal table."""

from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB_PATH = ROOT / "data" / "retail_prueba_tecnica.sqlite"


def format_value(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, float):
        return f"{value:,.2f}"
    if isinstance(value, int):
        return f"{value:,}"
    return str(value)


def print_table(headers: list[str], rows: list[tuple[object, ...]]) -> None:
    rendered_rows = [[format_value(value) for value in row] for row in rows]
    widths = [
        max(len(header), *(len(row[index]) for row in rendered_rows)) if rendered_rows else len(header)
        for index, header in enumerate(headers)
    ]

    def line(values: list[str]) -> str:
        return " | ".join(value.ljust(widths[index]) for index, value in enumerate(values))

    print(line(headers))
    print("-+-".join("-" * width for width in widths))
    for row in rendered_rows:
        print(line(row))


def run_query(db_path: Path, query: str) -> None:
    if not db_path.exists():
        raise SystemExit(f"No existe la base: {db_path}\nPrimero ejecuta: python scripts/create_sqlite_db.py")

    conn = sqlite3.connect(db_path)
    try:
        cursor = conn.execute(query)
        rows = cursor.fetchall()
        headers = [description[0] for description in cursor.description or []]
        if headers:
            print_table(headers, rows)
        else:
            conn.commit()
            print("Consulta ejecutada correctamente.")
    finally:
        conn.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Ejecutar una consulta SQLite sobre la base local.")
    parser.add_argument("query", nargs="?", help="Consulta SQL a ejecutar.")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH, help="Ruta de la base .sqlite.")
    parser.add_argument("--stdin", action="store_true", help="Leer la consulta desde stdin.")
    args = parser.parse_args()

    query = sys.stdin.read() if args.stdin else args.query
    if not query or not query.strip():
        raise SystemExit('Indica una consulta. Ejemplo: python scripts/query_sqlite.py "SELECT COUNT(*) FROM transactions;"')

    run_query(args.db.resolve(), query.strip())


if __name__ == "__main__":
    main()

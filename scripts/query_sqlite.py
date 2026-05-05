#!/usr/bin/env python3
"""Run a SQLite query and print the result as a terminal table."""

from __future__ import annotations

import argparse
import re
import sqlite3
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB_PATH = ROOT / "data" / "retail_prueba_tecnica.sqlite"
IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


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


def quote_identifier(identifier: str) -> str:
    if not IDENTIFIER_RE.match(identifier):
        raise SystemExit("El nombre de tabla solo puede usar letras, numeros y underscore, y no puede iniciar con numero.")
    return f'"{identifier}"'


def strip_trailing_semicolon(query: str) -> str:
    query = query.strip()
    while query.endswith(";"):
        query = query[:-1].strip()
    return query


def print_existing_tables(conn: sqlite3.Connection) -> None:
    cursor = conn.execute(
        """
        SELECT type, name
        FROM sqlite_master
        WHERE type IN ('table', 'view')
          AND name NOT LIKE 'sqlite_%'
        ORDER BY type, name;
        """
    )
    rows = cursor.fetchall()
    print_table(["tipo", "nombre"], rows)


def print_schema(conn: sqlite3.Connection, table_name: str) -> None:
    quoted_name = quote_identifier(table_name)
    cursor = conn.execute(f"PRAGMA table_info({quoted_name})")
    rows = cursor.fetchall()
    if not rows:
        raise SystemExit(f"No existe la tabla o vista: {table_name}")
    print_table(["cid", "nombre", "tipo", "not_null", "default", "pk"], rows)


def preview_query(conn: sqlite3.Connection, query: str, limit: int | None) -> None:
    preview_sql = query if limit is None else f"SELECT * FROM ({strip_trailing_semicolon(query)}) LIMIT {limit}"
    cursor = conn.execute(preview_sql)
    rows = cursor.fetchall()
    headers = [description[0] for description in cursor.description or []]
    if headers:
        print_table(headers, rows)
    else:
        conn.commit()
        print("Consulta ejecutada correctamente.")


def run_query(db_path: Path, query: str | None, save_table: str | None, preview_limit: int | None, tables: bool, schema: str | None) -> None:
    if not db_path.exists():
        raise SystemExit(f"No existe la base: {db_path}\nPrimero ejecuta: python scripts/create_sqlite_db.py")

    conn = sqlite3.connect(db_path)
    try:
        if tables:
            print_existing_tables(conn)
            return
        if schema:
            print_schema(conn, schema)
            return
        if not query or not query.strip():
            raise SystemExit('Indica una consulta. Ejemplo: python scripts/query_sqlite.py "SELECT COUNT(*) FROM transactions;"')

        clean_query = strip_trailing_semicolon(query)
        if save_table:
            quoted_table = quote_identifier(save_table)
            conn.execute(f"DROP TABLE IF EXISTS {quoted_table}")
            conn.execute(f"CREATE TABLE {quoted_table} AS {clean_query}")
            conn.commit()
            count = conn.execute(f"SELECT COUNT(*) FROM {quoted_table}").fetchone()[0]
            print(f"Tabla creada: {save_table} ({count:,} filas)")
            preview_query(conn, f"SELECT * FROM {quoted_table}", preview_limit)
            return

        preview_query(conn, clean_query, preview_limit)
    finally:
        conn.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Ejecutar una consulta SQLite sobre la base local.")
    parser.add_argument("query", nargs="?", help="Consulta SQL a ejecutar.")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH, help="Ruta de la base .sqlite.")
    parser.add_argument("--stdin", action="store_true", help="Leer la consulta desde stdin.")
    parser.add_argument("--save", help="Guardar el resultado de la consulta como tabla para verlo en SQLite Viewer.")
    parser.add_argument("--limit", type=int, default=None, help="Limitar filas impresas en terminal.")
    parser.add_argument("--tables", action="store_true", help="Listar tablas y vistas disponibles.")
    parser.add_argument("--schema", help="Mostrar columnas de una tabla o vista.")
    args = parser.parse_args()

    query = sys.stdin.read() if args.stdin else args.query
    run_query(args.db.resolve(), query.strip() if query else None, args.save, args.limit, args.tables, args.schema)


if __name__ == "__main__":
    main()

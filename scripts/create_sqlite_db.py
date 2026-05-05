#!/usr/bin/env python3
"""Create the local SQLite database from the CSV files."""

from __future__ import annotations

import argparse
import csv
import sqlite3
from pathlib import Path
from typing import Callable, Iterable


ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = ROOT / "data" / "raw"
DEFAULT_DB_PATH = ROOT / "data" / "retail_prueba_tecnica.sqlite"


def as_text(value: str) -> str | None:
    value = value.strip()
    return value or None


def as_int(value: str) -> int | None:
    value = value.strip()
    return int(value) if value else None


def as_float(value: str) -> float | None:
    value = value.strip()
    return float(value) if value else None


def as_bool(value: str) -> int:
    return 1 if value.strip().lower() == "true" else 0


def rows_from_csv(
    csv_path: Path,
    columns: list[str],
    converters: dict[str, Callable[[str], object]],
) -> Iterable[tuple[object, ...]]:
    with csv_path.open(newline="", encoding="utf-8-sig") as file:
        reader = csv.DictReader(file)
        for row in reader:
            yield tuple(converters.get(column, as_text)(row[column]) for column in columns)


def load_table(
    conn: sqlite3.Connection,
    table_name: str,
    csv_name: str,
    columns: list[str],
    converters: dict[str, Callable[[str], object]],
) -> int:
    placeholders = ", ".join(["?"] * len(columns))
    column_list = ", ".join(columns)
    sql = f"INSERT INTO {table_name} ({column_list}) VALUES ({placeholders})"
    rows = list(rows_from_csv(RAW_DIR / csv_name, columns, converters))
    conn.executemany(sql, rows)
    return len(rows)


def create_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        DROP VIEW IF EXISTS v_items_ventas;
        DROP VIEW IF EXISTS v_transacciones_ventas_netas;

        DROP TABLE IF EXISTS store_promotions;
        DROP TABLE IF EXISTS transaction_items;
        DROP TABLE IF EXISTS transactions;
        DROP TABLE IF EXISTS products;
        DROP TABLE IF EXISTS vendors;
        DROP TABLE IF EXISTS stores;

        CREATE TABLE vendors (
          vendor_id TEXT PRIMARY KEY,
          vendor_name TEXT NOT NULL,
          country TEXT NOT NULL,
          tier TEXT NOT NULL,
          is_shared_catalog INTEGER NOT NULL
        );

        CREATE TABLE stores (
          store_id TEXT PRIMARY KEY,
          store_name TEXT NOT NULL,
          country TEXT NOT NULL,
          city TEXT NOT NULL,
          format TEXT NOT NULL,
          size_sqm INTEGER NOT NULL,
          opening_date TEXT NOT NULL,
          region TEXT NOT NULL
        );

        CREATE TABLE products (
          item_id TEXT PRIMARY KEY,
          item_name TEXT NOT NULL,
          brand TEXT NOT NULL,
          vendor_id TEXT,
          category TEXT NOT NULL,
          department TEXT NOT NULL,
          cost REAL NOT NULL
        );

        CREATE TABLE transactions (
          transaction_id TEXT PRIMARY KEY,
          customer_id TEXT,
          transaction_date TEXT NOT NULL,
          store_id TEXT NOT NULL,
          total_amount REAL NOT NULL,
          payment_method TEXT NOT NULL,
          loyalty_card INTEGER NOT NULL,
          status TEXT NOT NULL
        );

        CREATE TABLE transaction_items (
          transaction_item_id TEXT PRIMARY KEY,
          transaction_id TEXT NOT NULL,
          item_id TEXT NOT NULL,
          quantity INTEGER NOT NULL,
          unit_price REAL NOT NULL,
          was_on_promo INTEGER NOT NULL
        );

        CREATE TABLE store_promotions (
          promotion_id INTEGER PRIMARY KEY AUTOINCREMENT,
          store_id TEXT NOT NULL,
          promo_name TEXT NOT NULL,
          variant TEXT NOT NULL,
          start_date TEXT NOT NULL,
          end_date TEXT NOT NULL,
          promo_type TEXT NOT NULL
        );

        CREATE INDEX idx_transactions_date ON transactions(transaction_date);
        CREATE INDEX idx_transactions_store ON transactions(store_id);
        CREATE INDEX idx_transactions_customer ON transactions(customer_id);
        CREATE INDEX idx_transaction_items_tx ON transaction_items(transaction_id);
        CREATE INDEX idx_transaction_items_item ON transaction_items(item_id);
        CREATE INDEX idx_products_category ON products(category);
        CREATE INDEX idx_promotions_store ON store_promotions(store_id);

        CREATE VIEW v_transacciones_ventas_netas AS
        SELECT
          transaction_id,
          customer_id,
          transaction_date,
          store_id,
          total_amount,
          payment_method,
          loyalty_card,
          status,
          CASE WHEN status = 'RETURNED' THEN -total_amount ELSE total_amount END AS ventas_netas
        FROM transactions;

        CREATE VIEW v_items_ventas AS
        SELECT
          ti.transaction_item_id,
          ti.transaction_id,
          ti.item_id,
          p.item_name,
          p.category,
          p.vendor_id,
          ti.quantity,
          ti.unit_price,
          p.cost,
          ti.was_on_promo,
          ti.quantity * ti.unit_price AS ventas_brutas_item,
          ti.quantity * p.cost AS costo_item
        FROM transaction_items ti
        JOIN products p ON p.item_id = ti.item_id;
        """
    )


def build_database(db_path: Path) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    if db_path.exists():
        db_path.unlink()

    conn = sqlite3.connect(db_path)
    try:
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA synchronous = NORMAL")
        create_schema(conn)

        counts = {
            "vendors": load_table(
                conn,
                "vendors",
                "vendors.csv",
                ["vendor_id", "vendor_name", "country", "tier", "is_shared_catalog"],
                {"is_shared_catalog": as_bool},
            ),
            "stores": load_table(
                conn,
                "stores",
                "stores.csv",
                ["store_id", "store_name", "country", "city", "format", "size_sqm", "opening_date", "region"],
                {"size_sqm": as_int},
            ),
            "products": load_table(
                conn,
                "products",
                "products.csv",
                ["item_id", "item_name", "brand", "vendor_id", "category", "department", "cost"],
                {"cost": as_float},
            ),
            "transactions": load_table(
                conn,
                "transactions",
                "transactions.csv",
                [
                    "transaction_id",
                    "customer_id",
                    "transaction_date",
                    "store_id",
                    "total_amount",
                    "payment_method",
                    "loyalty_card",
                    "status",
                ],
                {"total_amount": as_float, "loyalty_card": as_bool},
            ),
            "transaction_items": load_table(
                conn,
                "transaction_items",
                "transaction_items.csv",
                ["transaction_item_id", "transaction_id", "item_id", "quantity", "unit_price", "was_on_promo"],
                {"quantity": as_int, "unit_price": as_float, "was_on_promo": as_bool},
            ),
            "store_promotions": load_table(
                conn,
                "store_promotions",
                "store_promotions.csv",
                ["store_id", "promo_name", "variant", "start_date", "end_date", "promo_type"],
                {},
            ),
        }
        conn.commit()
    finally:
        conn.close()

    print(f"Base SQLite creada: {db_path}")
    for table, count in counts.items():
        print(f"- {table}: {count:,} filas")


def main() -> None:
    parser = argparse.ArgumentParser(description="Crear base SQLite local desde data/raw.")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH, help="Ruta del archivo .sqlite a crear.")
    args = parser.parse_args()
    build_database(args.db.resolve())


if __name__ == "__main__":
    main()

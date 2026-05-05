from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
import pandas as pd
from reportlab.lib import colors
from reportlab.lib.pagesizes import landscape, letter
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.pdfgen import canvas
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle


ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
VIZ = ROOT / "bloque3_visualizaciones"
PROCESSED = ROOT / "data" / "processed"

PALETTE = {
    "HIPERMERCADO": "#176B87",
    "SUPERMERCADO": "#3E8E7E",
    "DESCUENTO": "#D97941",
    "EXPRESS": "#7B4B94",
    "CONTROL": "#667085",
    "TREATMENT": "#C04B37",
}


def money(value: float) -> str:
    return f"${value:,.0f}"


def money2(value: float) -> str:
    return f"${value:,.2f}"


def pct(value: float) -> str:
    return "NA" if pd.isna(value) else f"{value:.1f}%"


def load_data() -> dict[str, pd.DataFrame]:
    tx = pd.read_csv(RAW / "transactions.csv", parse_dates=["transaction_date"])
    items = pd.read_csv(RAW / "transaction_items.csv")
    stores = pd.read_csv(RAW / "stores.csv", parse_dates=["opening_date"])
    products = pd.read_csv(RAW / "products.csv")
    vendors = pd.read_csv(RAW / "vendors.csv")
    promos = pd.read_csv(RAW / "store_promotions.csv", parse_dates=["start_date", "end_date"])

    tx["customer_id"] = tx["customer_id"].replace("", np.nan)
    tx["sign"] = np.where(tx["status"].eq("RETURNED"), -1, 1)
    tx["net_gmv"] = tx["total_amount"] * tx["sign"]
    items["line_gmv"] = items["quantity"] * items["unit_price"]

    full = (
        items.merge(
            tx[
                [
                    "transaction_id",
                    "customer_id",
                    "transaction_date",
                    "store_id",
                    "total_amount",
                    "net_gmv",
                    "payment_method",
                    "loyalty_card",
                    "status",
                    "sign",
                ]
            ],
            on="transaction_id",
        )
        .merge(products, on="item_id", how="left")
        .merge(stores, on="store_id", how="left")
        .merge(vendors, on="vendor_id", how="left")
    )
    full["net_line_gmv"] = full["line_gmv"] * full["sign"]
    full["net_cost"] = full["cost"] * full["quantity"] * full["sign"]
    return {
        "transactions": tx,
        "items": items,
        "stores": stores,
        "products": products,
        "vendors": vendors,
        "promos": promos,
        "full": full,
    }


def markdown_table(rows: list[list[object]], headers: list[str]) -> str:
    out = ["| " + " | ".join(headers) + " |"]
    out.append("| " + " | ".join(["---"] * len(headers)) + " |")
    for row in rows:
        out.append("| " + " | ".join(str(x) for x in row) + " |")
    return "\n".join(out)


def write_audit(dfs: dict[str, pd.DataFrame]) -> dict[str, object]:
    tx, items, stores, products, vendors, promos = (
        dfs["transactions"],
        dfs["items"],
        dfs["stores"],
        dfs["products"],
        dfs["vendors"],
        dfs["promos"],
    )
    calc = items.groupby("transaction_id", as_index=False)["line_gmv"].sum()
    amount_check = tx.merge(calc, on="transaction_id", how="left")
    amount_check["delta"] = amount_check["total_amount"] - amount_check["line_gmv"]
    amount_mismatches = amount_check[amount_check["delta"].abs() > 0.01]

    all_dates = pd.date_range(tx["transaction_date"].min(), tx["transaction_date"].max(), freq="D")
    store_gap_rows = []
    for store_id, group in tx.groupby("store_id"):
        dates = set(group["transaction_date"].dt.normalize())
        missing = [d for d in all_dates if d not in dates]
        runs = []
        if missing:
            start = prev = missing[0]
            for d in missing[1:]:
                if (d - prev).days == 1:
                    prev = d
                else:
                    runs.append((start, prev, (prev - start).days + 1))
                    start = prev = d
            runs.append((start, prev, (prev - start).days + 1))
        if runs:
            max_run = max(runs, key=lambda x: x[2])
            store_gap_rows.append(
                {
                    "store_id": store_id,
                    "missing_days": len(missing),
                    "gap_runs": len(runs),
                    "max_gap_start": max_run[0],
                    "max_gap_end": max_run[1],
                    "max_gap_days": max_run[2],
                }
            )
    store_gaps = pd.DataFrame(store_gap_rows)

    temporal = tx.merge(stores[["store_id", "store_name", "opening_date"]], on="store_id")
    before_opening = temporal[temporal["transaction_date"] < temporal["opening_date"]]
    ab_variants = (
        promos.groupby("store_id")
        .agg(n_variants=("variant", "nunique"), variants=("variant", lambda s: ", ".join(sorted(s.unique()))))
        .query("n_variants > 1")
        .reset_index()
    )

    missing_vendor_products = products[~products["vendor_id"].isin(vendors["vendor_id"])]
    null_customer = int(tx["customer_id"].isna().sum())
    null_customer_pct = null_customer / len(tx) * 100
    bad_loyalty_true = int((tx["customer_id"].isna() & tx["loyalty_card"]).sum())
    bad_loyalty_false = int((tx["customer_id"].notna() & ~tx["loyalty_card"]).sum())

    findings = [
        [
            "Completitud",
            "Transacciones sin customer_id",
            f"{null_customer:,} de {len(tx):,} ({null_customer_pct:.1f}%)",
            "Es consistente: no hay customer_id nulo con loyalty_card = TRUE ni customer_id informado con loyalty_card = FALSE.",
            "Mantener customer_id nulo como comprador anonimo. En cohortes usar solo loyalty_card = TRUE.",
        ],
        [
            "Consistencia",
            "total_amount vs suma de items",
            f"{len(amount_mismatches):,} transacciones ({len(amount_mismatches)/len(tx)*100:.1f}%) con diferencia > $0.01; delta maximo {money2(amount_mismatches['delta'].abs().max())}.",
            "La mayoria de diferencias son negativas: el total reportado es menor que la suma de items.",
            "Para KPIs de GMV usar total_amount a nivel transaccion; para categoria/proveedor usar line_gmv y documentar la diferencia.",
        ],
        [
            "Unicidad",
            "transaction_id duplicados",
            f"{tx['transaction_id'].duplicated().sum():,}",
            "No se detectaron duplicados.",
            "No se requiere deduplicacion para esta version.",
        ],
        [
            "Validez",
            "Montos cero/negativos y precios cero",
            f"{(tx['total_amount'] <= 0).sum():,} transacciones con total_amount <= 0; {((items['unit_price'] == 0) & (~items['was_on_promo'])).sum():,} items con unit_price = 0 sin promo.",
            "Hay ventas completadas con monto cero y precios cero que no estan explicados por promocion.",
            "Excluir transacciones con total_amount <= 0 de tickets promedio; marcar items con precio cero como alerta de pricing/master data.",
        ],
        [
            "Integridad referencial",
            "FKs contra dimensiones",
            f"{(~tx['store_id'].isin(stores['store_id'])).sum():,} store_id invalidos; {(~items['item_id'].isin(products['item_id'])).sum():,} item_id invalidos; {len(missing_vendor_products):,} productos con vendor_id inexistente.",
            "Cinco productos apuntan a VND_031, que no existe en vendors.",
            "Mantener esos productos con vendor 'SIN_VENDOR' en analisis de categoria y levantar incidente de master data.",
        ],
        [
            "Frescura",
            "Gaps diarios por tienda",
            f"{len(store_gaps):,} tiendas con gaps. Maximos: "
            + ", ".join(
                f"{r.store_id} {r.max_gap_days} dias"
                for r in store_gaps.sort_values("max_gap_days", ascending=False).head(3).itertuples()
            ),
            "TIENDA_037 tiene 135 dias sin venta antes de iniciar actividad; TIENDA_012 tiene 7 dias sin datos en septiembre 2024.",
            "Tratar TIENDA_037 como gap esperado por apertura; revisar TIENDA_012 como alerta operativa.",
        ],
        [
            "Integridad temporal",
            "Ventas antes de opening_date",
            f"{len(before_opening):,} transacciones, todas en TIENDA_037 entre {before_opening['transaction_date'].min().date()} y {before_opening['transaction_date'].max().date()}.",
            "La tienda tiene opening_date 2024-06-01 pero ventas desde 2024-05-15.",
            "No excluir del analisis historico, pero corregir opening_date o confirmar soft-opening.",
        ],
        [
            "A/B Test",
            "Tiendas en CONTROL y TREATMENT",
            f"{len(ab_variants):,} tiendas: " + ", ".join(ab_variants["store_id"].tolist()),
            "TIENDA_008 y TIENDA_037 aparecen asignadas a ambos grupos.",
            "Excluir estas tiendas del A/B test primario y reportarlas como falla de diseno experimental.",
        ],
    ]

    text = [
        "# Bloque 0 - Auditoria de calidad de datos",
        "",
        f"Periodo observado: {tx['transaction_date'].min().date()} a {tx['transaction_date'].max().date()}. "
        f"Dataset: {len(tx):,} transacciones, {len(items):,} items, {len(stores):,} tiendas, {len(products):,} productos.",
        "",
        markdown_table(findings, ["Dimension", "Pregunta", "Evidencia", "Lectura", "Decision"]),
        "",
        "## Notas de uso en bloques siguientes",
        "",
        "- GMV neto: `COMPLETED` suma positivo y `RETURNED` resta. Para el A/B test se usan solo transacciones completadas.",
        "- Los analisis por proveedor mantienen productos con vendor faltante como `SIN_VENDOR` cuando aplica.",
        "- Las tiendas con doble asignacion experimental se excluyen del resultado estadistico principal.",
        "- Los gaps de stock son senales operativas, no prueba definitiva de quiebre: se priorizan por GMV estimado perdido y velocidad previa.",
    ]
    (ROOT / "bloque0_auditoria.md").write_text("\n".join(text), encoding="utf-8")
    return {
        "amount_mismatches": amount_mismatches,
        "store_gaps": store_gaps,
        "before_opening": before_opening,
        "ab_ambiguous": ab_variants,
    }


def comparable_sales(dfs: dict[str, pd.DataFrame]) -> tuple[pd.DataFrame, pd.DataFrame]:
    tx, stores = dfs["transactions"], dfs["stores"]
    max_date = tx["transaction_date"].max()
    current_start = pd.Timestamp(year=max_date.year, month=1, day=1)
    current_end = max_date
    previous_start = current_start - pd.DateOffset(years=1)
    previous_end = current_end - pd.DateOffset(years=1)
    eligible = stores[stores["opening_date"] <= previous_start]["store_id"]
    comp = tx[tx["store_id"].isin(eligible)].merge(stores, on="store_id")
    comp["period"] = np.select(
        [
            comp["transaction_date"].between(current_start, current_end),
            comp["transaction_date"].between(previous_start, previous_end),
        ],
        ["current", "previous"],
        default="other",
    )
    comp = comp[comp["period"] != "other"]
    store_level = (
        comp.groupby(["country", "format", "store_id", "store_name", "period"])["net_gmv"]
        .sum()
        .unstack(fill_value=0)
        .reset_index()
    )
    store_level = store_level[(store_level["current"] != 0) & (store_level["previous"] != 0)].copy()
    store_level["growth_pct"] = (store_level["current"] / store_level["previous"] - 1) * 100
    store_level["rank_in_format"] = store_level.groupby("format")["growth_pct"].rank(ascending=False, method="dense")
    country_format = (
        store_level.groupby(["country", "format"])
        .agg(gmv_current=("current", "sum"), gmv_previous=("previous", "sum"), stores=("store_id", "nunique"))
        .reset_index()
    )
    country_format["growth_pct"] = (country_format["gmv_current"] / country_format["gmv_previous"] - 1) * 100
    return store_level.sort_values("growth_pct", ascending=False), country_format.sort_values("growth_pct", ascending=False)


def productivity(dfs: dict[str, pd.DataFrame]) -> pd.DataFrame:
    tx, stores = dfs["transactions"], dfs["stores"]
    max_date = tx["transaction_date"].max()
    quarter_start = pd.Timestamp(year=max_date.year, month=((max_date.month - 1) // 3) * 3 + 1, day=1)
    data = tx[tx["transaction_date"].between(quarter_start, max_date)].merge(stores, on="store_id")
    out = (
        data.groupby(["store_id", "store_name", "country", "format", "region", "size_sqm"])
        .agg(gmv=("net_gmv", "sum"), transactions=("transaction_id", "nunique"))
        .reset_index()
    )
    out["gmv_per_sqm"] = out["gmv"] / out["size_sqm"]
    out["transactions_per_sqm"] = out["transactions"] / out["size_sqm"]
    out["avg_ticket"] = out["gmv"] / out["transactions"]
    out["p25_format"] = out.groupby("format")["gmv_per_sqm"].transform(lambda s: s.quantile(0.25))
    out["performance_flag"] = np.where(out["gmv_per_sqm"] < out["p25_format"], "BAJO_RENDIMIENTO", "OK")
    out["rank_in_format"] = out.groupby("format")["gmv_per_sqm"].rank(ascending=False, method="dense")
    return out.sort_values(["format", "rank_in_format"])


def cohorts(dfs: dict[str, pd.DataFrame]) -> tuple[pd.DataFrame, pd.DataFrame]:
    tx = dfs["transactions"]
    loyalty = tx[(tx["loyalty_card"]) & (tx["status"] == "COMPLETED")].copy()
    loyalty["tx_month"] = loyalty["transaction_date"].values.astype("datetime64[M]")
    first = loyalty.groupby("customer_id")["tx_month"].min().rename("cohort_month")
    loyalty = loyalty.join(first, on="customer_id")
    loyalty["month_n"] = (
        (loyalty["tx_month"].dt.year - loyalty["cohort_month"].dt.year) * 12
        + (loyalty["tx_month"].dt.month - loyalty["cohort_month"].dt.month)
    )
    sizes = first.reset_index().groupby("cohort_month")["customer_id"].nunique().rename("cohort_size")
    summary = (
        loyalty.groupby(["cohort_month", "month_n"])
        .agg(customers=("customer_id", "nunique"), avg_ticket=("total_amount", "mean"))
        .reset_index()
        .join(sizes, on="cohort_month")
    )
    summary["retention_pct"] = summary["customers"] / summary["cohort_size"] * 100
    pivot = summary[summary["month_n"].isin([0, 1, 2, 3, 6])].pivot(index="cohort_month", columns="month_n", values="retention_pct")
    ticket = summary[summary["month_n"].isin([0, 1, 2, 3, 6])].pivot(index="cohort_month", columns="month_n", values="avg_ticket")
    return pivot, ticket


def gmroi(dfs: dict[str, pd.DataFrame]) -> pd.DataFrame:
    full = dfs["full"].copy()
    full = full[full["status"] == "COMPLETED"]
    full["vendor_name"] = full["vendor_name"].fillna("SIN_VENDOR")
    out = (
        full.groupby(["vendor_id", "vendor_name", "category"], dropna=False)
        .agg(
            gmv=("line_gmv", "sum"),
            cost_total=("net_cost", "sum"),
            units=("quantity", "sum"),
            active_skus=("item_id", "nunique"),
            first_date=("transaction_date", "min"),
            last_date=("transaction_date", "max"),
        )
        .reset_index()
    )
    out["gross_margin"] = out["gmv"] - out["cost_total"]
    out["gmroi"] = out["gross_margin"] / out["cost_total"].replace(0, np.nan)
    out["days"] = (out["last_date"] - out["first_date"]).dt.days + 1
    out["sales_velocity_units_day"] = out["units"] / out["days"].clip(lower=1)
    out["gmroi_flag"] = np.where(out["gmroi"] < 1, "GMROI_BAJO_1", "OK")
    return out.sort_values("gmroi")


def promo_basket(dfs: dict[str, pd.DataFrame]) -> pd.DataFrame:
    full = dfs["full"]
    completed = full[full["status"] == "COMPLETED"].copy()
    by_tx_cat = (
        completed.groupby(["transaction_id", "category"])
        .agg(
            category_gmv=("line_gmv", "sum"),
            units=("quantity", "sum"),
            promo_tx=("was_on_promo", "any"),
            total_ticket=("total_amount", "first"),
        )
        .reset_index()
    )
    out = (
        by_tx_cat.groupby(["category", "promo_tx"])
        .agg(
            transactions=("transaction_id", "nunique"),
            avg_category_gmv=("category_gmv", "mean"),
            avg_units=("units", "mean"),
            avg_ticket=("total_ticket", "mean"),
        )
        .reset_index()
    )
    return out


def weekly_seasonality(dfs: dict[str, pd.DataFrame]) -> tuple[pd.DataFrame, pd.DataFrame]:
    tx, stores = dfs["transactions"], dfs["stores"]
    max_date = tx["transaction_date"].max()
    last_week_start = max_date - pd.Timedelta(days=max_date.weekday())
    complete_until = max_date if max_date.weekday() == 6 else last_week_start - pd.Timedelta(days=1)
    data = tx[tx["transaction_date"] <= complete_until].merge(stores, on="store_id")
    data["week_start"] = data["transaction_date"].dt.to_period("W-SUN").dt.start_time
    weekly = data.groupby(["week_start", "format"])["net_gmv"].sum().reset_index()
    weekly = weekly.sort_values(["format", "week_start"])
    weekly["wow_abs"] = weekly.groupby("format")["net_gmv"].diff()
    weekly["wow_pct"] = weekly.groupby("format")["net_gmv"].pct_change() * 100
    cv = weekly.groupby("format")["net_gmv"].agg(["mean", "std"]).reset_index()
    cv["cv"] = cv["std"] / cv["mean"]
    return weekly, cv.sort_values("cv", ascending=False)


def pareto_categories(dfs: dict[str, pd.DataFrame]) -> pd.DataFrame:
    full = dfs["full"]
    out = full.groupby(["format", "category"])["net_line_gmv"].sum().reset_index()
    out["share"] = out.groupby("format")["net_line_gmv"].transform(lambda s: s / s.sum())
    out = out.sort_values(["format", "net_line_gmv"], ascending=[True, False])
    out["cum_share"] = out.groupby("format")["share"].cumsum()
    return out


def stock_gaps(dfs: dict[str, pd.DataFrame]) -> pd.DataFrame:
    tx, items, products, vendors, stores = (
        dfs["transactions"],
        dfs["items"],
        dfs["products"],
        dfs["vendors"],
        dfs["stores"],
    )
    completed = tx[tx["status"] == "COMPLETED"][["transaction_id", "transaction_date", "store_id"]]
    sales = (
        items.merge(completed, on="transaction_id")
        .merge(products[["item_id", "item_name", "category", "vendor_id"]], on="item_id", how="left")
        .merge(vendors[["vendor_id", "vendor_name"]], on="vendor_id", how="left")
    )
    sales["gmv"] = sales["quantity"] * sales["unit_price"]
    daily = (
        sales.groupby(["store_id", "item_id", "transaction_date", "item_name", "category", "vendor_id", "vendor_name"], dropna=False)
        .agg(gmv=("gmv", "sum"), qty=("quantity", "sum"))
        .reset_index()
        .sort_values(["store_id", "item_id", "transaction_date"])
    )
    max_date = completed["transaction_date"].max().normalize()
    rows = []
    for (store_id, item_id), group in daily.groupby(["store_id", "item_id"], sort=False):
        dates = group["transaction_date"].tolist()
        meta = group.iloc[0]
        for previous_date, next_date in zip(dates, dates[1:]):
            gap_days = (next_date - previous_date).days - 1
            if gap_days >= 3:
                gap_start = previous_date + pd.Timedelta(days=1)
                gap_end = next_date - pd.Timedelta(days=1)
                before = group[(group["transaction_date"] >= gap_start - pd.Timedelta(days=14)) & (group["transaction_date"] < gap_start)]
                avg_daily = before["gmv"].sum() / 14 if not before.empty else 0
                rows.append(
                    [
                        store_id,
                        item_id,
                        meta["item_name"],
                        meta["category"],
                        meta["vendor_id"],
                        meta["vendor_name"] if pd.notna(meta["vendor_name"]) else "SIN_VENDOR",
                        gap_start,
                        gap_end,
                        gap_days,
                        avg_daily,
                        avg_daily * gap_days,
                        False,
                    ]
                )
        active_gap = (max_date - dates[-1]).days
        if active_gap >= 3:
            gap_start = dates[-1] + pd.Timedelta(days=1)
            gap_end = max_date
            before = group[(group["transaction_date"] >= gap_start - pd.Timedelta(days=14)) & (group["transaction_date"] < gap_start)]
            avg_daily = before["gmv"].sum() / 14 if not before.empty else 0
            rows.append(
                [
                    store_id,
                    item_id,
                    meta["item_name"],
                    meta["category"],
                    meta["vendor_id"],
                    meta["vendor_name"] if pd.notna(meta["vendor_name"]) else "SIN_VENDOR",
                    gap_start,
                    gap_end,
                    active_gap,
                    avg_daily,
                    avg_daily * active_gap,
                    True,
                ]
            )
    out = pd.DataFrame(
        rows,
        columns=[
            "store_id",
            "item_id",
            "item_name",
            "category",
            "vendor_id",
            "vendor_name",
            "gap_start",
            "gap_end",
            "gap_days",
            "avg_daily_gmv_before",
            "estimated_lost_gmv",
            "active_gap",
        ],
    )
    out = out.merge(stores[["store_id", "store_name", "country", "format", "region"]], on="store_id", how="left")
    return out.sort_values("estimated_lost_gmv", ascending=False)


def betacf(a: float, b: float, x: float) -> float:
    max_iterations, eps, fpmin = 200, 3e-12, 1e-300
    qab, qap, qam = a + b, a + 1, a - 1
    c = 1.0
    d = 1.0 - qab * x / qap
    d = fpmin if abs(d) < fpmin else d
    d = 1.0 / d
    h = d
    for m in range(1, max_iterations + 1):
        m2 = 2 * m
        aa = m * (b - m) * x / ((qam + m2) * (a + m2))
        d = 1.0 + aa * d
        d = fpmin if abs(d) < fpmin else d
        c = 1.0 + aa / c
        c = fpmin if abs(c) < fpmin else c
        d = 1.0 / d
        h *= d * c
        aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))
        d = 1.0 + aa * d
        d = fpmin if abs(d) < fpmin else d
        c = 1.0 + aa / c
        c = fpmin if abs(c) < fpmin else c
        d = 1.0 / d
        delta = d * c
        h *= delta
        if abs(delta - 1.0) < eps:
            break
    return h


def betai(a: float, b: float, x: float) -> float:
    if x <= 0:
        return 0.0
    if x >= 1:
        return 1.0
    bt = math.exp(math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b) + a * math.log(x) + b * math.log1p(-x))
    if x < (a + 1) / (a + b + 2):
        return bt * betacf(a, b, x) / a
    return 1 - bt * betacf(b, a, 1 - x) / b


def t_cdf(t_value: float, df: float) -> float:
    x = df / (df + t_value * t_value)
    ib = betai(df / 2, 0.5, x)
    return 1 - 0.5 * ib if t_value >= 0 else 0.5 * ib


def welch_ttest(control: pd.Series, treatment: pd.Series) -> dict[str, float]:
    a = control.astype(float).to_numpy()
    b = treatment.astype(float).to_numpy()
    n1, n2 = len(a), len(b)
    m1, m2 = a.mean(), b.mean()
    v1, v2 = a.var(ddof=1), b.var(ddof=1)
    se = math.sqrt(v1 / n1 + v2 / n2)
    t_value = (m2 - m1) / se
    df = (v1 / n1 + v2 / n2) ** 2 / ((v1 / n1) ** 2 / (n1 - 1) + (v2 / n2) ** 2 / (n2 - 1))
    p_value = 2 * (1 - t_cdf(abs(t_value), df))
    lo, hi = 0.0, 10.0
    for _ in range(80):
        mid = (lo + hi) / 2
        if t_cdf(mid, df) < 0.975:
            lo = mid
        else:
            hi = mid
    crit = (lo + hi) / 2
    diff = m2 - m1
    return {
        "n_control": n1,
        "n_treatment": n2,
        "control_mean": m1,
        "treatment_mean": m2,
        "diff": diff,
        "lift_pct": diff / m1 * 100,
        "t": t_value,
        "df": df,
        "p_value": p_value,
        "ci_low": diff - crit * se,
        "ci_high": diff + crit * se,
    }


def ab_test(dfs: dict[str, pd.DataFrame]) -> dict[str, object]:
    tx, promos, stores = dfs["transactions"], dfs["promos"], dfs["stores"]
    ambiguous = promos.groupby("store_id")["variant"].nunique()
    ambiguous = ambiguous[ambiguous > 1].index.tolist()
    clean = promos[~promos["store_id"].isin(ambiguous)].drop_duplicates("store_id")
    completed = tx[tx["status"] == "COMPLETED"]
    start = pd.Timestamp("2024-09-01")
    end = pd.Timestamp("2024-10-12")
    pre_start = start - pd.Timedelta(days=42)
    pre_end = start - pd.Timedelta(days=1)

    def period(start_date: pd.Timestamp, end_date: pd.Timestamp, name: str) -> pd.DataFrame:
        frame = (
            completed[completed["transaction_date"].between(start_date, end_date)]
            .groupby("store_id")
            .agg(gmv=("total_amount", "sum"), tx=("transaction_id", "nunique"))
            .reset_index()
            .merge(clean[["store_id", "variant"]], on="store_id")
        )
        frame[f"{name}_weekly_gmv"] = frame["gmv"] / 6
        frame[f"{name}_weekly_tx"] = frame["tx"] / 6
        frame[f"{name}_ticket"] = frame["gmv"] / frame["tx"]
        return frame[["store_id", "variant", f"{name}_weekly_gmv", f"{name}_weekly_tx", f"{name}_ticket"]]

    pre = period(pre_start, pre_end, "pre")
    test = period(start, end, "test")
    wide = pre.merge(test.drop(columns="variant"), on="store_id")
    wide["gmv_change"] = wide["test_weekly_gmv"] - wide["pre_weekly_gmv"]
    wide["tx_change"] = wide["test_weekly_tx"] - wide["pre_weekly_tx"]
    wide["ticket_change"] = wide["test_ticket"] - wide["pre_ticket"]

    results = {
        "ambiguous": ambiguous,
        "format_counts": clean.merge(stores, on="store_id").groupby(["variant", "format"]).size().unstack(fill_value=0),
        "size_summary": clean.merge(stores, on="store_id").groupby("variant")["size_sqm"].agg(["count", "mean", "median", "min", "max"]),
        "pre_summary": pre.groupby("variant").agg(
            n=("store_id", "nunique"),
            avg_weekly_gmv=("pre_weekly_gmv", "mean"),
            avg_weekly_tx=("pre_weekly_tx", "mean"),
            avg_ticket=("pre_ticket", "mean"),
        ),
        "test_summary": test.groupby("variant").agg(
            n=("store_id", "nunique"),
            avg_weekly_gmv=("test_weekly_gmv", "mean"),
            avg_weekly_tx=("test_weekly_tx", "mean"),
            avg_ticket=("test_ticket", "mean"),
        ),
        "ttest_gmv": welch_ttest(
            test[test["variant"] == "CONTROL"]["test_weekly_gmv"],
            test[test["variant"] == "TREATMENT"]["test_weekly_gmv"],
        ),
        "ttest_tx": welch_ttest(
            test[test["variant"] == "CONTROL"]["test_weekly_tx"],
            test[test["variant"] == "TREATMENT"]["test_weekly_tx"],
        ),
        "ttest_ticket": welch_ttest(
            test[test["variant"] == "CONTROL"]["test_ticket"],
            test[test["variant"] == "TREATMENT"]["test_ticket"],
        ),
        "ttest_change": welch_ttest(
            wide[wide["variant"] == "CONTROL"]["gmv_change"],
            wide[wide["variant"] == "TREATMENT"]["gmv_change"],
        ),
        "wide": wide,
    }
    return results


def svg_line_chart(data: pd.DataFrame, path: Path, title: str, x_col: str, y_col: str, series_col: str) -> None:
    width, height = 980, 460
    margin = {"left": 86, "right": 28, "top": 58, "bottom": 58}
    x_vals = sorted(data[x_col].unique())
    y_min, y_max = 0, data[y_col].max() * 1.08
    plot_w = width - margin["left"] - margin["right"]
    plot_h = height - margin["top"] - margin["bottom"]

    def x_pos(x):
        idx = x_vals.index(x)
        return margin["left"] + idx / max(1, len(x_vals) - 1) * plot_w

    def y_pos(y):
        return margin["top"] + plot_h - (y - y_min) / (y_max - y_min) * plot_h

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" fill="#fbfaf7"/>',
        f'<text x="{margin["left"]}" y="34" font-family="Arial" font-size="24" font-weight="700" fill="#1f2933">{title}</text>',
    ]
    for i in range(5):
        y = margin["top"] + i * plot_h / 4
        val = y_max - i * (y_max - y_min) / 4
        parts.append(f'<line x1="{margin["left"]}" y1="{y:.1f}" x2="{width-margin["right"]}" y2="{y:.1f}" stroke="#e5e2dc"/>')
        parts.append(f'<text x="22" y="{y+4:.1f}" font-family="Arial" font-size="12" fill="#667085">{money(val)}</text>')
    for name, group in data.groupby(series_col):
        points = " ".join(f"{x_pos(row[x_col]):.1f},{y_pos(row[y_col]):.1f}" for _, row in group.sort_values(x_col).iterrows())
        color = PALETTE.get(str(name), "#344054")
        parts.append(f'<polyline points="{points}" fill="none" stroke="{color}" stroke-width="3" stroke-linejoin="round"/>')
    legend_x = margin["left"]
    for idx, name in enumerate(sorted(data[series_col].unique())):
        color = PALETTE.get(str(name), "#344054")
        x = legend_x + idx * 175
        parts.append(f'<rect x="{x}" y="{height-34}" width="12" height="12" fill="{color}"/>')
        parts.append(f'<text x="{x+18}" y="{height-24}" font-family="Arial" font-size="13" fill="#344054">{name}</text>')
    for idx in np.linspace(0, len(x_vals) - 1, 6, dtype=int):
        x = x_pos(x_vals[idx])
        label = pd.Timestamp(x_vals[idx]).strftime("%Y-%m-%d")
        parts.append(f'<text x="{x-32:.1f}" y="{height-16}" font-family="Arial" font-size="11" fill="#667085">{label}</text>')
    parts.append("</svg>")
    path.write_text("\n".join(parts), encoding="utf-8")


def svg_bar_chart(data: pd.DataFrame, path: Path, title: str, label_col: str, value_col: str, color: str = "#176B87") -> None:
    width, height = 880, 430
    margin_left, margin_top, margin_right, margin_bottom = 190, 58, 34, 34
    plot_w = width - margin_left - margin_right
    row_h = (height - margin_top - margin_bottom) / len(data)
    max_val = data[value_col].max() * 1.08
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" fill="#fbfaf7"/>',
        f'<text x="{margin_left}" y="34" font-family="Arial" font-size="24" font-weight="700" fill="#1f2933">{title}</text>',
    ]
    for i, row in enumerate(data.itertuples()):
        y = margin_top + i * row_h + 5
        value = getattr(row, value_col)
        label = str(getattr(row, label_col))
        bar_w = value / max_val * plot_w
        parts.append(f'<text x="20" y="{y+row_h/2+4:.1f}" font-family="Arial" font-size="13" fill="#344054">{label}</text>')
        parts.append(f'<rect x="{margin_left}" y="{y:.1f}" width="{bar_w:.1f}" height="{row_h-10:.1f}" rx="3" fill="{color}"/>')
        parts.append(f'<text x="{margin_left+bar_w+8:.1f}" y="{y+row_h/2+4:.1f}" font-family="Arial" font-size="12" fill="#344054">{money(value)}</text>')
    parts.append("</svg>")
    path.write_text("\n".join(parts), encoding="utf-8")


def svg_cohort_heatmap(retention: pd.DataFrame, path: Path) -> None:
    months = [0, 1, 2, 3, 6]
    rows = list(retention.index)
    cell_w, cell_h = 88, 38
    width = 190 + len(months) * cell_w
    height = 76 + len(rows) * cell_h
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" fill="#fbfaf7"/>',
        '<text x="20" y="34" font-family="Arial" font-size="24" font-weight="700" fill="#1f2933">Retencion de cohortes de lealtad</text>',
    ]
    for j, month in enumerate(months):
        parts.append(f'<text x="{178+j*cell_w}" y="66" font-family="Arial" font-size="12" font-weight="700" fill="#344054">M{month}</text>')
    for i, cohort_month in enumerate(rows):
        y = 78 + i * cell_h
        parts.append(f'<text x="20" y="{y+24}" font-family="Arial" font-size="12" fill="#344054">{pd.Timestamp(cohort_month).strftime("%Y-%m")}</text>')
        for j, month in enumerate(months):
            val = retention.loc[cohort_month, month] if month in retention.columns else np.nan
            intensity = 0 if pd.isna(val) else min(1, max(0, val / 100))
            r = int(238 - intensity * 98)
            g = int(246 - intensity * 90)
            b = int(243 - intensity * 95)
            x = 150 + j * cell_w
            parts.append(f'<rect x="{x}" y="{y}" width="{cell_w-5}" height="{cell_h-5}" rx="3" fill="rgb({r},{g},{b})"/>')
            parts.append(f'<text x="{x+16}" y="{y+23}" font-family="Arial" font-size="12" fill="#1f2933">{"" if pd.isna(val) else f"{val:.1f}%"}</text>')
    parts.append("</svg>")
    path.write_text("\n".join(parts), encoding="utf-8")


def create_visuals(weekly: pd.DataFrame, pareto: pd.DataFrame, retention: pd.DataFrame, gaps: pd.DataFrame, ab: dict[str, object]) -> None:
    VIZ.mkdir(exist_ok=True)
    svg_line_chart(weekly, VIZ / "gmv_semanal_formato.svg", "Ventas netas semanales por formato", "week_start", "net_gmv", "format")
    top_categories = (
        pareto.groupby("category")["net_line_gmv"].sum().sort_values(ascending=False).reset_index().head(8)
    )
    svg_bar_chart(top_categories, VIZ / "pareto_categorias_gmv.svg", "Ventas netas por categoria", "category", "net_line_gmv", "#3E8E7E")
    svg_cohort_heatmap(retention, VIZ / "cohortes_retencion.svg")
    category_loss = gaps.groupby("category")["estimated_lost_gmv"].sum().sort_values(ascending=False).reset_index()
    svg_bar_chart(category_loss, VIZ / "stockouts_gmv_perdido_categoria.svg", "Ventas estimadas perdidas por quiebres", "category", "estimated_lost_gmv", "#C04B37")

    ab_summary = ab["test_summary"].reset_index()
    ab_summary = ab_summary.rename(columns={"avg_weekly_gmv": "value"})
    svg_bar_chart(ab_summary, VIZ / "ab_test_gmv_promedio.svg", "Prueba A/B: ventas semanales promedio por tienda", "variant", "value", "#D97941")


def write_sql_queries() -> None:
    sql = """-- Bloque 1 - SQL avanzado
-- Dialecto: BigQuery Standard SQL.
-- Supuesto: los CSV fueron cargados como tablas transactions, transaction_items, stores, products, vendors y store_promotions.
-- GMV neto: COMPLETED suma positivo y RETURNED resta.

-- Query 1: Ventas comparables (Comp Sales)
DECLARE current_start DATE DEFAULT DATE '2025-01-01';
DECLARE current_end DATE DEFAULT DATE '2025-06-30';
DECLARE previous_start DATE DEFAULT DATE_SUB(current_start, INTERVAL 1 YEAR);
DECLARE previous_end DATE DEFAULT DATE_SUB(current_end, INTERVAL 1 YEAR);

WITH tx AS (
  SELECT
    t.transaction_id,
    DATE(t.transaction_date) AS transaction_date,
    t.store_id,
    CASE WHEN t.status = 'RETURNED' THEN -t.total_amount ELSE t.total_amount END AS net_gmv
  FROM transactions t
),
eligible_stores AS (
  SELECT store_id, store_name, country, format
  FROM stores
  WHERE DATE(opening_date) <= previous_start
),
sales AS (
  SELECT
    s.country,
    s.format,
    s.store_id,
    s.store_name,
    SUM(IF(tx.transaction_date BETWEEN current_start AND current_end, tx.net_gmv, 0)) AS gmv_current,
    SUM(IF(tx.transaction_date BETWEEN previous_start AND previous_end, tx.net_gmv, 0)) AS gmv_previous
  FROM tx
  JOIN eligible_stores s USING (store_id)
  WHERE tx.transaction_date BETWEEN previous_start AND current_end
  GROUP BY 1, 2, 3, 4
)
SELECT
  country,
  format,
  store_id,
  store_name,
  gmv_current,
  gmv_previous,
  SAFE_DIVIDE(gmv_current, gmv_previous) - 1 AS comp_sales_growth_pct,
  DENSE_RANK() OVER (PARTITION BY format ORDER BY SAFE_DIVIDE(gmv_current, gmv_previous) - 1 DESC) AS rank_store_growth_in_format
FROM sales
WHERE gmv_current <> 0 AND gmv_previous <> 0
ORDER BY format, rank_store_growth_in_format;

-- Query 2: Productividad por metro cuadrado
WITH params AS (
  SELECT DATE '2025-04-01' AS quarter_start, DATE '2025-06-30' AS quarter_end
),
store_sales AS (
  SELECT
    s.store_id,
    s.store_name,
    s.country,
    s.format,
    s.region,
    s.size_sqm,
    SUM(CASE WHEN t.status = 'RETURNED' THEN -t.total_amount ELSE t.total_amount END) AS gmv,
    COUNT(DISTINCT t.transaction_id) AS transactions
  FROM transactions t
  JOIN stores s USING (store_id)
  CROSS JOIN params p
  WHERE DATE(t.transaction_date) BETWEEN p.quarter_start AND p.quarter_end
  GROUP BY 1, 2, 3, 4, 5, 6
),
scored AS (
  SELECT
    *,
    SAFE_DIVIDE(gmv, size_sqm) AS gmv_per_sqm,
    SAFE_DIVIDE(transactions, size_sqm) AS transactions_per_sqm,
    SAFE_DIVIDE(gmv, transactions) AS avg_ticket,
    PERCENTILE_CONT(SAFE_DIVIDE(gmv, size_sqm), 0.25) OVER (PARTITION BY format) AS p25_gmv_per_sqm
  FROM store_sales
)
SELECT
  *,
  DENSE_RANK() OVER (PARTITION BY format ORDER BY gmv_per_sqm DESC) AS rank_in_format,
  IF(gmv_per_sqm < p25_gmv_per_sqm, 'BAJO_RENDIMIENTO', 'OK') AS performance_flag
FROM scored
ORDER BY format, rank_in_format;

-- Query 3: Cohortes de clientes con tarjeta de lealtad
WITH loyalty_tx AS (
  SELECT
    customer_id,
    transaction_id,
    DATE_TRUNC(DATE(transaction_date), MONTH) AS tx_month,
    total_amount
  FROM transactions
  WHERE loyalty_card = TRUE
    AND customer_id IS NOT NULL
    AND status = 'COMPLETED'
),
first_purchase AS (
  SELECT customer_id, MIN(tx_month) AS cohort_month
  FROM loyalty_tx
  GROUP BY 1
),
activity AS (
  SELECT
    f.cohort_month,
    DATE_DIFF(l.tx_month, f.cohort_month, MONTH) AS month_n,
    l.customer_id,
    l.total_amount
  FROM loyalty_tx l
  JOIN first_purchase f USING (customer_id)
),
cohort_size AS (
  SELECT cohort_month, COUNT(DISTINCT customer_id) AS cohort_customers
  FROM first_purchase
  GROUP BY 1
),
metrics AS (
  SELECT
    a.cohort_month,
    a.month_n,
    COUNT(DISTINCT a.customer_id) AS active_customers,
    AVG(a.total_amount) AS avg_ticket,
    ANY_VALUE(cs.cohort_customers) AS cohort_customers,
    SAFE_DIVIDE(COUNT(DISTINCT a.customer_id), ANY_VALUE(cs.cohort_customers)) AS retention_rate
  FROM activity a
  JOIN cohort_size cs USING (cohort_month)
  WHERE month_n IN (0, 1, 2, 3, 6)
  GROUP BY 1, 2
)
SELECT
  cohort_month,
  MAX(cohort_customers) AS cohort_customers,
  MAX(IF(month_n = 0, retention_rate, NULL)) AS retention_m0,
  MAX(IF(month_n = 1, retention_rate, NULL)) AS retention_m1,
  MAX(IF(month_n = 2, retention_rate, NULL)) AS retention_m2,
  MAX(IF(month_n = 3, retention_rate, NULL)) AS retention_m3,
  MAX(IF(month_n = 6, retention_rate, NULL)) AS retention_m6,
  MAX(IF(month_n = 0, avg_ticket, NULL)) AS avg_ticket_m0,
  MAX(IF(month_n = 1, avg_ticket, NULL)) AS avg_ticket_m1,
  MAX(IF(month_n = 2, avg_ticket, NULL)) AS avg_ticket_m2,
  MAX(IF(month_n = 3, avg_ticket, NULL)) AS avg_ticket_m3,
  MAX(IF(month_n = 6, avg_ticket, NULL)) AS avg_ticket_m6,
  CASE
    WHEN MAX(IF(month_n = 6, avg_ticket, NULL)) > MAX(IF(month_n = 0, avg_ticket, NULL)) THEN 'CRECE'
    WHEN MAX(IF(month_n = 6, avg_ticket, NULL)) < MAX(IF(month_n = 0, avg_ticket, NULL)) THEN 'DECRECE'
    ELSE 'SIN_DATOS'
  END AS ticket_trend_m0_to_m6
FROM metrics
GROUP BY cohort_month
ORDER BY cohort_month;

-- Query 4: GMROI por proveedor y categoria
WITH item_sales AS (
  SELECT
    p.vendor_id,
    COALESCE(v.vendor_name, 'SIN_VENDOR') AS vendor_name,
    p.category,
    ti.item_id,
    DATE(t.transaction_date) AS sale_date,
    ti.quantity,
    ti.quantity * ti.unit_price AS gmv,
    ti.quantity * p.cost AS cost_total
  FROM transaction_items ti
  JOIN transactions t USING (transaction_id)
  JOIN products p USING (item_id)
  LEFT JOIN vendors v USING (vendor_id)
  WHERE t.status = 'COMPLETED'
)
SELECT
  vendor_id,
  vendor_name,
  category,
  SUM(gmv) AS gmv,
  SUM(cost_total) AS cost_total,
  SUM(gmv) - SUM(cost_total) AS gross_margin,
  SAFE_DIVIDE(SUM(gmv) - SUM(cost_total), SUM(cost_total)) AS gmroi,
  COUNT(DISTINCT item_id) AS active_skus,
  SAFE_DIVIDE(SUM(quantity), DATE_DIFF(MAX(sale_date), MIN(sale_date), DAY) + 1) AS sales_velocity_units_day,
  IF(SAFE_DIVIDE(SUM(gmv) - SUM(cost_total), SUM(cost_total)) < 1, 'GMROI_BAJO_1', 'OK') AS gmroi_flag
FROM item_sales
GROUP BY 1, 2, 3
ORDER BY gmroi ASC;

-- Query 5: Deteccion de posibles quiebres de stock
WITH params AS (SELECT DATE '2025-06-30' AS max_date),
daily_sales AS (
  SELECT
    t.store_id,
    ti.item_id,
    DATE(t.transaction_date) AS sale_date,
    SUM(ti.quantity) AS units,
    SUM(ti.quantity * ti.unit_price) AS gmv
  FROM transaction_items ti
  JOIN transactions t USING (transaction_id)
  WHERE t.status = 'COMPLETED'
  GROUP BY 1, 2, 3
),
store_item_bounds AS (
  SELECT store_id, item_id, MIN(sale_date) AS first_sale_date, (SELECT max_date FROM params) AS max_date
  FROM daily_sales
  GROUP BY 1, 2
),
spine AS (
  SELECT b.store_id, b.item_id, day AS calendar_date
  FROM store_item_bounds b, UNNEST(GENERATE_DATE_ARRAY(b.first_sale_date, b.max_date)) AS day
),
missing_days AS (
  SELECT
    s.store_id,
    s.item_id,
    s.calendar_date,
    DATE_SUB(s.calendar_date, INTERVAL ROW_NUMBER() OVER (PARTITION BY s.store_id, s.item_id ORDER BY s.calendar_date) DAY) AS island_key
  FROM spine s
  LEFT JOIN daily_sales d
    ON d.store_id = s.store_id
   AND d.item_id = s.item_id
   AND d.sale_date = s.calendar_date
  WHERE d.sale_date IS NULL
),
gaps AS (
  SELECT
    store_id,
    item_id,
    MIN(calendar_date) AS gap_start,
    MAX(calendar_date) AS gap_end,
    COUNT(*) AS gap_days
  FROM missing_days
  GROUP BY 1, 2, island_key
  HAVING COUNT(*) >= 3
),
scored AS (
  SELECT
    g.*,
    SAFE_DIVIDE((
      SELECT SUM(d.gmv)
      FROM daily_sales d
      WHERE d.store_id = g.store_id
        AND d.item_id = g.item_id
        AND d.sale_date BETWEEN DATE_SUB(g.gap_start, INTERVAL 14 DAY) AND DATE_SUB(g.gap_start, INTERVAL 1 DAY)
    ), 14) AS avg_daily_gmv_before_gap
  FROM gaps g
)
SELECT
  s.store_id,
  st.store_name,
  s.item_id,
  p.item_name,
  p.category,
  COALESCE(v.vendor_name, 'SIN_VENDOR') AS vendor_name,
  s.gap_start,
  s.gap_end,
  s.gap_days,
  s.avg_daily_gmv_before_gap,
  s.avg_daily_gmv_before_gap * s.gap_days AS estimated_lost_gmv
FROM scored s
JOIN stores st USING (store_id)
JOIN products p USING (item_id)
LEFT JOIN vendors v USING (vendor_id)
ORDER BY estimated_lost_gmv DESC;

-- Query 6: Impacto de promociones en ticket y volumen
WITH tx_category AS (
  SELECT
    t.transaction_id,
    p.category,
    LOGICAL_OR(ti.was_on_promo) AS has_promo_item,
    SUM(ti.quantity) AS category_units,
    SUM(ti.quantity * ti.unit_price) AS category_gmv,
    ANY_VALUE(t.total_amount) AS transaction_ticket
  FROM transactions t
  JOIN transaction_items ti USING (transaction_id)
  JOIN products p USING (item_id)
  WHERE t.status = 'COMPLETED'
  GROUP BY 1, 2
)
SELECT
  category,
  has_promo_item,
  COUNT(DISTINCT transaction_id) AS transactions,
  AVG(transaction_ticket) AS avg_ticket,
  AVG(category_units) AS avg_units,
  AVG(category_gmv) AS avg_category_gmv
FROM tx_category
GROUP BY 1, 2
ORDER BY category, has_promo_item;
"""
    (ROOT / "bloque1_queries.sql").write_text(sql, encoding="utf-8")


def write_model_docs() -> None:
    md = """# Bloque 2 - Modelo dimensional, pipeline y gobernanza

## A. Star schema propuesto para BigQuery

Grano principal: una fila por item vendido dentro de una transaccion (`fact_sales_item`). Este grano soporta GMROI, promociones, categorias, proveedores y composicion del basket. Para KPIs de tienda se agrega a `fact_store_day` como tabla derivada/materializada.

### Hechos

| Tabla | Grano | Campos clave |
| --- | --- | --- |
| `fact_sales_item` | Item por transaccion | transaction_item_id, transaction_id, date_key, store_key, product_key, customer_key nullable, promotion_key nullable, quantity, unit_price, gross_gmv, net_gmv, unit_cost, gross_margin |
| `fact_transaction` | Transaccion | transaction_id, date_key, store_key, customer_key nullable, payment_method, status, total_amount, net_gmv, loyalty_card |
| `fact_store_day` | Tienda-dia | date_key, store_key, net_gmv, transactions, avg_ticket, gmv_per_sqm, returned_amount |
| `fact_stock_gap` | Gap tienda-producto | store_key, product_key, gap_start_date_key, gap_end_date_key, gap_days, avg_daily_gmv_before_gap, estimated_lost_gmv |
| `fact_cohort_month` | Cohorte-mes | cohort_month_key, month_n, active_customers, retention_rate, avg_ticket |

### Dimensiones

| Tabla | Campos |
| --- | --- |
| `dim_date` | date_key, date, week_start, month, quarter, year, fiscal_week |
| `dim_store` | store_key, store_id, store_name, country, city, format, size_sqm, opening_date, region |
| `dim_product` | product_key, item_id, item_name, brand, vendor_key, category, department, cost |
| `dim_vendor` | vendor_key, vendor_id, vendor_name, country, tier, is_shared_catalog |
| `dim_customer` | customer_key, customer_hash, loyalty_segment, first_purchase_month. Para compradores anonimos usar customer_key = -1 |
| `dim_promotion` | promotion_key, promo_name, variant, start_date, end_date, promo_type |

## Decisiones de diseno

1. `customer_id` nulo se modela como comprador anonimo. El 59.8% de transacciones no tiene cliente identificado; forzar un customer_id falso inflaria retencion. Para cohortes solo se usa `loyalty_card = TRUE`.
2. Se separa `fact_sales_item` de `fact_transaction`. La auditoria muestra 1,745 diferencias entre total de transaccion y suma de items; tienda y ticket deben usar el total reportado, mientras categoria/proveedor necesita el item.
3. `fact_store_day` es una tabla derivada. Comp Sales, productividad y dashboard diario necesitan respuestas rapidas por tienda/dia sin recalcular 542k lineas cada vez.
4. `dim_promotion` queda en una dimension separada porque una tienda puede tener experimentos por ventana temporal. Las asignaciones ambiguas se auditan y no se sobreescriben silenciosamente.
5. `fact_stock_gap` es una tabla operacional derivada. No representa inventario real; representa senales de ausencia de venta y debe cruzarse con inventario/ordenes cuando existan.

## B. Pipeline ETL/ELT

1. Ingesta raw cada hora a `raw_*` con particion por fecha de llegada y hash de archivo.
2. Staging valida tipos, llaves, duplicados y montos. Los errores se escriben en `dq_findings`.
3. Carga incremental usa `transaction_id` y `transaction_item_id` como llaves naturales con `MERGE`. Si llega el mismo ID, se actualiza solo si cambia el hash de fila.
4. Para retrasos de hasta 2 horas, el pipeline reprocesa una ventana movil de 3 horas y el cierre diario reprocesa D-1 completo.
5. Para detectar tiendas sin datos, se compara cada tienda activa contra su patron esperado. Si no reporta transacciones por 2 horas en horario operativo, se emite alerta; si falta un dia completo, se bloquea certificacion del dashboard.
6. Refresh diario: staging horario, marts de BI a las 05:00 hora local con reintento a las 06:00. El dashboard consume solo tablas certificadas.

## C. Gobernanza

- `customer_id` debe hashearse con salt administrado por Data Platform. Analistas ven `customer_hash`, no PII directa.
- Data owner de transacciones: Operaciones Retail/Ventas; Data Steward tecnico: Data Engineering.
- Si dos reportes muestran GMV distinto, primero se revisa definicion certificada de GMV, luego filtros de status/returns, granularidad item vs transaccion, timezone y fecha de actualizacion. La resolucion se documenta en un changelog de metricas.
"""
    (ROOT / "bloque2_decisiones.md").write_text(md, encoding="utf-8")
    (ROOT / "bloque2_modelo.mmd").write_text(
        """erDiagram
  dim_date ||--o{ fact_sales_item : date_key
  dim_store ||--o{ fact_sales_item : store_key
  dim_product ||--o{ fact_sales_item : product_key
  dim_vendor ||--o{ dim_product : vendor_key
  dim_customer ||--o{ fact_sales_item : customer_key
  dim_promotion ||--o{ fact_sales_item : promotion_key
  dim_store ||--o{ fact_store_day : store_key
  dim_date ||--o{ fact_store_day : date_key
  dim_product ||--o{ fact_stock_gap : product_key
  dim_store ||--o{ fact_stock_gap : store_key
""",
        encoding="utf-8",
    )

    pdf = ROOT / "bloque2_modelo.pdf"
    c = canvas.Canvas(str(pdf), pagesize=landscape(letter))
    w, h = landscape(letter)
    c.setFillColor(colors.HexColor("#1f2933"))
    c.setFont("Helvetica-Bold", 22)
    c.drawString(0.55 * inch, h - 0.55 * inch, "Star Schema - Retail Data Mart")
    c.setFont("Helvetica", 10)
    c.drawString(0.55 * inch, h - 0.78 * inch, "Grano principal: item vendido por transaccion. Tablas derivadas para dashboard, cohortes y stock gaps.")

    boxes = {
        "fact_sales_item": (4.1 * inch, 2.55 * inch, 2.35 * inch, 1.35 * inch, "#176B87"),
        "dim_date": (0.55 * inch, 4.85 * inch, 2.0 * inch, 0.88 * inch, "#3E8E7E"),
        "dim_store": (0.55 * inch, 2.8 * inch, 2.0 * inch, 1.05 * inch, "#3E8E7E"),
        "dim_product": (7.75 * inch, 3.82 * inch, 2.2 * inch, 1.05 * inch, "#D97941"),
        "dim_vendor": (10.2 * inch, 3.82 * inch, 1.75 * inch, 1.05 * inch, "#D97941"),
        "dim_customer": (0.55 * inch, 1.1 * inch, 2.0 * inch, 0.9 * inch, "#7B4B94"),
        "dim_promotion": (7.75 * inch, 1.6 * inch, 2.2 * inch, 0.9 * inch, "#C04B37"),
        "fact_store_day": (4.1 * inch, 4.75 * inch, 2.35 * inch, 0.92 * inch, "#176B87"),
        "fact_stock_gap": (4.1 * inch, 0.95 * inch, 2.35 * inch, 0.92 * inch, "#176B87"),
        "fact_cohort_month": (7.75 * inch, 0.55 * inch, 2.2 * inch, 0.8 * inch, "#176B87"),
    }

    def draw_box(name, x, y, bw, bh, color):
        c.setFillColor(colors.HexColor(color))
        c.roundRect(x, y, bw, bh, 6, fill=1, stroke=0)
        c.setFillColor(colors.white)
        c.setFont("Helvetica-Bold", 10)
        c.drawString(x + 0.12 * inch, y + bh - 0.25 * inch, name)
        c.setFont("Helvetica", 7.8)
        field_map = {
            "fact_sales_item": "qty, price, net_gmv, cost, margin",
            "fact_store_day": "gmv, tx, ticket, gmv_per_sqm",
            "fact_stock_gap": "gap_days, avg_before, lost_gmv",
            "fact_cohort_month": "retention, avg_ticket",
            "dim_store": "country, format, region, size",
            "dim_product": "category, department, cost",
            "dim_vendor": "tier, country, shared_catalog",
            "dim_customer": "hash, segment, first_month",
            "dim_promotion": "variant, dates, type",
            "dim_date": "week, month, quarter, year",
        }
        c.drawString(x + 0.12 * inch, y + 0.18 * inch, field_map[name])

    for name, params in boxes.items():
        draw_box(name, *params)

    c.setStrokeColor(colors.HexColor("#667085"))
    c.setLineWidth(1.2)

    def center(name):
        x, y, bw, bh, _ = boxes[name]
        return x + bw / 2, y + bh / 2

    for a, b in [
        ("dim_date", "fact_sales_item"),
        ("dim_store", "fact_sales_item"),
        ("dim_product", "fact_sales_item"),
        ("dim_customer", "fact_sales_item"),
        ("dim_promotion", "fact_sales_item"),
        ("dim_vendor", "dim_product"),
        ("dim_store", "fact_store_day"),
        ("dim_date", "fact_store_day"),
        ("dim_store", "fact_stock_gap"),
        ("dim_product", "fact_stock_gap"),
        ("dim_customer", "fact_cohort_month"),
    ]:
        x1, y1 = center(a)
        x2, y2 = center(b)
        c.line(x1, y1, x2, y2)
    c.showPage()
    c.save()


def write_kpi_framework() -> None:
    rows = [
        ["Ventas netas por metro cuadrado", "Ventas netas por cada metro cuadrado de tienda", "Ventas netas / metros cuadrados de tienda", "Semanal", "fact_store_day + dim_store", ">= p50 del formato", "Metros cuadrados nulos/cero, ventas negativas sin devoluciones"],
        ["Transacciones por metro cuadrado", "Cantidad de tickets por cada metro cuadrado", "Transacciones / metros cuadrados de tienda", "Semanal", "fact_store_day", ">= p50 del formato", "Caida >30% vs media movil sin alerta de cierre"],
        ["Ticket promedio neto", "Venta neta por transaccion", "Ventas netas / transacciones", "Diario", "fact_transaction", "+3% YoY comparable", "Total <=0 o transacciones duplicadas"],
        ["Conversion de lealtad", "Participacion de tickets identificados", "tx con loyalty_card / tx totales", "Semanal", "fact_transaction", "45% en 6 meses", "customer_id nulo con loyalty_card TRUE"],
        ["Retencion M1", "Clientes de cohorte que vuelven al mes 1", "clientes activos M1 / tamano cohorte", "Mensual", "fact_cohort_month", ">=70%", "Cohorte sin customer_hash o month_n negativo"],
        ["Indice de quiebre", "Ventas estimadas perdidas por falta de venta", "Ventas estimadas perdidas / ventas netas", "Diario", "fact_stock_gap + fact_store_day", "<2% de ventas netas", "Gap en producto sin ventas historicas"],
        ["Retorno de margen bruto sobre inversion", "Retorno de margen sobre costo", "(Ventas - costo) / costo", "Mensual", "fact_sales_item + dim_product", ">1.5 por proveedor-categoria", "Costo nulo/cero o proveedor inexistente"],
        ["Fill-rate proxy", "Leading indicator de abastecimiento", "1 - items activos con gap 3+ dias / items activos", "Diario", "fact_stock_gap", ">=97%", "Item marcado activo sin ventas ultimos 180 dias"],
        ["Puntaje de salud de productividad", "KPI compuesto de productividad", "0.4 ventas netas por metro cuadrado + 0.25 transacciones por metro cuadrado + 0.2 ticket + 0.15 fill-rate normalizados", "Semanal", "Marts certificados", ">=75/100", "Alguna metrica base faltante o fuera de rango"],
    ]
    text = [
        "# Bloque 4 - Framework de KPIs para productividad de tiendas",
        "",
        markdown_table(
            rows,
            [
                "KPI",
                "Definicion exacta",
                "Formula",
                "Frecuencia",
                "Fuente de datos",
                "Target sugerido",
                "Como detectas si el dato esta mal",
            ],
        ),
        "",
        "## North Star Metric",
        "",
        "**Puntaje de salud de productividad** es la North Star Metric del programa. Combina resultado financiero (ventas netas por metro cuadrado), actividad operativa (transacciones por metro cuadrado), experiencia/comportamiento de cliente (ticket y retencion via componentes) y disponibilidad (fill-rate proxy). Es mejor que usar solo ventas porque evita premiar tiendas grandes que venden mucho pero son ineficientes o tienen problemas de stock.",
        "",
        "## Leading indicator",
        "",
        "El **Fill-rate proxy** funciona como indicador predictivo: si empiezan gaps de venta en productos activos, el GMV futuro probablemente caera antes de que el cierre mensual lo muestre.",
    ]
    (ROOT / "bloque4_kpi_framework.md").write_text("\n".join(text), encoding="utf-8")


def write_analysis_html(
    comp_store: pd.DataFrame,
    comp_country: pd.DataFrame,
    prod: pd.DataFrame,
    retention: pd.DataFrame,
    ticket: pd.DataFrame,
    gmroi_df: pd.DataFrame,
    promo: pd.DataFrame,
    weekly: pd.DataFrame,
    cv: pd.DataFrame,
    pareto: pd.DataFrame,
    gaps: pd.DataFrame,
    ab: dict[str, object],
) -> None:
    top_peaks = weekly.sort_values("wow_abs", ascending=False).head(3)
    top_drops = weekly.sort_values("wow_abs").head(3)
    old = retention.loc[retention.index <= pd.Timestamp("2024-03-01"), 1].mean()
    recent_mask = (retention.index >= pd.Timestamp("2024-04-01")) & (retention.index <= pd.Timestamp("2024-06-01"))
    recent = retention.loc[recent_mask, 1].mean()
    category_loss = gaps.groupby("category")["estimated_lost_gmv"].sum().sort_values(ascending=False)
    vendor_loss = gaps.groupby(["vendor_id", "vendor_name"])["estimated_lost_gmv"].sum().sort_values(ascending=False).head(5)
    electronics_share = pareto[pareto["category"] == "Electrónica"]["net_line_gmv"].sum() / pareto["net_line_gmv"].sum() * 100
    gmroi_low = (gmroi_df["gmroi"] < 1).sum()
    ttest = ab["ttest_gmv"]
    change = ab["ttest_change"]

    sections = f"""
<!doctype html>
<html lang="es">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Bloque 3 - Analisis Exploratorio y A/B Test</title>
  <style>
    body {{ margin:0; font-family: Arial, sans-serif; color:#1f2933; background:#fbfaf7; line-height:1.5; }}
    main {{ max-width: 1120px; margin: 0 auto; padding: 34px 24px 56px; }}
    h1 {{ font-size: 34px; margin: 0 0 6px; }}
    h2 {{ margin-top: 34px; border-top: 1px solid #d9d5cc; padding-top: 24px; }}
    .grid {{ display:grid; grid-template-columns: repeat(4, 1fr); gap: 12px; margin: 22px 0; }}
    .kpi {{ background:#fff; border:1px solid #e7e2da; border-radius:8px; padding:16px; }}
    .kpi b {{ display:block; font-size: 22px; }}
    img {{ max-width: 100%; border:1px solid #e7e2da; border-radius:8px; margin: 12px 0; }}
    table {{ width:100%; border-collapse:collapse; font-size: 13px; background:#fff; }}
    th, td {{ border-bottom:1px solid #e7e2da; padding:8px; text-align:left; }}
    th {{ background:#f2efe8; }}
    .callout {{ background:#fff; border-left:4px solid #D97941; padding:14px 16px; margin:14px 0; }}
    @media (max-width: 800px) {{ .grid {{ grid-template-columns: 1fr 1fr; }} }}
  </style>
</head>
<body>
<main>
  <h1>Bloque 3 - Analisis Exploratorio + Experimentacion</h1>
  <p>Datos sinteticos de retail multiformato, enero 2024 a junio 2025. Las ventas netas restan devoluciones; la prueba A/B usa solo ventas completadas.</p>

  <div class="grid">
    <div class="kpi"><span>Ventas netas</span><b>{money(comp_store['current'].sum() + comp_store['previous'].sum())}</b></div>
    <div class="kpi"><span>Tiendas</span><b>{prod['store_id'].nunique()}</b></div>
    <div class="kpi"><span>Proveedores-categoria con retorno bajo</span><b>{gmroi_low}</b></div>
    <div class="kpi"><span>Ventas estimadas perdidas</span><b>{money(category_loss.sum())}</b></div>
  </div>

  <h2>Parte A - Analisis Exploratorio</h2>
  <h3>1. Estacionalidad por formato</h3>
  <img src="bloque3_visualizaciones/gmv_semanal_formato.svg" alt="Ventas netas semanales por formato">
  <p>El formato mas sensible es <b>{cv.iloc[0]['format']}</b>, con coeficiente de variacion {cv.iloc[0]['cv']:.2f}. Los picos principales se concentran alrededor de semanas comerciales fuertes; las caidas grandes se explican por cierres de ciclo/promocion o semanas posteriores a picos.</p>
  {top_peaks[['week_start','format','net_gmv','wow_abs','wow_pct']].round(2).to_html(index=False)}
  <p><b>Caidas mas significativas:</b></p>
  {top_drops[['week_start','format','net_gmv','wow_abs','wow_pct']].round(2).to_html(index=False)}

  <h3>2. Pareto de categorias por formato</h3>
  <img src="bloque3_visualizaciones/pareto_categorias_gmv.svg" alt="Pareto de categorias">
  <p>En todos los formatos, Electronica y Hogar explican alrededor de 76% de las ventas netas. El patron de HIPERMERCADO y DESCUENTO es muy parecido: no cambia tanto la mezcla lider, sino la productividad y escala por tienda. Esto sugiere que el comprador de descuento tambien esta usando el formato para compras de alto valor.</p>
  {pareto.sort_values(['format','cum_share']).groupby('format').head(3)[['format','category','share','cum_share']].assign(share=lambda d: (d['share']*100).round(1), cum_share=lambda d: (d['cum_share']*100).round(1)).to_html(index=False)}

  <h3>3. Cohortes de lealtad</h3>
  <img src="bloque3_visualizaciones/cohortes_retencion.svg" alt="Heatmap de cohortes">
  <p>Las cohortes recientes de abril-junio 2024 retienen mejor en M1 ({recent:.1f}%) que las cohortes enero-marzo ({old:.1f}%), aunque las cohortes recientes son pequenas. La mayor caida promedio ocurre de M0 a M1; despues hay recuperaciones, lo que apunta a compras recurrentes no necesariamente mensuales.</p>

  <h3>4. Quiebres de stock e impacto</h3>
  <img src="bloque3_visualizaciones/stockouts_gmv_perdido_categoria.svg" alt="Ventas estimadas perdidas por quiebres">
  <p>Se detectaron {len(gaps):,} gaps de 3+ dias. No todos son quiebres reales, pero priorizados por ventas estimadas perdidas apuntan a Electronica como el mayor riesgo: {money(category_loss.iloc[0])}. Proveedores con mayor impacto estimado:</p>
  {vendor_loss.reset_index().rename(columns={'estimated_lost_gmv':'lost_gmv'}).to_html(index=False)}

  <h3>5. Hallazgo libre</h3>
  <div class="callout">Electronica representa {electronics_share:.1f}% de las ventas totales aunque son 20 de 200 SKUs. Esto crea una concentracion fuerte: cualquier quiebre o error de precio en pocos SKUs mueve el resultado regional. La recomendacion es crear monitoreo diario de disponibilidad para los 20 SKUs de Electronica antes de expandirlo a todo el catalogo.</div>

  <h2>Parte B - Interpretacion de A/B Test</h2>
  <img src="bloque3_visualizaciones/ab_test_gmv_promedio.svg" alt="Prueba A/B de ventas promedio">
  <p>Validacion: hay dos tiendas asignadas a ambos grupos ({', '.join(ab['ambiguous'])}), excluidas del test primario. Los grupos limpios no son perfectamente comparables: CONTROL tiene tiendas mas grandes y mas hiper/supermercados.</p>
  <p>Resultado principal de ventas semanales promedio por tienda: diferencia TREATMENT - CONTROL = <b>{money2(ttest['diff'])}</b>, lift {ttest['lift_pct']:.1f}%, p-value {ttest['p_value']:.3f}, IC95% [{money2(ttest['ci_low'])}, {money2(ttest['ci_high'])}]. No es estadisticamente significativo y el signo es negativo en comparacion directa.</p>
  <p>Sin embargo, contra su propia linea base, TREATMENT mejora mientras CONTROL cae: diferencia-en-diferencias aproximada = {money2(change['diff'])}, p-value {change['p_value']:.3f}. Esto sugiere que el diseno necesita una repeticion con balance por formato/tamano antes de escalar.</p>
  <p><b>Decision:</b> no implementaria la exhibicion en todas las tiendas todavia. Haria un segundo test estratificado por formato y tamano, con costo de implementacion medido. Si el p-value fuera 0.08 y el lift cubre el costo, lo trataria como senal prometedora para piloto ampliado, no como rollout total.</p>
</main>
</body>
</html>
"""
    (ROOT / "bloque3_analisis.html").write_text(sections, encoding="utf-8")


def write_dashboard(dfs: dict[str, pd.DataFrame], retention: pd.DataFrame, prod: pd.DataFrame, gaps: pd.DataFrame) -> None:
    tx, stores = dfs["transactions"], dfs["stores"]
    daily = (
        tx.merge(stores, on="store_id")
        .groupby(["transaction_date", "store_id", "store_name", "country", "format", "region", "size_sqm"])
        .agg(gmv=("net_gmv", "sum"), tx=("transaction_id", "nunique"))
        .reset_index()
    )
    daily["date"] = daily["transaction_date"].dt.strftime("%Y-%m-%d")
    payload = {
        "daily": daily[["date", "store_id", "store_name", "country", "format", "region", "size_sqm", "gmv", "tx"]].to_dict("records"),
        "retention": [
            {"cohort": pd.Timestamp(idx).strftime("%Y-%m"), **{f"m{int(k)}": (None if pd.isna(v) else round(float(v), 1)) for k, v in row.items()}}
            for idx, row in retention.iterrows()
        ],
        "stock": gaps[gaps["active_gap"]]
        .head(250)[
            [
                "store_id",
                "store_name",
                "country",
                "format",
                "region",
                "item_id",
                "item_name",
                "category",
                "gap_days",
                "estimated_lost_gmv",
            ]
        ]
        .to_dict("records"),
    }
    default_start = (tx["transaction_date"].max() - pd.Timedelta(days=6)).strftime("%Y-%m-%d")
    default_end = tx["transaction_date"].max().strftime("%Y-%m-%d")
    html = f"""<!doctype html>
<html lang="es">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Dashboard operativo regional de retail</title>
  <style>
    :root {{ --ink:#1f2933; --muted:#667085; --line:#ded8cf; --paper:#fbfaf7; --panel:#ffffff; --red:#C04B37; --green:#3E8E7E; --orange:#D97941; --teal:#176B87; }}
    body {{ margin:0; font-family: Arial, sans-serif; color:var(--ink); background:var(--paper); }}
    header {{ padding:22px 28px 16px; border-bottom:1px solid var(--line); background:#fff; position:sticky; top:0; z-index:2; }}
    h1 {{ margin:0 0 12px; font-size:24px; }}
    .filters {{ display:grid; grid-template-columns: repeat(7, minmax(120px, 1fr)); gap:10px; align-items:end; }}
    label {{ display:block; font-size:11px; color:var(--muted); margin-bottom:4px; }}
    select, input {{ width:100%; box-sizing:border-box; padding:8px; border:1px solid var(--line); border-radius:6px; background:#fff; color:var(--ink); }}
    main {{ padding:22px 28px 46px; }}
    .kpis {{ display:grid; grid-template-columns: repeat(4, 1fr); gap:14px; margin-bottom:18px; }}
    .kpi {{ background:var(--panel); border:1px solid var(--line); border-radius:8px; padding:16px; min-height:78px; }}
    .kpi span {{ color:var(--muted); font-size:12px; }}
    .kpi strong {{ display:block; font-size:25px; margin-top:6px; }}
    .delta.up {{ color:var(--green); }} .delta.down {{ color:var(--red); }}
    .layout {{ display:grid; grid-template-columns: 1.2fr .8fr; gap:18px; align-items:start; }}
    section {{ background:#fff; border:1px solid var(--line); border-radius:8px; padding:16px; margin-bottom:18px; }}
    h2 {{ margin:0 0 12px; font-size:17px; }}
    svg {{ width:100%; height:320px; }}
    table {{ width:100%; border-collapse:collapse; font-size:12px; }}
    th, td {{ padding:7px 8px; border-bottom:1px solid #eee8df; text-align:left; }}
    th {{ color:var(--muted); font-weight:700; background:#f5f1ea; }}
    tr.low td {{ background:#fff0ed; }}
    .heat td {{ text-align:center; }}
    details.logic {{ margin-top:12px; border-top:1px solid #eee8df; padding-top:10px; }}
    details.logic summary {{ cursor:pointer; color:var(--teal); font-weight:700; font-size:13px; }}
    .logic p {{ color:var(--muted); font-size:13px; margin:8px 0; }}
    pre {{ white-space:pre-wrap; background:#17212b; color:#f4f7f9; padding:12px; border-radius:6px; overflow:auto; font-size:11px; line-height:1.45; }}
    @media (max-width: 1000px) {{ .filters, .kpis, .layout {{ grid-template-columns:1fr 1fr; }} }}
    @media (max-width: 700px) {{ .filters, .kpis, .layout {{ grid-template-columns:1fr; }} header {{ position:static; }} }}
  </style>
</head>
<body>
<header>
  <h1>Dashboard operativo regional de retail</h1>
  <div class="filters">
    <div><label>Pais</label><select id="country"><option value="">Todos</option></select></div>
    <div><label>Formato</label><select id="format"><option value="">Todos</option></select></div>
    <div><label>Region</label><select id="region"><option value="">Todas</option></select></div>
    <div><label>Fecha inicial</label><input id="start" type="date" value="{default_start}"></div>
    <div><label>Fecha final</label><input id="end" type="date" value="{default_end}"></div>
    <div><label>Alerta</label><select id="alert"><option value="">Todas las tiendas</option><option value="low">Debajo del percentil 25 de ventas por metro cuadrado</option></select></div>
    <div><label>Ordenar por</label><select id="sort"><option value="gmv_sqm">Ventas netas por metro cuadrado</option><option value="gmv">Ventas netas</option><option value="ticket">Ticket promedio</option></select></div>
  </div>
</header>
<main>
  <div class="kpis">
    <div class="kpi"><span>Ventas netas</span><strong id="kpi-gmv">$0</strong><div id="delta-gmv" class="delta"></div></div>
    <div class="kpi"><span>Transacciones</span><strong id="kpi-tx">0</strong><div id="delta-tx" class="delta"></div></div>
    <div class="kpi"><span>Ticket promedio</span><strong id="kpi-ticket">$0</strong><div id="delta-ticket" class="delta"></div></div>
    <div class="kpi"><span>Ventas netas por metro cuadrado</span><strong id="kpi-sqm">$0</strong><div id="delta-sqm" class="delta"></div></div>
  </div>
  <section>
    <h2>Indicadores principales</h2>
    <details class="logic" open>
      <summary>Explicacion tecnica y consulta base</summary>
      <p>Los indicadores usan ventas netas: una venta completada suma y una devolucion resta. El ticket promedio divide ventas netas entre transacciones. Las ventas netas por metro cuadrado dividen las ventas netas entre el tamano de las tiendas incluidas por los filtros.</p>
      <pre><code>WITH ventas_por_tienda AS (
  SELECT
    s.store_id,
    s.size_sqm,
    SUM(CASE WHEN t.status = 'RETURNED' THEN -t.total_amount ELSE t.total_amount END) AS ventas_netas,
    COUNT(DISTINCT t.transaction_id) AS transacciones
  FROM dbo.transactions t
  JOIN dbo.stores s ON s.store_id = t.store_id
  WHERE t.transaction_date BETWEEN @fecha_inicial AND @fecha_final
  GROUP BY s.store_id, s.size_sqm
)
SELECT
  SUM(ventas_netas) AS ventas_netas,
  SUM(transacciones) AS transacciones,
  SUM(ventas_netas) / NULLIF(SUM(transacciones), 0) AS ticket_promedio,
  SUM(ventas_netas) / NULLIF(SUM(size_sqm), 0) AS ventas_netas_por_metro_cuadrado
FROM ventas_por_tienda;</code></pre>
    </details>
  </section>
  <div class="layout">
    <div>
      <section>
        <h2>Tendencia semanal de ventas comparables</h2>
        <svg id="trend" viewBox="0 0 900 320"></svg>
        <details class="logic">
          <summary>Explicacion tecnica y consulta usada</summary>
          <p>La grafica agrupa las ventas netas por semana y por formato. En entrevista puedes explicarlo asi: convierto cada transaccion a venta neta, uno la tienda para saber el formato y agrego por inicio de semana.</p>
          <pre><code>SET DATEFIRST 1; -- lunes como primer dia de la semana

SELECT
  DATEADD(day, 1 - DATEPART(weekday, CAST(t.transaction_date AS date)), CAST(t.transaction_date AS date)) AS semana,
  s.format AS formato,
  SUM(CASE WHEN t.status = 'RETURNED' THEN -t.total_amount ELSE t.total_amount END) AS ventas_netas
FROM dbo.transactions t
JOIN dbo.stores s ON s.store_id = t.store_id
WHERE t.transaction_date BETWEEN @fecha_inicial AND @fecha_final
GROUP BY DATEADD(day, 1 - DATEPART(weekday, CAST(t.transaction_date AS date)), CAST(t.transaction_date AS date)), s.format
ORDER BY semana, formato;</code></pre>
        </details>
      </section>
      <section>
        <h2>Ranking de tiendas por formato</h2>
        <table id="ranking"></table>
        <details class="logic">
          <summary>Explicacion tecnica y consulta usada</summary>
          <p>Este ranking calcula ventas netas, ticket promedio y ventas netas por metro cuadrado por tienda. Luego compara cada tienda contra el percentil 25 de su formato para marcar bajo rendimiento.</p>
          <pre><code>WITH ventas_tienda AS (
  SELECT
    s.store_id,
    s.store_name,
    s.format,
    s.size_sqm,
    SUM(CASE WHEN t.status = 'RETURNED' THEN -t.total_amount ELSE t.total_amount END) AS ventas_netas,
    COUNT(DISTINCT t.transaction_id) AS transacciones
  FROM dbo.transactions t
  JOIN dbo.stores s ON s.store_id = t.store_id
  WHERE t.transaction_date BETWEEN @fecha_inicial AND @fecha_final
  GROUP BY s.store_id, s.store_name, s.format, s.size_sqm
),
scored AS (
  SELECT
    *,
    ventas_netas / NULLIF(size_sqm, 0) AS ventas_netas_por_metro_cuadrado,
    ventas_netas / NULLIF(transacciones, 0) AS ticket_promedio,
    PERCENTILE_CONT(0.25) WITHIN GROUP (ORDER BY ventas_netas / NULLIF(size_sqm, 0))
      OVER (PARTITION BY format) AS percentil_25_formato
  FROM ventas_tienda
)
SELECT *,
  CASE WHEN ventas_netas_por_metro_cuadrado < percentil_25_formato THEN 'BAJO_RENDIMIENTO' ELSE 'OK' END AS alerta
FROM scored
ORDER BY format, ventas_netas_por_metro_cuadrado DESC;</code></pre>
        </details>
      </section>
      <section>
        <h2>Retencion de clientes de lealtad por cohorte</h2>
        <table id="retention" class="heat"></table>
        <details class="logic">
          <summary>Explicacion tecnica y consulta usada</summary>
          <p>Una cohorte es el mes de primera compra del cliente identificado. La retencion del mes 1, 2, 3 o 6 es el porcentaje de clientes de esa cohorte que vuelve a comprar en ese mes relativo.</p>
          <pre><code>WITH ventas_lealtad AS (
  SELECT
    customer_id,
    DATEFROMPARTS(YEAR(transaction_date), MONTH(transaction_date), 1) AS mes_compra,
    total_amount
  FROM dbo.transactions
  WHERE loyalty_card = 1 AND customer_id IS NOT NULL AND status = 'COMPLETED'
),
primera_compra AS (
  SELECT customer_id, MIN(mes_compra) AS mes_cohorte
  FROM ventas_lealtad
  GROUP BY customer_id
),
actividad AS (
  SELECT
    p.mes_cohorte,
    DATEDIFF(month, p.mes_cohorte, v.mes_compra) AS mes_relativo,
    v.customer_id,
    v.total_amount
  FROM ventas_lealtad v
  JOIN primera_compra p ON p.customer_id = v.customer_id
)
SELECT
  mes_cohorte,
  COUNT(DISTINCT CASE WHEN mes_relativo = 0 THEN customer_id END) AS clientes_cohorte,
  COUNT(DISTINCT CASE WHEN mes_relativo = 1 THEN customer_id END) * 1.0
    / NULLIF(COUNT(DISTINCT CASE WHEN mes_relativo = 0 THEN customer_id END), 0) AS retencion_mes_1,
  COUNT(DISTINCT CASE WHEN mes_relativo = 2 THEN customer_id END) * 1.0
    / NULLIF(COUNT(DISTINCT CASE WHEN mes_relativo = 0 THEN customer_id END), 0) AS retencion_mes_2,
  COUNT(DISTINCT CASE WHEN mes_relativo = 3 THEN customer_id END) * 1.0
    / NULLIF(COUNT(DISTINCT CASE WHEN mes_relativo = 0 THEN customer_id END), 0) AS retencion_mes_3,
  COUNT(DISTINCT CASE WHEN mes_relativo = 6 THEN customer_id END) * 1.0
    / NULLIF(COUNT(DISTINCT CASE WHEN mes_relativo = 0 THEN customer_id END), 0) AS retencion_mes_6
FROM actividad
GROUP BY mes_cohorte
ORDER BY mes_cohorte;</code></pre>
        </details>
      </section>
    </div>
    <div>
      <section>
        <h2>Quiebres activos de venta por tienda y producto</h2>
        <table id="stock"></table>
        <details class="logic">
          <summary>Explicacion tecnica y consulta usada</summary>
          <p>Un posible quiebre aparece cuando un producto que historicamente se vendia en una tienda deja de venderse por tres o mas dias. La perdida estimada usa el promedio diario de ventas de los 14 dias previos multiplicado por la duracion del gap.</p>
          <pre><code>WITH ventas_diarias AS (
  SELECT
    t.store_id,
    ti.item_id,
    CAST(t.transaction_date AS date) AS fecha,
    SUM(ti.quantity * ti.unit_price) AS ventas
  FROM dbo.transaction_items ti
  JOIN dbo.transactions t ON t.transaction_id = ti.transaction_id
  WHERE t.status = 'COMPLETED'
  GROUP BY t.store_id, ti.item_id, CAST(t.transaction_date AS date)
),
gaps_priorizados AS (
  SELECT TOP 20
    store_id,
    item_id,
    MAX(fecha) AS ultima_fecha_con_venta,
    DATEDIFF(day, MAX(fecha), '2025-06-30') AS dias_sin_venta
  FROM ventas_diarias
  GROUP BY store_id, item_id
  HAVING DATEDIFF(day, MAX(fecha), '2025-06-30') >= 3
)
SELECT
  g.store_id,
  s.store_name,
  g.item_id,
  p.item_name,
  g.dias_sin_venta,
  (SELECT SUM(v.ventas) / 14.0
   FROM ventas_diarias v
   WHERE v.store_id = g.store_id
     AND v.item_id = g.item_id
     AND v.fecha BETWEEN DATEADD(day, -14, DATEADD(day, 1, g.ultima_fecha_con_venta)) AND g.ultima_fecha_con_venta)
   * g.dias_sin_venta AS ventas_estimadas_perdidas
FROM gaps_priorizados g
JOIN dbo.stores s ON s.store_id = g.store_id
JOIN dbo.products p ON p.item_id = g.item_id
ORDER BY ventas_estimadas_perdidas DESC;</code></pre>
        </details>
      </section>
    </div>
  </div>
</main>
<script>
const DATA = {json.dumps(payload, ensure_ascii=False)};
const fmtMoney = v => '$' + Math.round(v).toLocaleString('en-US');
const fmtPct = v => (v>=0?'+':'') + v.toFixed(1) + '% comparado con periodo anterior';
const byId = id => document.getElementById(id);
const colors = {{'HIPERMERCADO':'#176B87','SUPERMERCADO':'#3E8E7E','DESCUENTO':'#D97941','EXPRESS':'#7B4B94','2025':'#176B87','2024':'#D97941'}};

function unique(field) {{ return [...new Set(DATA.daily.map(d => d[field]))].sort(); }}
for (const field of ['country','format','region']) {{
  const el = byId(field);
  unique(field).forEach(v => el.insertAdjacentHTML('beforeend', `<option value="${{v}}">${{v}}</option>`));
  el.addEventListener('change', update);
}}
['start','end','alert','sort'].forEach(id => byId(id).addEventListener('change', update));

function filtered(start=null, end=null) {{
  const c=byId('country').value, f=byId('format').value, r=byId('region').value;
  const s=start || byId('start').value, e=end || byId('end').value;
  return DATA.daily.filter(d => (!c || d.country===c) && (!f || d.format===f) && (!r || d.region===r) && d.date>=s && d.date<=e);
}}

function summarize(rows) {{
  const gmv = rows.reduce((a,d)=>a+d.gmv,0);
  const tx = rows.reduce((a,d)=>a+d.tx,0);
  const size = [...new Map(rows.map(d=>[d.store_id,d.size_sqm])).values()].reduce((a,d)=>a+d,0);
  return {{gmv, tx, ticket: tx?gmv/tx:0, sqm: size?gmv/size:0}};
}}

function delta(current, previous) {{
  if (!previous) return '';
  return fmtPct((current/previous-1)*100);
}}

function setDelta(id, value) {{
  const el = byId(id); el.textContent = value;
  el.className = 'delta ' + (value.startsWith('+') ? 'up' : 'down');
}}

function storeRanking(rows) {{
  const map = new Map();
  rows.forEach(d => {{
    if (!map.has(d.store_id)) map.set(d.store_id, {{...d, gmv:0, tx:0}});
    const x = map.get(d.store_id); x.gmv += d.gmv; x.tx += d.tx;
  }});
  let arr = [...map.values()].map(d => ({{...d, gmv_sqm:d.gmv/d.size_sqm, ticket:d.tx?d.gmv/d.tx:0}}));
  const byFormat = {{}};
  arr.forEach(d => {{ (byFormat[d.format] ||= []).push(d.gmv_sqm); }});
  arr.forEach(d => {{ const vals = byFormat[d.format].sort((a,b)=>a-b); d.p25 = vals[Math.floor((vals.length-1)*0.25)]; d.low = d.gmv_sqm < d.p25; }});
  if (byId('alert').value === 'low') arr = arr.filter(d=>d.low);
  const sort = byId('sort').value;
  arr.sort((a,b)=>b[sort]-a[sort]);
  const rowsHtml = arr.slice(0,18).map(d=>`<tr class="${{d.low?'low':''}}"><td>${{d.store_name}}</td><td>${{d.format}}</td><td>${{fmtMoney(d.gmv)}}</td><td>${{fmtMoney(d.gmv_sqm)}}</td><td>${{fmtMoney(d.ticket)}}</td></tr>`).join('');
  byId('ranking').innerHTML = '<tr><th>Tienda</th><th>Formato</th><th>Ventas netas</th><th>Ventas netas por metro cuadrado</th><th>Ticket promedio</th></tr>' + rowsHtml;
}}

function drawTrend(rows) {{
  const svg = byId('trend'); svg.innerHTML = '';
  const weekly = new Map();
  rows.forEach(d => {{
    const date = new Date(d.date + 'T00:00:00');
    const monday = new Date(date); monday.setDate(date.getDate() - ((date.getDay()+6)%7));
    const year = String(date.getFullYear());
    const wk = monday.toISOString().slice(5,10);
    const key = year + '|' + wk;
    weekly.set(key, (weekly.get(key)||0) + d.gmv);
  }});
  const pointsByYear = {{}};
  [...weekly.entries()].forEach(([key,val]) => {{ const [year,wk]=key.split('|'); (pointsByYear[year] ||= []).push({{wk,val}}); }});
  const years = Object.keys(pointsByYear).sort();
  const xVals = [...new Set([].concat(...years.map(y=>pointsByYear[y].map(p=>p.wk))))].sort();
  const maxY = Math.max(1, ...[].concat(...years.map(y=>pointsByYear[y].map(p=>p.val))))*1.08;
  const x = wk => 55 + xVals.indexOf(wk)/Math.max(1,xVals.length-1)*790;
  const y = val => 270 - val/maxY*220;
  for (let i=0;i<5;i++) {{
    const yy = 50+i*55; svg.insertAdjacentHTML('beforeend', `<line x1="55" y1="${{yy}}" x2="850" y2="${{yy}}" stroke="#e7e2da"/>`);
  }}
  years.forEach(year => {{
    const pts = pointsByYear[year].sort((a,b)=>a.wk.localeCompare(b.wk)).map(p=>`${{x(p.wk)}},${{y(p.val)}}`).join(' ');
    svg.insertAdjacentHTML('beforeend', `<polyline points="${{pts}}" fill="none" stroke="${{colors[year]||'#667085'}}" stroke-width="3"/>`);
  }});
  years.forEach((year,i)=>svg.insertAdjacentHTML('beforeend', `<text x="${{70+i*90}}" y="305" fill="${{colors[year]}}" font-size="13">${{year}}</text>`));
}}

function renderRetention() {{
  const headers = ['Cohorte','Mes 0','Mes 1','Mes 2','Mes 3','Mes 6'];
  const rows = DATA.retention.map(r => `<tr><td>${{r.cohort}}</td>${{['m0','m1','m2','m3','m6'].map(k=>`<td style="background:rgba(62,142,126,${{(r[k]||0)/120}})">${{r[k]==null?'':r[k]+'%'}}</td>`).join('')}}</tr>`).join('');
  byId('retention').innerHTML = '<tr>' + headers.map(h=>`<th>${{h}}</th>`).join('') + '</tr>' + rows;
}}

function renderStock() {{
  const c=byId('country').value, f=byId('format').value, r=byId('region').value;
  const rows = DATA.stock.filter(d => (!c || d.country===c) && (!f || d.format===f) && (!r || d.region===r)).slice(0,20);
  byId('stock').innerHTML = '<tr><th>Tienda</th><th>Producto</th><th>Dias sin venta</th><th>Ventas estimadas perdidas</th></tr>' + rows.map(d=>`<tr><td>${{d.store_name}}</td><td>${{d.item_name}}</td><td>${{d.gap_days}}</td><td>${{fmtMoney(d.estimated_lost_gmv)}}</td></tr>`).join('');
}}

function update() {{
  const rows = filtered();
  const s = summarize(rows);
  const start = new Date(byId('start').value + 'T00:00:00');
  const end = new Date(byId('end').value + 'T00:00:00');
  const days = Math.max(1, Math.round((end - start) / 86400000) + 1);
  const prevEnd = new Date(start); prevEnd.setDate(start.getDate()-1);
  const prevStart = new Date(prevEnd); prevStart.setDate(prevEnd.getDate()-days+1);
  const p = summarize(filtered(prevStart.toISOString().slice(0,10), prevEnd.toISOString().slice(0,10)));
  byId('kpi-gmv').textContent = fmtMoney(s.gmv);
  byId('kpi-tx').textContent = Math.round(s.tx).toLocaleString('en-US');
  byId('kpi-ticket').textContent = fmtMoney(s.ticket);
  byId('kpi-sqm').textContent = fmtMoney(s.sqm);
  setDelta('delta-gmv', delta(s.gmv,p.gmv));
  setDelta('delta-tx', delta(s.tx,p.tx));
  setDelta('delta-ticket', delta(s.ticket,p.ticket));
  setDelta('delta-sqm', delta(s.sqm,p.sqm));
  drawTrend(rows); storeRanking(rows); renderRetention(); renderStock();
}}
update();
</script>
</body>
</html>"""
    (ROOT / "bloque5_dashboard.html").write_text(html, encoding="utf-8")


def write_presentation(ab: dict[str, object], comp_store: pd.DataFrame, prod: pd.DataFrame, gaps: pd.DataFrame, gmroi_df: pd.DataFrame, retention: pd.DataFrame) -> None:
    pdf = ROOT / "bloque5_presentacion_EN.pdf"
    c = canvas.Canvas(str(pdf), pagesize=landscape(letter))
    w, h = landscape(letter)

    def slide(title: str, bullets: list[str], footer: str = ""):
        c.setFillColor(colors.HexColor("#fbfaf7"))
        c.rect(0, 0, w, h, fill=1, stroke=0)
        c.setFillColor(colors.HexColor("#176B87"))
        c.rect(0, h - 0.18 * inch, w, 0.18 * inch, fill=1, stroke=0)
        c.setFillColor(colors.HexColor("#1f2933"))
        c.setFont("Helvetica-Bold", 28)
        c.drawString(0.65 * inch, h - 0.75 * inch, title)
        c.setFont("Helvetica", 17)
        y = h - 1.45 * inch
        for b in bullets:
            c.setFillColor(colors.HexColor("#D97941"))
            c.circle(0.82 * inch, y + 0.07 * inch, 4, fill=1, stroke=0)
            c.setFillColor(colors.HexColor("#1f2933"))
            text = c.beginText(1.05 * inch, y)
            text.setFont("Helvetica", 16)
            for line in wrap_text(b, 88):
                text.textLine(line)
            c.drawText(text)
            y -= 0.72 * inch
        if footer:
            c.setFont("Helvetica", 10)
            c.setFillColor(colors.HexColor("#667085"))
            c.drawString(0.65 * inch, 0.45 * inch, footer)
        c.showPage()

    best = comp_store.sort_values("growth_pct", ascending=False).iloc[0]
    worst = comp_store.sort_values("growth_pct").iloc[0]
    low_stores = int((prod["performance_flag"] == "BAJO_RENDIMIENTO").sum())
    lost_total = gaps["estimated_lost_gmv"].sum()
    low_gmroi = int((gmroi_df["gmroi"] < 1).sum())
    m1_large = retention.loc[retention.index <= pd.Timestamp("2024-03-01"), 1].dropna().mean()
    t = ab["ttest_gmv"]
    change = ab["ttest_change"]

    slide(
        "1. Executive Summary",
        [
            f"Net sales are concentrated: Electronics is the main category and drives more than half of total sales.",
            f"Stock gap signals show {money(lost_total)} estimated lost sales. This is the largest operational risk.",
            f"The A/B test is not ready for rollout: p-value is {t['p_value']:.3f} and two stores had both variants.",
        ],
    )
    slide(
        "2. Store Performance",
        [
            f"Best comparable store: {best['store_id']} with {best['growth_pct']:.1f}% growth.",
            f"Weakest comparable store: {worst['store_id']} with {worst['growth_pct']:.1f}% growth.",
            f"{low_stores} stores are below the p25 of GMV per square meter inside their format.",
        ],
    )
    slide(
        "3. Opportunities",
        [
            f"Fix low productivity stores first. Target the bottom {low_stores} stores with a weekly action plan.",
            f"{low_gmroi} vendor-category combinations have GMROI below 1. They cost more than the gross margin they create.",
            f"Loyalty M1 retention in the large early cohorts is {m1_large:.1f}%. The biggest drop happens after the first purchase.",
        ],
    )
    slide(
        "4. Risks",
        [
            "Data quality risk: 1,745 transactions do not match item totals. Use transaction total for store sales.",
            "Experiment risk: Treatment stores are smaller before the test. The groups are not fully balanced.",
            f"Stock risk: top categories with gaps can erase millions in sales if supply is not corrected.",
        ],
    )
    slide(
        "5. Recommendations",
        [
            "Do not roll out the new display to all stores yet. Run a second balanced test by format and size.",
            f"Create a daily stock alert for the top 20 Electronics SKUs. Owner: Supply Chain. Start in 30 days.",
            f"Launch a 90-day productivity sprint for stores below p25 net sales per square meter. Owner: Regional Operations.",
        ],
        "Simple English version for VP Operations review.",
    )
    c.save()


def wrap_text(text: str, width: int) -> list[str]:
    words = text.split()
    lines, current = [], []
    length = 0
    for word in words:
        if length + len(word) + len(current) > width:
            lines.append(" ".join(current))
            current = [word]
            length = len(word)
        else:
            current.append(word)
            length += len(word)
    if current:
        lines.append(" ".join(current))
    return lines


def write_summary_exports(
    comp_store: pd.DataFrame,
    comp_country: pd.DataFrame,
    prod: pd.DataFrame,
    retention: pd.DataFrame,
    ticket: pd.DataFrame,
    gmroi_df: pd.DataFrame,
    promo: pd.DataFrame,
    weekly: pd.DataFrame,
    pareto: pd.DataFrame,
    gaps: pd.DataFrame,
) -> None:
    PROCESSED.mkdir(exist_ok=True)
    comp_store.to_csv(PROCESSED / "comp_sales_store.csv", index=False)
    comp_country.to_csv(PROCESSED / "comp_sales_country_format.csv", index=False)
    prod.to_csv(PROCESSED / "productivity_store_q2_2025.csv", index=False)
    retention.to_csv(PROCESSED / "cohort_retention.csv")
    ticket.to_csv(PROCESSED / "cohort_ticket.csv")
    gmroi_df.to_csv(PROCESSED / "gmroi_vendor_category.csv", index=False)
    promo.to_csv(PROCESSED / "promo_basket_category.csv", index=False)
    weekly.to_csv(PROCESSED / "weekly_gmv_format.csv", index=False)
    pareto.to_csv(PROCESSED / "pareto_category_format.csv", index=False)
    gaps.head(1000).to_csv(PROCESSED / "stock_gaps_top1000.csv", index=False)


def write_readme(dfs: dict[str, pd.DataFrame]) -> None:
    tx = dfs["transactions"]
    text = f"""# Prueba tecnica Data Analyst - Retail Centroamerica

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
source .venv/bin/activate  # En Windows: .venv\\Scripts\\activate
pip install -r requirements.txt
python scripts/generate_all.py
```

En una computadora donde no puedas instalar programas, puedes revisar todos los entregables ya generados sin ejecutar nada. Para mostrar la parte de base de datos desde VS Code, abre `sql/README_SQL_SERVER.md` y ejecuta los scripts numerados de la carpeta `sql/` con la extension MSSQL.

## Datos

- Periodo: {tx['transaction_date'].min().date()} a {tx['transaction_date'].max().date()}
- Transacciones: {len(tx):,}
- Items: {len(dfs['items']):,}
- Tiendas: {len(dfs['stores']):,}
- Productos: {len(dfs['products']):,}

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
"""
    (ROOT / "README.md").write_text(text, encoding="utf-8")


def write_support_files() -> None:
    (ROOT / "requirements.txt").write_text("pandas>=2.0\nnumpy>=1.24\nreportlab>=4.0\n", encoding="utf-8")
    (ROOT / ".gitignore").write_text(".DS_Store\n__pycache__/\n.venv/\n*.pyc\n", encoding="utf-8")
    (ROOT / ".vscode" / "tasks.json").write_text(
        json.dumps(
            {
                "version": "2.0.0",
                "tasks": [
                    {
                        "label": "Regenerar entregables",
                        "type": "shell",
                        "command": "python scripts/generate_all.py",
                        "group": "build",
                        "problemMatcher": [],
                    }
                ],
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    sqlserver_note = """# SQL Server desde VS Code

Esta carpeta permite demostrar la prueba tecnica como trabajo de base de datos usando la extension MSSQL de VS Code.

## Requisito

La extension MSSQL de VS Code es solo el cliente. Necesitas conectarte a un SQL Server existente: servidor de la empresa, Azure SQL, una maquina remota o un SQL Server ya instalado por TI. No necesitas instalar SQL Server localmente en tu computadora de trabajo.

## Orden recomendado

1. Abre VS Code en la carpeta del repo.
2. Instala o abre la extension **SQL Server (MSSQL)**.
3. Crea una conexion a tu servidor desde el panel de la extension.
4. Ejecuta los archivos en este orden:

| Orden | Archivo | Que hace |
| --- | --- | --- |
| 1 | `00_crear_tablas_sql_server.sql` | Crea la base `RetailPruebaTecnica`, tablas e indices. |
| 2 | `01_cargar_csv_sql_server.sql` | Carga los CSV de `data/raw` usando staging tables. |
| 3 | `02_validar_carga_sql_server.sql` | Valida conteos, fechas, diferencias y asignaciones A/B. |
| 4 | `03_bloque1_queries_sql_server.sql` | Ejecuta las seis queries avanzadas del Bloque 1 en T-SQL. |
| 5 | `04_consultas_dashboard_sql_server.sql` | Consultas usadas para explicar cada componente del dashboard. |
| 6 | `05_demo_en_vivo_milla_extra.sql` | Consultas cortas para ejecutar durante la entrevista sin esperar procesos pesados. |

## Punto importante sobre carga de CSV

`BULK INSERT` lee archivos desde la maquina donde corre SQL Server, no desde VS Code. Si el servidor no puede leer tu carpeta local:

- usa el asistente **Import Flat File** de la extension MSSQL si esta disponible en tu entorno;
- o copia los CSV a una ruta compartida/accesible para el servidor;
- o pide una base temporal y sube los CSV con la herramienta corporativa permitida.

## Como ejecutar una query en VS Code

1. Abre un archivo `.sql`.
2. Selecciona la conexion en la parte superior del editor.
3. Selecciona la base `RetailPruebaTecnica`.
4. Ejecuta todo el archivo o selecciona una consulta especifica.
5. Revisa los resultados en el panel inferior.

## Demo recomendada para entrevista

Si tienes poco tiempo, ejecuta solo:

1. `02_validar_carga_sql_server.sql`
2. `05_demo_en_vivo_milla_extra.sql`

Con eso muestras conteos, ventas netas, productividad, calidad del A/B test y una recomendacion priorizada.

## Equivalencia con BigQuery

El archivo `bloque1_queries.sql` conserva la version BigQuery Standard SQL pedida por la prueba. El archivo `03_bloque1_queries_sql_server.sql` es la version ejecutable en SQL Server.

Traducciones principales:

- `DATE_TRUNC(..., MONTH)` -> `DATEFROMPARTS(YEAR(fecha), MONTH(fecha), 1)`
- `DATE_DIFF(a, b, MONTH)` -> `DATEDIFF(MONTH, b, a)`
- `SAFE_DIVIDE(x, y)` -> `x / NULLIF(y, 0)`
- `LOGICAL_OR` -> `MAX(CASE WHEN condicion THEN 1 ELSE 0 END)`
"""
    (ROOT / "sql" / "README_SQL_SERVER.md").write_text(sqlserver_note, encoding="utf-8")


def main() -> None:
    VIZ.mkdir(exist_ok=True)
    PROCESSED.mkdir(exist_ok=True)
    dfs = load_data()
    write_audit(dfs)
    comp_store, comp_country = comparable_sales(dfs)
    prod = productivity(dfs)
    retention, ticket = cohorts(dfs)
    gmroi_df = gmroi(dfs)
    promo = promo_basket(dfs)
    weekly, cv = weekly_seasonality(dfs)
    pareto = pareto_categories(dfs)
    gaps = stock_gaps(dfs)
    ab = ab_test(dfs)

    write_summary_exports(comp_store, comp_country, prod, retention, ticket, gmroi_df, promo, weekly, pareto, gaps)
    create_visuals(weekly, pareto, retention, gaps, ab)
    write_sql_queries()
    write_model_docs()
    write_kpi_framework()
    write_analysis_html(comp_store, comp_country, prod, retention, ticket, gmroi_df, promo, weekly, cv, pareto, gaps, ab)
    write_dashboard(dfs, retention, prod, gaps)
    write_presentation(ab, comp_store, prod, gaps, gmroi_df, retention)
    write_readme(dfs)
    write_support_files()
    print("Entregables generados en", ROOT)


if __name__ == "__main__":
    main()

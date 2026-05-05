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
            "Para indicadores de ventas netas usar total_amount a nivel transaccion; para categoria/proveedor usar el monto calculado desde items y documentar la diferencia.",
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
            "Excluir transacciones con total_amount <= 0 de tickets promedio; marcar items con precio cero como alerta de precios/datos maestros.",
        ],
        [
            "Integridad referencial",
            "Llaves foraneas contra dimensiones",
            f"{(~tx['store_id'].isin(stores['store_id'])).sum():,} store_id invalidos; {(~items['item_id'].isin(products['item_id'])).sum():,} item_id invalidos; {len(missing_vendor_products):,} productos con vendor_id inexistente.",
            "Cinco productos apuntan a VND_031, que no existe en vendors.",
            "Mantener esos productos con proveedor 'SIN_VENDOR' en analisis de categoria y levantar incidente de datos maestros.",
        ],
        [
            "Frescura",
            "Ausencias diarias por tienda",
            f"{len(store_gaps):,} tiendas con ausencias de venta. Maximos: "
            + ", ".join(
                f"{r.store_id} {r.max_gap_days} dias"
                for r in store_gaps.sort_values("max_gap_days", ascending=False).head(3).itertuples()
            ),
            "TIENDA_037 tiene 135 dias sin venta antes de iniciar actividad; TIENDA_012 tiene 7 dias sin datos en septiembre 2024.",
            "Tratar TIENDA_037 como ausencia esperada por apertura; revisar TIENDA_012 como alerta operativa.",
        ],
        [
            "Integridad temporal",
            "Ventas antes de opening_date",
            f"{len(before_opening):,} transacciones, todas en TIENDA_037 entre {before_opening['transaction_date'].min().date()} y {before_opening['transaction_date'].max().date()}.",
            "La tienda tiene opening_date 2024-06-01 pero ventas desde 2024-05-15.",
            "No excluir del analisis historico, pero corregir opening_date o confirmar soft-opening.",
        ],
        [
            "Prueba A/B",
            "Tiendas en CONTROL y TREATMENT",
            f"{len(ab_variants):,} tiendas: " + ", ".join(ab_variants["store_id"].tolist()),
            "TIENDA_008 y TIENDA_037 aparecen asignadas a ambos grupos.",
            "Excluir estas tiendas de la prueba A/B primaria y reportarlas como falla de diseno experimental.",
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
        "- Ventas netas: `COMPLETED` suma positivo y `RETURNED` resta. Para la prueba A/B se usan solo transacciones completadas.",
        "- Los analisis por proveedor mantienen productos con vendor faltante como `SIN_VENDOR` cuando aplica.",
        "- Las tiendas con doble asignacion experimental se excluyen del resultado estadistico principal.",
        "- Las ausencias de venta son senales operativas, no prueba definitiva de quiebre: se priorizan por ventas estimadas perdidas y velocidad previa.",
    ]
    (ROOT / "bloque0_auditoria.md").write_text("\n".join(text) + "\n", encoding="utf-8")
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
    daily["transaction_date"] = daily["transaction_date"].dt.normalize()
    max_day = np.datetime64(completed["transaction_date"].max().normalize().date())
    rows = []
    for (store_id, item_id), group in daily.groupby(["store_id", "item_id"], sort=False):
        meta = group.iloc[0]
        date_days = group["transaction_date"].to_numpy(dtype="datetime64[D]")
        gmv_values = group["gmv"].to_numpy(dtype=float)

        def prior_14_day_average(gap_start_day: np.datetime64) -> float:
            window_start = gap_start_day - np.timedelta64(14, "D")
            left = np.searchsorted(date_days, window_start, side="left")
            right = np.searchsorted(date_days, gap_start_day, side="left")
            return float(gmv_values[left:right].sum() / 14)

        for previous_day, next_day in zip(date_days, date_days[1:]):
            gap_days = int((next_day - previous_day) / np.timedelta64(1, "D")) - 1
            if gap_days >= 3:
                gap_start_day = previous_day + np.timedelta64(1, "D")
                gap_end_day = next_day - np.timedelta64(1, "D")
                avg_daily = prior_14_day_average(gap_start_day)
                rows.append(
                    [
                        store_id,
                        item_id,
                        meta["item_name"],
                        meta["category"],
                        meta["vendor_id"],
                        meta["vendor_name"] if pd.notna(meta["vendor_name"]) else "SIN_VENDOR",
                        pd.Timestamp(gap_start_day),
                        pd.Timestamp(gap_end_day),
                        gap_days,
                        avg_daily,
                        avg_daily * gap_days,
                        False,
                    ]
                )
        active_gap = int((max_day - date_days[-1]) / np.timedelta64(1, "D"))
        if active_gap >= 3:
            gap_start_day = date_days[-1] + np.timedelta64(1, "D")
            avg_daily = prior_14_day_average(gap_start_day)
            rows.append(
                [
                    store_id,
                    item_id,
                    meta["item_name"],
                    meta["category"],
                    meta["vendor_id"],
                    meta["vendor_name"] if pd.notna(meta["vendor_name"]) else "SIN_VENDOR",
                    pd.Timestamp(gap_start_day),
                    pd.Timestamp(max_day),
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
        parts.append(f'<text x="{170+j*cell_w}" y="66" font-family="Arial" font-size="12" font-weight="700" fill="#344054">Mes {month}</text>')
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
-- Ventas netas: COMPLETED suma positivo y RETURNED resta.

-- Query 1: Ventas comparables
DECLARE current_start DATE DEFAULT DATE '2025-01-01';
DECLARE current_end DATE DEFAULT DATE '2025-06-30';
DECLARE previous_start DATE DEFAULT DATE_SUB(current_start, INTERVAL 1 YEAR);
DECLARE previous_end DATE DEFAULT DATE_SUB(current_end, INTERVAL 1 YEAR);

WITH transacciones_base AS (
  SELECT
    t.transaction_id,
    DATE(t.transaction_date) AS fecha_transaccion,
    t.store_id,
    CASE WHEN t.status = 'RETURNED' THEN -t.total_amount ELSE t.total_amount END AS ventas_netas
  FROM transactions t
),
tiendas_comparables AS (
  SELECT store_id, store_name, country, format
  FROM stores
  WHERE DATE(opening_date) <= previous_start
),
ventas AS (
  SELECT
    s.country,
    s.format,
    s.store_id,
    s.store_name,
    SUM(IF(t.fecha_transaccion BETWEEN current_start AND current_end, t.ventas_netas, 0)) AS ventas_netas_periodo_actual,
    SUM(IF(t.fecha_transaccion BETWEEN previous_start AND previous_end, t.ventas_netas, 0)) AS ventas_netas_periodo_anterior
  FROM transacciones_base t
  JOIN tiendas_comparables s USING (store_id)
  WHERE t.fecha_transaccion BETWEEN previous_start AND current_end
  GROUP BY 1, 2, 3, 4
)
SELECT
  country,
  format,
  store_id,
  store_name,
  ventas_netas_periodo_actual,
  ventas_netas_periodo_anterior,
  SAFE_DIVIDE(ventas_netas_periodo_actual, ventas_netas_periodo_anterior) - 1 AS crecimiento_ventas_comparables_pct,
  DENSE_RANK() OVER (
    PARTITION BY format
    ORDER BY SAFE_DIVIDE(ventas_netas_periodo_actual, ventas_netas_periodo_anterior) - 1 DESC
  ) AS ranking_crecimiento_tienda_formato
FROM ventas
WHERE ventas_netas_periodo_actual <> 0
  AND ventas_netas_periodo_anterior <> 0
ORDER BY format, ranking_crecimiento_tienda_formato;

-- Query 2: Productividad por metro cuadrado
WITH parametros AS (
  SELECT DATE '2025-04-01' AS fecha_inicio_trimestre, DATE '2025-06-30' AS fecha_fin_trimestre
),
ventas_tienda AS (
  SELECT
    s.store_id,
    s.store_name,
    s.country,
    s.format,
    s.region,
    s.size_sqm,
    SUM(CASE WHEN t.status = 'RETURNED' THEN -t.total_amount ELSE t.total_amount END) AS ventas_netas,
    COUNT(DISTINCT t.transaction_id) AS transacciones
  FROM transactions t
  JOIN stores s USING (store_id)
  CROSS JOIN parametros p
  WHERE DATE(t.transaction_date) BETWEEN p.fecha_inicio_trimestre AND p.fecha_fin_trimestre
  GROUP BY 1, 2, 3, 4, 5, 6
),
tiendas_calculadas AS (
  SELECT
    *,
    SAFE_DIVIDE(ventas_netas, size_sqm) AS ventas_netas_por_metro_cuadrado,
    SAFE_DIVIDE(transacciones, size_sqm) AS transacciones_por_metro_cuadrado,
    SAFE_DIVIDE(ventas_netas, transacciones) AS ticket_promedio,
    PERCENTILE_CONT(SAFE_DIVIDE(ventas_netas, size_sqm), 0.25) OVER (PARTITION BY format) AS percentil_25_ventas_por_metro_cuadrado
  FROM ventas_tienda
)
SELECT
  *,
  DENSE_RANK() OVER (PARTITION BY format ORDER BY ventas_netas_por_metro_cuadrado DESC) AS ranking_en_formato,
  IF(ventas_netas_por_metro_cuadrado < percentil_25_ventas_por_metro_cuadrado, 'BAJO_RENDIMIENTO', 'OK') AS alerta_rendimiento
FROM tiendas_calculadas
ORDER BY format, ranking_en_formato;

-- Query 3: Cohortes de clientes con tarjeta de lealtad
WITH transacciones_lealtad AS (
  SELECT
    customer_id,
    transaction_id,
    DATE_TRUNC(DATE(transaction_date), MONTH) AS mes_compra,
    total_amount
  FROM transactions
  WHERE loyalty_card = TRUE
    AND customer_id IS NOT NULL
    AND status = 'COMPLETED'
),
primera_compra AS (
  SELECT customer_id, MIN(mes_compra) AS mes_cohorte
  FROM transacciones_lealtad
  GROUP BY 1
),
actividad AS (
  SELECT
    p.mes_cohorte,
    DATE_DIFF(t.mes_compra, p.mes_cohorte, MONTH) AS mes_relativo,
    t.customer_id,
    t.total_amount
  FROM transacciones_lealtad t
  JOIN primera_compra p USING (customer_id)
),
tamano_cohorte AS (
  SELECT mes_cohorte, COUNT(DISTINCT customer_id) AS clientes_cohorte
  FROM primera_compra
  GROUP BY 1
),
metricas AS (
  SELECT
    a.mes_cohorte,
    a.mes_relativo,
    COUNT(DISTINCT a.customer_id) AS clientes_activos,
    AVG(a.total_amount) AS ticket_promedio,
    ANY_VALUE(tc.clientes_cohorte) AS clientes_cohorte,
    SAFE_DIVIDE(COUNT(DISTINCT a.customer_id), ANY_VALUE(tc.clientes_cohorte)) AS tasa_retencion
  FROM actividad a
  JOIN tamano_cohorte tc USING (mes_cohorte)
  WHERE mes_relativo IN (0, 1, 2, 3, 6)
  GROUP BY 1, 2
)
SELECT
  mes_cohorte,
  MAX(clientes_cohorte) AS clientes_cohorte,
  MAX(IF(mes_relativo = 0, tasa_retencion, NULL)) AS retencion_mes_0,
  MAX(IF(mes_relativo = 1, tasa_retencion, NULL)) AS retencion_mes_1,
  MAX(IF(mes_relativo = 2, tasa_retencion, NULL)) AS retencion_mes_2,
  MAX(IF(mes_relativo = 3, tasa_retencion, NULL)) AS retencion_mes_3,
  MAX(IF(mes_relativo = 6, tasa_retencion, NULL)) AS retencion_mes_6,
  MAX(IF(mes_relativo = 0, ticket_promedio, NULL)) AS ticket_promedio_mes_0,
  MAX(IF(mes_relativo = 1, ticket_promedio, NULL)) AS ticket_promedio_mes_1,
  MAX(IF(mes_relativo = 2, ticket_promedio, NULL)) AS ticket_promedio_mes_2,
  MAX(IF(mes_relativo = 3, ticket_promedio, NULL)) AS ticket_promedio_mes_3,
  MAX(IF(mes_relativo = 6, ticket_promedio, NULL)) AS ticket_promedio_mes_6,
  CASE
    WHEN MAX(IF(mes_relativo = 6, ticket_promedio, NULL)) > MAX(IF(mes_relativo = 0, ticket_promedio, NULL)) THEN 'CRECE'
    WHEN MAX(IF(mes_relativo = 6, ticket_promedio, NULL)) < MAX(IF(mes_relativo = 0, ticket_promedio, NULL)) THEN 'DECRECE'
    ELSE 'SIN_DATOS'
  END AS tendencia_ticket_mes_0_a_mes_6
FROM metricas
GROUP BY mes_cohorte
ORDER BY mes_cohorte;

-- Query 4: Retorno de margen bruto sobre inversion por proveedor y categoria
WITH ventas_item AS (
  SELECT
    p.vendor_id,
    COALESCE(v.vendor_name, 'SIN_VENDOR') AS vendor_name,
    p.category,
    ti.item_id,
    DATE(t.transaction_date) AS fecha_venta,
    ti.quantity,
    ti.quantity * ti.unit_price AS ventas_brutas_item,
    ti.quantity * p.cost AS costo_total
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
  SUM(ventas_brutas_item) AS ventas_brutas_items,
  SUM(costo_total) AS costo_total,
  SUM(ventas_brutas_item) - SUM(costo_total) AS margen_bruto,
  SAFE_DIVIDE(SUM(ventas_brutas_item) - SUM(costo_total), SUM(costo_total)) AS retorno_margen_bruto_sobre_costo,
  COUNT(DISTINCT item_id) AS items_activos,
  SAFE_DIVIDE(SUM(quantity), DATE_DIFF(MAX(fecha_venta), MIN(fecha_venta), DAY) + 1) AS velocidad_unidades_por_dia,
  IF(SAFE_DIVIDE(SUM(ventas_brutas_item) - SUM(costo_total), SUM(costo_total)) < 1, 'RETORNO_MARGEN_BAJO_1', 'OK') AS alerta_retorno_margen
FROM ventas_item
GROUP BY 1, 2, 3
ORDER BY retorno_margen_bruto_sobre_costo ASC;

-- Query 5: Deteccion de posibles quiebres de stock
WITH parametros AS (SELECT DATE '2025-06-30' AS fecha_maxima),
ventas_diarias AS (
  SELECT
    t.store_id,
    ti.item_id,
    DATE(t.transaction_date) AS fecha_venta,
    SUM(ti.quantity) AS unidades,
    SUM(ti.quantity * ti.unit_price) AS ventas_brutas
  FROM transaction_items ti
  JOIN transactions t USING (transaction_id)
  WHERE t.status = 'COMPLETED'
  GROUP BY 1, 2, 3
),
limites_tienda_item AS (
  SELECT store_id, item_id, MIN(fecha_venta) AS primera_fecha_venta, (SELECT fecha_maxima FROM parametros) AS fecha_maxima
  FROM ventas_diarias
  GROUP BY 1, 2
),
calendario AS (
  SELECT l.store_id, l.item_id, dia AS fecha_calendario
  FROM limites_tienda_item l, UNNEST(GENERATE_DATE_ARRAY(l.primera_fecha_venta, l.fecha_maxima)) AS dia
),
dias_sin_venta AS (
  SELECT
    c.store_id,
    c.item_id,
    c.fecha_calendario,
    DATE_SUB(c.fecha_calendario, INTERVAL ROW_NUMBER() OVER (PARTITION BY c.store_id, c.item_id ORDER BY c.fecha_calendario) DAY) AS clave_grupo
  FROM calendario c
  LEFT JOIN ventas_diarias v
    ON v.store_id = c.store_id
   AND v.item_id = c.item_id
   AND v.fecha_venta = c.fecha_calendario
  WHERE v.fecha_venta IS NULL
),
ausencias AS (
  SELECT
    store_id,
    item_id,
    MIN(fecha_calendario) AS fecha_inicio_ausencia,
    MAX(fecha_calendario) AS fecha_fin_ausencia,
    COUNT(*) AS dias_sin_venta
  FROM dias_sin_venta
  GROUP BY 1, 2, clave_grupo
  HAVING COUNT(*) >= 3
),
ausencias_priorizadas AS (
  SELECT
    a.*,
    SAFE_DIVIDE((
      SELECT SUM(v.ventas_brutas)
      FROM ventas_diarias v
      WHERE v.store_id = a.store_id
        AND v.item_id = a.item_id
        AND v.fecha_venta BETWEEN DATE_SUB(a.fecha_inicio_ausencia, INTERVAL 14 DAY) AND DATE_SUB(a.fecha_inicio_ausencia, INTERVAL 1 DAY)
    ), 14) AS venta_diaria_promedio_previa
  FROM ausencias a
)
SELECT
  a.store_id,
  s.store_name,
  a.item_id,
  p.item_name,
  p.category,
  COALESCE(v.vendor_name, 'SIN_VENDOR') AS vendor_name,
  a.fecha_inicio_ausencia,
  a.fecha_fin_ausencia,
  a.dias_sin_venta,
  a.venta_diaria_promedio_previa,
  a.venta_diaria_promedio_previa * a.dias_sin_venta AS venta_estimada_perdida
FROM ausencias_priorizadas a
JOIN stores s USING (store_id)
JOIN products p USING (item_id)
LEFT JOIN vendors v USING (vendor_id)
ORDER BY venta_estimada_perdida DESC;

-- Query 6: Impacto de promociones en ticket y volumen
WITH transaccion_categoria AS (
  SELECT
    t.transaction_id,
    p.category,
    LOGICAL_OR(ti.was_on_promo) AS tiene_item_en_promocion,
    SUM(ti.quantity) AS unidades_categoria,
    SUM(ti.quantity * ti.unit_price) AS ventas_categoria,
    ANY_VALUE(t.total_amount) AS ticket_transaccion
  FROM transactions t
  JOIN transaction_items ti USING (transaction_id)
  JOIN products p USING (item_id)
  WHERE t.status = 'COMPLETED'
  GROUP BY 1, 2
),
agregado AS (
  SELECT
    category,
    tiene_item_en_promocion,
    COUNT(DISTINCT transaction_id) AS transacciones,
    AVG(ticket_transaccion) AS ticket_promedio,
    AVG(unidades_categoria) AS unidades_promedio,
    AVG(ventas_categoria) AS ventas_promedio_categoria
  FROM transaccion_categoria
  GROUP BY 1, 2
)
SELECT
  category,
  MAX(IF(tiene_item_en_promocion, transacciones, NULL)) AS transacciones_con_promocion,
  MAX(IF(NOT tiene_item_en_promocion, transacciones, NULL)) AS transacciones_sin_promocion,
  MAX(IF(tiene_item_en_promocion, ticket_promedio, NULL)) AS ticket_promedio_con_promocion,
  MAX(IF(NOT tiene_item_en_promocion, ticket_promedio, NULL)) AS ticket_promedio_sin_promocion,
  MAX(IF(tiene_item_en_promocion, ticket_promedio, NULL)) - MAX(IF(NOT tiene_item_en_promocion, ticket_promedio, NULL)) AS diferencia_ticket_promedio,
  MAX(IF(tiene_item_en_promocion, unidades_promedio, NULL)) AS unidades_promedio_con_promocion,
  MAX(IF(NOT tiene_item_en_promocion, unidades_promedio, NULL)) AS unidades_promedio_sin_promocion,
  MAX(IF(tiene_item_en_promocion, unidades_promedio, NULL)) - MAX(IF(NOT tiene_item_en_promocion, unidades_promedio, NULL)) AS diferencia_unidades_promedio,
  MAX(IF(tiene_item_en_promocion, ventas_promedio_categoria, NULL)) - MAX(IF(NOT tiene_item_en_promocion, ventas_promedio_categoria, NULL)) AS diferencia_ventas_categoria_promedio,
  CASE
    WHEN MAX(IF(tiene_item_en_promocion, unidades_promedio, NULL)) > MAX(IF(NOT tiene_item_en_promocion, unidades_promedio, NULL))
     AND MAX(IF(tiene_item_en_promocion, ticket_promedio, NULL)) >= MAX(IF(NOT tiene_item_en_promocion, ticket_promedio, NULL))
    THEN 'UPLIFT_REAL'
    WHEN MAX(IF(tiene_item_en_promocion, unidades_promedio, NULL)) > MAX(IF(NOT tiene_item_en_promocion, unidades_promedio, NULL))
    THEN 'MAS_UNIDADES_CON_MENOR_TICKET'
    ELSE 'SIN_UPLIFT_CLARO'
  END AS lectura_promocion
FROM agregado
GROUP BY category
ORDER BY category;
"""
    (ROOT / "bloque1_queries.sql").write_text(sql, encoding="utf-8")


def write_model_docs() -> None:
    md = """# Bloque 2 - Modelo dimensional, pipeline y gobernanza

## A. Star schema propuesto para BigQuery

Grano principal: una fila por item vendido dentro de una transaccion (`fact_sales_item`). Este grano soporta retorno de margen bruto sobre inversion, promociones, categorias, proveedores y composicion del basket. Para indicadores de tienda se agrega a `fact_store_day` como tabla derivada/materializada.

### Hechos

| Tabla | Grano | Campos clave |
| --- | --- | --- |
| `fact_sales_item` | Item por transaccion | transaction_item_id, transaction_id, date_key, store_key, product_key, customer_key nullable, promotion_key nullable, quantity, unit_price, ventas_brutas_item, ventas_netas_item, costo_unitario, margen_bruto |
| `fact_transaction` | Transaccion | transaction_id, date_key, store_key, customer_key nullable, payment_method, status, total_amount, ventas_netas, loyalty_card |
| `fact_store_day` | Tienda-dia | date_key, store_key, ventas_netas, transacciones, ticket_promedio, ventas_netas_por_metro_cuadrado, monto_devoluciones |
| `fact_stock_gap` | Ausencia tienda-producto | store_key, product_key, fecha_inicio_ausencia, fecha_fin_ausencia, dias_sin_venta, venta_diaria_promedio_previa, venta_estimada_perdida |
| `fact_cohort_month` | Cohorte-mes | cohort_month_key, mes_relativo, clientes_activos, tasa_retencion, ticket_promedio |

### Dimensiones

| Tabla | Campos |
| --- | --- |
| `dim_date` | date_key, fecha, inicio_semana, mes, trimestre, anio, semana_fiscal |
| `dim_store` | store_key, store_id, store_name, country, city, format, size_sqm, opening_date, region |
| `dim_product` | product_key, item_id, item_name, brand, vendor_key, category, department, cost |
| `dim_vendor` | vendor_key, vendor_id, vendor_name, country, tier, is_shared_catalog |
| `dim_customer` | customer_key, customer_hash, segmento_lealtad, mes_primera_compra. Para compradores anonimos usar customer_key = -1 |
| `dim_promotion` | promotion_key, promo_name, variant, start_date, end_date, promo_type |

## Decisiones de diseno

1. `customer_id` nulo se modela como comprador anonimo. El 59.8% de transacciones no tiene cliente identificado; forzar un customer_id falso inflaria retencion. Para cohortes solo se usa `loyalty_card = TRUE`.
2. Se separa `fact_sales_item` de `fact_transaction`. La auditoria muestra 1,745 diferencias entre total de transaccion y suma de items; tienda y ticket deben usar el total reportado, mientras categoria/proveedor necesita el item.
3. `fact_store_day` es una tabla derivada. Las ventas comparables, productividad y dashboard diario necesitan respuestas rapidas por tienda/dia sin recalcular 542k lineas cada vez.
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
- Si dos reportes muestran ventas netas distintas, primero se revisa la definicion certificada de ventas netas, luego filtros de status/returns, granularidad item vs transaccion, timezone y fecha de actualizacion. La resolucion se documenta en un changelog de metricas.
"""
    (ROOT / "bloque2_decisiones.md").write_text(md, encoding="utf-8")
    (ROOT / "bloque2_modelo.mmd").write_text(
        """erDiagram
  fact_sales_item {
    string transaction_item_id
    string transaction_id
    string store_key
    string product_key
    string customer_key_nullable
    string promotion_key_nullable
    integer quantity
    float ventas_netas_item
    float costo_unitario
    float margen_bruto
  }

  fact_transaction {
    string transaction_id
    string store_key
    string customer_key_nullable
    string payment_method
    string status
    float total_amount
    float ventas_netas
    boolean loyalty_card
  }

  fact_store_day {
    string date_key
    string store_key
    float ventas_netas
    integer transacciones
    float ticket_promedio
    float ventas_netas_por_metro_cuadrado
  }

  fact_stock_gap {
    string store_key
    string product_key
    date fecha_inicio_ausencia
    date fecha_fin_ausencia
    integer dias_sin_venta
    float venta_diaria_promedio_previa
    float venta_estimada_perdida
  }

  fact_cohort_month {
    string cohort_month_key
    integer mes_relativo
    integer clientes_activos
    float tasa_retencion
    float ticket_promedio
  }

  dim_date {
    string date_key
    date fecha
    date inicio_semana
    integer mes
    integer trimestre
    integer anio
  }

  dim_store {
    string store_key
    string store_id
    string store_name
    string country
    string format
    integer size_sqm
    string region
  }

  dim_product {
    string product_key
    string item_id
    string item_name
    string brand
    string vendor_key
    string category
    float cost
  }

  dim_vendor {
    string vendor_key
    string vendor_id
    string vendor_name
    string country
    string tier
  }

  dim_customer {
    string customer_key
    string customer_hash
    string segmento_lealtad
    date mes_primera_compra
  }

  dim_promotion {
    string promotion_key
    string promo_name
    string variant
    date start_date
    date end_date
    string promo_type
  }

  dim_date ||--o{ fact_sales_item : date_key
  dim_store ||--o{ fact_sales_item : store_key
  dim_product ||--o{ fact_sales_item : product_key
  dim_vendor ||--o{ dim_product : vendor_key
  dim_customer ||--o{ fact_sales_item : customer_key
  dim_promotion ||--o{ fact_sales_item : promotion_key
  dim_store ||--o{ fact_transaction : store_key
  dim_customer ||--o{ fact_transaction : customer_key
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
    c.drawString(0.55 * inch, h - 0.55 * inch, "Modelo estrella - Retail multiformato")
    c.setFont("Helvetica", 10)
    c.drawString(0.55 * inch, h - 0.78 * inch, "Grano principal: item vendido por transaccion. Tablas derivadas para dashboard, cohortes y ausencias de venta.")

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
            "fact_sales_item": "cantidad, precio, ventas netas, costo, margen",
            "fact_store_day": "ventas netas, transacciones, ticket, ventas por metro cuadrado",
            "fact_stock_gap": "dias sin venta, promedio previo, perdida estimada",
            "fact_cohort_month": "mes relativo, clientes activos, retencion, ticket",
            "dim_store": "pais, formato, region, metros cuadrados",
            "dim_product": "categoria, departamento, costo",
            "dim_vendor": "nivel, pais, catalogo compartido",
            "dim_customer": "cliente protegido, segmento, primera compra",
            "dim_promotion": "variante, fechas, tipo",
            "dim_date": "semana, mes, trimestre, anio",
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
        ["Ticket promedio neto", "Venta neta por transaccion", "Ventas netas / transacciones", "Diario", "fact_transaction", "+3% contra el mismo periodo del ano anterior", "Total <=0 o transacciones duplicadas"],
        ["Conversion de lealtad", "Participacion de tickets identificados", "Transacciones con loyalty_card / transacciones totales", "Semanal", "fact_transaction", "45% en 6 meses", "customer_id nulo con loyalty_card TRUE"],
        ["Retencion mes 1", "Clientes de cohorte que vuelven al mes 1", "Clientes activos en mes 1 / tamano cohorte", "Mensual", "fact_cohort_month", ">=70%", "Cohorte sin customer_hash o month_n negativo"],
        ["Indice de quiebre", "Ventas estimadas perdidas por falta de venta", "Ventas estimadas perdidas / ventas netas", "Diario", "fact_stock_gap + fact_store_day", "<2% de ventas netas", "Gap en producto sin ventas historicas"],
        ["Retorno de margen bruto sobre inversion", "Retorno de margen sobre costo", "(Ventas - costo) / costo", "Mensual", "fact_sales_item + dim_product", ">1.5 por proveedor-categoria", "Costo nulo/cero o proveedor inexistente"],
        ["Indice estimado de disponibilidad", "Indicador anticipado de abastecimiento", "1 - items activos con ausencia de venta 3+ dias / items activos", "Diario", "fact_stock_gap", ">=97%", "Item marcado activo sin ventas ultimos 180 dias"],
        ["Puntaje de salud de productividad", "Indicador compuesto de productividad", "0.4 ventas netas por metro cuadrado + 0.25 transacciones por metro cuadrado + 0.2 ticket + 0.15 disponibilidad normalizados", "Semanal", "Marts certificados", ">=75/100", "Alguna metrica base faltante o fuera de rango"],
    ]
    text = [
        "# Bloque 4 - Framework de indicadores para productividad de tiendas",
        "",
        markdown_table(
            rows,
            [
                "Indicador",
                "Definicion exacta",
                "Formula",
                "Frecuencia",
                "Fuente de datos",
                "Objetivo sugerido",
                "Como detectas si el dato esta mal",
            ],
        ),
        "",
        "## Metrica principal",
        "",
        "**Puntaje de salud de productividad** es la metrica principal del programa. Combina resultado financiero (ventas netas por metro cuadrado), actividad operativa (transacciones por metro cuadrado), experiencia/comportamiento de cliente (ticket y retencion via componentes) y disponibilidad estimada. Es mejor que usar solo ventas porque evita premiar tiendas grandes que venden mucho pero son ineficientes o tienen problemas de stock.",
        "",
        "## Indicador anticipado",
        "",
        "El **indice estimado de disponibilidad** funciona como indicador predictivo: si empiezan ausencias de venta en productos activos, las ventas netas futuras probablemente caeran antes de que el cierre mensual lo muestre.",
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
    ttest_tx = ab["ttest_tx"]
    ttest_ticket = ab["ttest_ticket"]
    change = ab["ttest_change"]
    week_table_cols = ["week_start", "format", "net_gmv", "wow_abs", "wow_pct"]
    week_table_names = {
        "week_start": "semana",
        "format": "formato",
        "net_gmv": "ventas_netas",
        "wow_abs": "cambio_semana_anterior",
        "wow_pct": "cambio_porcentual",
    }

    def weekly_table(df: pd.DataFrame) -> str:
        out = df[week_table_cols].copy()
        out[["net_gmv", "wow_abs", "wow_pct"]] = out[["net_gmv", "wow_abs", "wow_pct"]].round(2)
        return out.rename(columns=week_table_names).to_html(index=False)

    top_peaks_table = weekly_table(top_peaks)
    top_drops_table = weekly_table(top_drops)

    sections = f"""
<!doctype html>
<html lang="es">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Bloque 3 - Analisis Exploratorio y Prueba A/B</title>
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
  {top_peaks_table}
  <p><b>Caidas mas significativas:</b></p>
  {top_drops_table}
  <p><b>Hipotesis de picos:</b> 2024-12-02 en HIPERMERCADO se asocia a temporada navidena y compras de alto valor; 2024-07-01 en SUPERMERCADO puede venir de pago de medio ano y abastecimiento de inicio de semestre; 2025-05-05 en SUPERMERCADO coincide con una semana comercial fuerte previa a Dia de la Madre en la region.</p>
  <p><b>Hipotesis de caidas:</b> 2024-12-30 cae por compras adelantadas de Navidad y menor trafico posterior; la caida de HIPERMERCADO en esa misma semana sugiere normalizacion despues de promociones; 2024-07-29 en HIPERMERCADO parece cierre de ciclo despues del pico de julio.</p>

  <h3>2. Pareto de categorias por formato</h3>
  <img src="bloque3_visualizaciones/pareto_categorias_gmv.svg" alt="Pareto de categorias">
  <p>En todos los formatos, Electronica y Hogar explican alrededor de 76% de las ventas netas. El patron de HIPERMERCADO y DESCUENTO es muy parecido: no cambia tanto la mezcla lider, sino la productividad y escala por tienda. Esto sugiere que el comprador de descuento tambien esta usando el formato para compras de alto valor.</p>
  {pareto.sort_values(['format','cum_share']).groupby('format').head(3)[['format','category','share','cum_share']].assign(share=lambda d: (d['share']*100).round(1), cum_share=lambda d: (d['cum_share']*100).round(1)).rename(columns={'format': 'formato', 'category': 'categoria', 'share': 'participacion_pct', 'cum_share': 'participacion_acumulada_pct'}).to_html(index=False)}

  <h3>3. Cohortes de lealtad</h3>
  <img src="bloque3_visualizaciones/cohortes_retencion.svg" alt="Heatmap de cohortes">
  <p>Las cohortes recientes de abril-junio 2024 retienen mejor en el mes 1 ({recent:.1f}%) que las cohortes enero-marzo ({old:.1f}%), aunque las cohortes recientes son pequenas. La mayor caida promedio ocurre del mes 0 al mes 1; despues hay recuperaciones, lo que apunta a compras recurrentes no necesariamente mensuales.</p>

  <h3>4. Quiebres de stock e impacto</h3>
  <img src="bloque3_visualizaciones/stockouts_gmv_perdido_categoria.svg" alt="Ventas estimadas perdidas por quiebres">
  <p>Se detectaron {len(gaps):,} ausencias de venta de 3+ dias. No todas son quiebres reales, pero priorizadas por ventas estimadas perdidas apuntan a Electronica como el mayor riesgo: {money(category_loss.iloc[0])}. Por la concentracion en productos con venta historica, lo interpreto principalmente como riesgo de abastecimiento/disponibilidad, no como falta de demanda. Proveedores con mayor impacto estimado:</p>
  {vendor_loss.reset_index().assign(estimated_lost_gmv=lambda d: d['estimated_lost_gmv'].map(money)).rename(columns={'vendor_id': 'proveedor_id', 'vendor_name': 'proveedor', 'estimated_lost_gmv': 'ventas_estimadas_perdidas'}).to_html(index=False)}

  <h3>5. Hallazgo libre</h3>
  <div class="callout">Electronica representa {electronics_share:.1f}% de las ventas totales aunque son 20 de 200 productos. Esto crea una concentracion fuerte: cualquier quiebre o error de precio en pocos productos mueve el resultado regional. La recomendacion es crear monitoreo diario de disponibilidad para los 20 productos de Electronica antes de expandirlo a todo el catalogo.</div>

  <h2>Parte B - Interpretacion de Prueba A/B</h2>
  <img src="bloque3_visualizaciones/ab_test_gmv_promedio.svg" alt="Prueba A/B de ventas promedio">
  <p>Validacion: hay dos tiendas asignadas a ambos grupos ({', '.join(ab['ambiguous'])}), excluidas de la prueba primaria. Los grupos limpios no son perfectamente comparables: CONTROL tenia ventas semanales base de {money2(ab['pre_summary'].loc['CONTROL', 'avg_weekly_gmv'])} contra {money2(ab['pre_summary'].loc['TREATMENT', 'avg_weekly_gmv'])} en TREATMENT, tamano promedio de {ab['size_summary'].loc['CONTROL', 'mean']:,.1f} vs {ab['size_summary'].loc['TREATMENT', 'mean']:,.1f} metros cuadrados, y mas hipermercados/supermercados.</p>
  <p>Resultado principal de ventas semanales promedio por tienda: diferencia TREATMENT - CONTROL = <b>{money2(ttest['diff'])}</b>, incremento relativo {ttest['lift_pct']:.1f}%, valor p {ttest['p_value']:.3f}, IC95% [{money2(ttest['ci_low'])}, {money2(ttest['ci_high'])}]. No es estadisticamente significativo y el signo es negativo en comparacion directa.</p>
  <p>Ticket y frecuencia: TREATMENT tuvo {ttest_tx['treatment_mean']:.1f} transacciones semanales promedio contra {ttest_tx['control_mean']:.1f} en CONTROL; diferencia {ttest_tx['diff']:.1f}, valor p {ttest_tx['p_value']:.3f}. El ticket promedio tambien fue menor: {money2(ttest_ticket['treatment_mean'])} contra {money2(ttest_ticket['control_mean'])}; diferencia {money2(ttest_ticket['diff'])}, valor p {ttest_ticket['p_value']:.3f}. Por eso el resultado directo no viene de tickets mas altos ni de mayor frecuencia.</p>
  <p>Sin embargo, contra su propia linea base, TREATMENT mejora mientras CONTROL cae: diferencia-en-diferencias aproximada = {money2(change['diff'])}, valor p {change['p_value']:.3f}. Esto sugiere que el diseno necesita una repeticion con balance por formato/tamano antes de escalar.</p>
  <p><b>Decision:</b> no implementaria la exhibicion en todas las tiendas todavia. Haria una segunda prueba estratificada por formato y tamano, con costo de implementacion medido. Si el valor p fuera 0.08 y el incremento relativo cubre el costo, lo trataria como senal prometedora para piloto ampliado, no como rollout total.</p>
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
    default_start = tx["transaction_date"].min().strftime("%Y-%m-%d")
    default_end = tx["transaction_date"].max().strftime("%Y-%m-%d")
    template = (ROOT / "templates" / "dashboard_operativo_regional.html").read_text(encoding="utf-8")
    html = (
        template.replace("__PAYLOAD__", json.dumps(payload, ensure_ascii=False))
        .replace("__DEFAULT_START__", default_start)
        .replace("__DEFAULT_END__", default_end)
    )
    (ROOT / "bloque5_dashboard.html").write_text(html.rstrip() + "\n", encoding="utf-8")
    return


def write_presentation(
    ab: dict[str, object],
    comp_store: pd.DataFrame,
    prod: pd.DataFrame,
    gaps: pd.DataFrame,
    gmroi_df: pd.DataFrame,
    retention: pd.DataFrame,
    pareto: pd.DataFrame,
) -> None:
    pdf = ROOT / "bloque5_presentacion_EN.pdf"
    c = canvas.Canvas(str(pdf), pagesize=landscape(letter))
    w, h = landscape(letter)

    best = comp_store.sort_values("growth_pct", ascending=False).iloc[0]
    worst = comp_store.sort_values("growth_pct").iloc[0]
    low_stores = int((prod["performance_flag"] == "BAJO_RENDIMIENTO").sum())
    lost_total = gaps["estimated_lost_gmv"].sum()
    low_gmroi = int((gmroi_df["gmroi"] < 1).sum())
    m1_large = retention.loc[retention.index <= pd.Timestamp("2024-03-01"), 1].dropna().mean()
    t = ab["ttest_gmv"]
    t_tx = ab["ttest_tx"]
    t_ticket = ab["ttest_ticket"]
    change = ab["ttest_change"]
    pre_summary = ab["pre_summary"]
    test_summary = ab["test_summary"]
    size_summary = ab["size_summary"]
    category_sales = pareto.groupby("category")["net_line_gmv"].sum().sort_values(ascending=False)
    electronics_share = category_sales.get("Electrónica", 0) / category_sales.sum() * 100
    category_loss = gaps.groupby("category")["estimated_lost_gmv"].sum().sort_values(ascending=False)
    active_gap_count = int(gaps["active_gap"].sum())
    low_by_format = prod[prod["performance_flag"] == "BAJO_RENDIMIENTO"].groupby("format").size().sort_values(ascending=False)
    worst_gmroi = gmroi_df.sort_values("gmroi").head(5)
    format_perf = (
        comp_store.groupby("format")[["current", "previous"]]
        .sum()
        .assign(growth=lambda d: (d["current"] / d["previous"] - 1) * 100)
        .sort_values("growth", ascending=False)
    )
    country_perf = (
        comp_store.groupby("country")[["current", "previous"]]
        .sum()
        .assign(growth=lambda d: (d["current"] / d["previous"] - 1) * 100)
        .sort_values("growth", ascending=False)
    )

    ink = colors.HexColor("#1f2933")
    muted = colors.HexColor("#667085")
    paper = colors.HexColor("#fbfaf7")
    line = colors.HexColor("#ded8cf")
    teal = colors.HexColor("#176B87")
    green = colors.HexColor("#3E8E7E")
    orange = colors.HexColor("#D97941")
    red = colors.HexColor("#C04B37")
    purple = colors.HexColor("#7B4B94")
    page_no = 0

    def draw_wrapped(text: str, x: float, y: float, max_width: float, size: float = 9.5, font: str = "Helvetica", color=ink, leading: float | None = None) -> float:
        c.setFont(font, size)
        c.setFillColor(color)
        leading = leading or size + 2.5
        words = str(text).split()
        lines: list[str] = []
        current: list[str] = []
        for word in words:
            candidate = " ".join(current + [word])
            if current and c.stringWidth(candidate, font, size) > max_width:
                lines.append(" ".join(current))
                current = [word]
            else:
                current.append(word)
        if current:
            lines.append(" ".join(current))
        for line in lines:
            c.drawString(x, y, line)
            y -= leading
        return y

    def start_slide(section: str, title: str, subtitle: str) -> None:
        nonlocal page_no
        page_no += 1
        c.setFillColor(paper)
        c.rect(0, 0, w, h, fill=1, stroke=0)
        c.setFillColor(teal)
        c.rect(0, h - 0.16 * inch, w, 0.16 * inch, fill=1, stroke=0)
        c.setFillColor(teal)
        c.rect(0, 0, 0.18 * inch, h, fill=1, stroke=0)
        c.setFillColor(ink)
        c.setFont("Helvetica-Bold", 10)
        c.drawString(0.55 * inch, h - 0.47 * inch, section.upper())
        title_bottom = draw_wrapped(title, 0.55 * inch, h - 0.82 * inch, 9.5 * inch, size=21, font="Helvetica-Bold", color=ink, leading=24)
        subtitle_y = min(h - 1.12 * inch, title_bottom - 0.03 * inch)
        subtitle_bottom = draw_wrapped(subtitle, 0.55 * inch, subtitle_y, 9.6 * inch, size=9.5, color=muted)
        c.setStrokeColor(line)
        rule_y = min(h - 1.32 * inch, subtitle_bottom - 0.04 * inch)
        c.line(0.55 * inch, rule_y, 10.45 * inch, rule_y)
        c.setFont("Helvetica", 7.5)
        c.setFillColor(muted)
        c.drawString(0.55 * inch, 0.28 * inch, "Retail Multi-format | Jan 2024 to Jun 2025 | Synthetic dataset")
        c.drawRightString(10.45 * inch, 0.28 * inch, f"{page_no}/5")

    def end_slide() -> None:
        c.showPage()

    def card(x: float, y: float, width: float, height: float, label: str, value: str, note: str, accent=teal) -> None:
        c.setFillColor(colors.white)
        c.setStrokeColor(line)
        c.roundRect(x, y, width, height, 7, fill=1, stroke=1)
        c.setFillColor(accent)
        c.roundRect(x, y + height - 0.08 * inch, width, 0.08 * inch, 4, fill=1, stroke=0)
        c.setFillColor(muted)
        c.setFont("Helvetica-Bold", 7.5)
        c.drawString(x + 0.12 * inch, y + height - 0.28 * inch, label.upper())
        c.setFillColor(ink)
        c.setFont("Helvetica-Bold", 17)
        c.drawString(x + 0.12 * inch, y + height - 0.58 * inch, value)
        draw_wrapped(note, x + 0.12 * inch, y + 0.22 * inch, width - 0.24 * inch, size=7.5, color=muted, leading=9)

    def panel(x: float, y: float, width: float, height: float, title: str, accent=teal) -> None:
        c.setFillColor(colors.white)
        c.setStrokeColor(line)
        c.roundRect(x, y, width, height, 8, fill=1, stroke=1)
        c.setFillColor(accent)
        c.roundRect(x, y + height - 0.11 * inch, width, 0.11 * inch, 5, fill=1, stroke=0)
        c.setFillColor(ink)
        c.setFont("Helvetica-Bold", 10)
        c.drawString(x + 0.16 * inch, y + height - 0.34 * inch, title)

    def bullet_list(items: list[str], x: float, y: float, width: float, color=orange, size: float = 9.4) -> float:
        for item in items:
            c.setFillColor(color)
            c.circle(x, y + 0.04 * inch, 2.3, fill=1, stroke=0)
            y = draw_wrapped(item, x + 0.12 * inch, y, width - 0.12 * inch, size=size, color=ink, leading=size + 3)
            y -= 0.07 * inch
        return y

    def hbar_chart(
        rows: list[tuple[str, float]],
        x: float,
        y: float,
        width: float,
        height: float,
        title: str,
        positive_negative: bool = False,
        value_formatter=money,
    ) -> None:
        panel(x, y, width, height, title, teal)
        plot_x = x + 0.22 * inch
        plot_y = y + height - 0.72 * inch
        plot_w = width - 0.45 * inch
        row_h = min(0.32 * inch, (height - 0.95 * inch) / max(len(rows), 1))
        values = [v for _, v in rows]
        if positive_negative:
            max_abs = max(max(abs(v) for v in values), 1)
            zero_x = plot_x + plot_w * 0.48
            c.setStrokeColor(line)
            c.line(zero_x, y + 0.28 * inch, zero_x, y + height - 0.78 * inch)
            scale = plot_w * 0.44 / max_abs
            for idx, (label, value) in enumerate(rows):
                yy = plot_y - idx * row_h
                bar_w = abs(value) * scale
                c.setFillColor(green if value >= 0 else red)
                c.rect(zero_x if value >= 0 else zero_x - bar_w, yy - 0.09 * inch, bar_w, 0.14 * inch, fill=1, stroke=0)
                c.setFillColor(ink)
                c.setFont("Helvetica-Bold", 7.5)
                c.drawRightString(zero_x - 0.08 * inch, yy - 0.04 * inch, label)
                c.drawString(zero_x + (bar_w if value >= 0 else -bar_w) + (0.05 * inch if value >= 0 else -0.36 * inch), yy - 0.04 * inch, f"{value:.1f}%")
        else:
            max_value = max(max(values), 1)
            for idx, (label, value) in enumerate(rows):
                yy = plot_y - idx * row_h
                c.setFillColor(muted)
                c.setFont("Helvetica-Bold", 7.5)
                c.drawString(plot_x, yy - 0.04 * inch, label)
                c.setFillColor(orange if idx == 0 else teal)
                c.rect(plot_x + 1.45 * inch, yy - 0.09 * inch, (plot_w - 2.0 * inch) * value / max_value, 0.14 * inch, fill=1, stroke=0)
                c.setFillColor(ink)
                c.drawRightString(plot_x + plot_w, yy - 0.04 * inch, value_formatter(value))

    def category_label(value: str) -> str:
        return {
            "Electrónica": "Electronics",
            "Hogar": "Home",
            "Ropa": "Apparel",
            "Alimentos": "Food",
            "Juguetes": "Toys",
            "Bebidas": "Beverages",
            "Cuidado Personal": "Personal Care",
            "Limpieza": "Cleaning",
        }.get(value, value)

    def simple_table(rows: list[list[str]], headers: list[str], x: float, y: float, width: float, row_h: float = 0.26 * inch, font_size: float = 7.6) -> None:
        col_w = width / len(headers)
        c.setFillColor(colors.HexColor("#f2efe8"))
        c.rect(x, y, width, row_h, fill=1, stroke=0)
        c.setFillColor(muted)
        c.setFont("Helvetica-Bold", font_size)
        for i, header in enumerate(headers):
            c.drawString(x + i * col_w + 0.05 * inch, y + 0.08 * inch, header)
        yy = y - row_h
        for r, row in enumerate(rows):
            c.setFillColor(colors.white if r % 2 == 0 else colors.HexColor("#fbfaf7"))
            c.rect(x, yy, width, row_h, fill=1, stroke=0)
            c.setFillColor(ink)
            c.setFont("Helvetica", font_size)
            for i, cell in enumerate(row):
                c.drawString(x + i * col_w + 0.05 * inch, yy + 0.08 * inch, str(cell)[:26])
            yy -= row_h

    start_slide(
        "1. Executive Summary",
        "The operating story is clear: fix availability and low-productivity stores first; do not scale the display test yet.",
        "Five metrics carry the decision. The test signal is not strong enough, while productivity and availability risks are already material.",
    )
    draw_wrapped(
        "Recommendation: pause full rollout, run a balanced second test, and launch daily operating controls for stock gaps and store productivity.",
        0.65 * inch,
        5.72 * inch,
        4.75 * inch,
        size=16,
        font="Helvetica-Bold",
        color=ink,
        leading=20,
    )
    bullet_list(
        [
            f"Electronics represents {electronics_share:.1f}% of net item sales, so small product issues move the full region.",
            f"Sales gap signals add up to {money(lost_total)} estimated lost sales; the top category is {category_label(category_loss.index[0])}.",
            f"A/B direct result is negative ({t['lift_pct']:.1f}% lift, p-value {t['p_value']:.3f}); design balance is weak.",
        ],
        0.72 * inch,
        4.45 * inch,
        4.5 * inch,
    )
    card(5.55 * inch, 4.68 * inch, 1.55 * inch, 1.0 * inch, "Net sales", money(category_sales.sum()), "Item-level sales used for category mix.", teal)
    card(7.25 * inch, 4.68 * inch, 1.55 * inch, 1.0 * inch, "Electronics", f"{electronics_share:.1f}%", "Share of net item sales.", orange)
    card(8.95 * inch, 4.68 * inch, 1.55 * inch, 1.0 * inch, "Lost sales", money(lost_total), "Estimated from sales gaps.", red)
    card(5.55 * inch, 3.28 * inch, 1.55 * inch, 1.0 * inch, "Low stores", str(low_stores), "Below 25th percentile.", purple)
    card(7.25 * inch, 3.28 * inch, 1.55 * inch, 1.0 * inch, "A/B p-value", f"{t['p_value']:.3f}", "Direct sales test.", red)
    card(8.95 * inch, 3.28 * inch, 1.55 * inch, 1.0 * inch, "Ambiguous", str(len(ab["ambiguous"])), "Stores in both variants.", orange)
    panel(5.55 * inch, 1.08 * inch, 4.95 * inch, 1.75 * inch, "Decision logic", green)
    bullet_list(
        [
            "Scale only after a clean experiment by format and store size.",
            "Use productivity alerts every week for the bottom 10 stores.",
            "Start daily stock-gap monitoring with the top 20 Electronics products.",
        ],
        5.78 * inch,
        2.35 * inch,
        4.5 * inch,
        color=green,
        size=8.6,
    )
    end_slide()

    start_slide(
        "2. Store Performance",
        "Comparable sales show where formats and stores are moving, but productivity varies sharply inside each format.",
        "The view below separates growth from efficiency so regional actions can be assigned by store.",
    )
    hbar_chart([(idx, row["growth"]) for idx, row in format_perf.iterrows()], 0.6 * inch, 3.65 * inch, 4.85 * inch, 2.4 * inch, "Comparable sales growth by format", True)
    hbar_chart([(idx, row["growth"]) for idx, row in country_perf.iterrows()], 0.6 * inch, 1.0 * inch, 4.85 * inch, 2.15 * inch, "Comparable sales growth by country", True)
    top_rows = [
        [r.store_id, r.format, f"{r.growth_pct:.1f}%", money(r.current)]
        for r in comp_store.sort_values("growth_pct", ascending=False).head(4).itertuples()
    ]
    bottom_rows = [
        [r.store_id, r.format, f"{r.growth_pct:.1f}%", money(r.current)]
        for r in comp_store.sort_values("growth_pct").head(4).itertuples()
    ]
    panel(5.75 * inch, 3.65 * inch, 4.75 * inch, 2.4 * inch, "Best comparable stores", green)
    simple_table(top_rows, ["Store", "Format", "Growth", "Current"], 5.92 * inch, 5.3 * inch, 4.4 * inch)
    panel(5.75 * inch, 1.0 * inch, 4.75 * inch, 2.15 * inch, "Worst comparable stores", red)
    simple_table(bottom_rows, ["Store", "Format", "Growth", "Current"], 5.92 * inch, 2.55 * inch, 4.4 * inch)
    end_slide()

    start_slide(
        "3. Opportunities",
        "The improvement pool is practical: ten low-productivity stores, low margin-return vendors, and loyalty retention after first purchase.",
        "These actions can start without waiting for a new platform or extra tooling.",
    )
    card(0.65 * inch, 4.85 * inch, 2.15 * inch, 0.95 * inch, "Productivity", f"{low_stores} stores", "Below 25th percentile inside format.", teal)
    card(3.0 * inch, 4.85 * inch, 2.15 * inch, 0.95 * inch, "Margin return", str(low_gmroi), "Vendor-category combos below 1.", red)
    card(5.35 * inch, 4.85 * inch, 2.15 * inch, 0.95 * inch, "Month 1 retention", f"{m1_large:.1f}%", "Large early loyalty cohorts.", purple)
    card(7.7 * inch, 4.85 * inch, 2.15 * inch, 0.95 * inch, "Active gaps", f"{active_gap_count:,}", "Open store-product signals.", orange)
    hbar_chart(
        [(idx, float(v)) for idx, v in low_by_format.items()],
        0.65 * inch,
        2.0 * inch,
        4.55 * inch,
        2.35 * inch,
        "Low-productivity stores by format",
        value_formatter=lambda value: f"{int(value)}",
    )
    panel(5.55 * inch, 2.0 * inch, 4.95 * inch, 2.35 * inch, "Lowest margin-return vendor/category pairs", red)
    gmroi_rows = [
        [r.vendor_id, category_label(r.category), f"{r.gmroi:.2f}", money(r.gross_margin)]
        for r in worst_gmroi.itertuples()
    ]
    simple_table(gmroi_rows, ["Vendor", "Category", "Return", "Margin"], 5.72 * inch, 3.65 * inch, 4.6 * inch, row_h=0.24 * inch)
    panel(0.65 * inch, 0.82 * inch, 9.85 * inch, 0.75 * inch, "Management implication", green)
    draw_wrapped(
        "Weekly productivity routines should start with the bottom 10 stores; vendor reviews should focus on return below 1; loyalty should trigger a second purchase before month one drops.",
        0.85 * inch,
        1.15 * inch,
        9.35 * inch,
        size=8.8,
        color=ink,
    )
    end_slide()

    start_slide(
        "4. Risks",
        "The analysis is usable, but the business should act with clear risk controls: data quality, experiment balance, and stock-gap interpretation.",
        "Each risk has a measurable control that can be checked before a VP-level rollout decision.",
    )
    card(0.65 * inch, 4.92 * inch, 1.85 * inch, 0.88 * inch, "Data mismatch", "1,745", "Transactions differ from item totals.", orange)
    card(2.7 * inch, 4.92 * inch, 1.85 * inch, 0.88 * inch, "Missing vendor", "5", "Products point to unknown vendor.", red)
    card(4.75 * inch, 4.92 * inch, 1.85 * inch, 0.88 * inch, "A/B conflict", "2", "Stores in both variants.", red)
    card(6.8 * inch, 4.92 * inch, 1.85 * inch, 0.88 * inch, "Price issue", "231", "Items at zero price without promo.", purple)
    hbar_chart([(category_label(idx), float(v)) for idx, v in category_loss.head(5).items()], 0.65 * inch, 1.2 * inch, 4.95 * inch, 3.2 * inch, "Estimated lost sales by category")
    panel(5.85 * inch, 1.2 * inch, 4.65 * inch, 3.2 * inch, "Experiment balance check", red)
    exp_rows = [
        ["Pre sales", money2(pre_summary.loc["CONTROL", "avg_weekly_gmv"]), money2(pre_summary.loc["TREATMENT", "avg_weekly_gmv"])],
        ["Test sales", money2(test_summary.loc["CONTROL", "avg_weekly_gmv"]), money2(test_summary.loc["TREATMENT", "avg_weekly_gmv"])],
        ["Transactions", f"{test_summary.loc['CONTROL', 'avg_weekly_tx']:.1f}", f"{test_summary.loc['TREATMENT', 'avg_weekly_tx']:.1f}"],
        ["Ticket", money2(test_summary.loc["CONTROL", "avg_ticket"]), money2(test_summary.loc["TREATMENT", "avg_ticket"])],
        ["Store size", f"{size_summary.loc['CONTROL', 'mean']:.0f}", f"{size_summary.loc['TREATMENT', 'mean']:.0f}"],
    ]
    simple_table(exp_rows, ["Metric", "Control", "Treatment"], 6.03 * inch, 3.82 * inch, 4.3 * inch, row_h=0.28 * inch)
    draw_wrapped(
        f"Direct sales difference is {money2(t['diff'])}, p-value {t['p_value']:.3f}. Difference-in-differences is {money2(change['diff'])}, p-value {change['p_value']:.3f}, so I would repeat the test with a balanced design.",
        6.05 * inch,
        1.78 * inch,
        4.25 * inch,
        size=8.2,
        color=ink,
    )
    end_slide()

    start_slide(
        "5. Recommendations",
        "The next plan is a controlled operating rollout, not a dashboard-only handoff.",
        "Each action includes owner, timing, and the number that proves whether it worked.",
    )
    timeline = [
        (
            "30 days",
            orange,
            [
                "Operations: action plan for the bottom 10 productivity stores.",
                "Supply Chain: daily alert for top 20 Electronics products.",
                "Data: fix 5 missing vendor links and zero-price exceptions.",
            ],
        ),
        (
            "60 days",
            teal,
            [
                "Merchandising: repeat A/B test by format and store size.",
                "Target: p-value below 0.05 or positive profit after implementation cost.",
                "Add inventory data to confirm real stock-outs.",
            ],
        ),
        (
            "90 days",
            green,
            [
                "Regional Operations: certify productivity score every week.",
                "Data team: publish metric owner and reconciliation rules.",
                "VP review: scale only stores/categories that clear the decision gate.",
            ],
        ),
    ]
    x = 0.65 * inch
    for label, accent, items in timeline:
        panel(x, 1.55 * inch, 3.05 * inch, 4.5 * inch, label, accent)
        bullet_list(items, x + 0.22 * inch, 5.18 * inch, 2.6 * inch, color=accent, size=8.6)
        x += 3.32 * inch
    c.setFillColor(colors.white)
    c.setStrokeColor(line)
    c.roundRect(0.65 * inch, 0.7 * inch, 9.7 * inch, 0.55 * inch, 8, fill=1, stroke=1)
    draw_wrapped(
        f"Final call: do not scale the display now. Run the balanced test, reduce the {money(lost_total)} sales-gap risk, and move the bottom {low_stores} stores above their format threshold.",
        0.85 * inch,
        1.02 * inch,
        9.25 * inch,
        size=9.2,
        font="Helvetica-Bold",
        color=ink,
    )
    end_slide()
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
| Datos | {len(tx):,} transacciones, {len(dfs['items']):,} items, {len(dfs['stores']):,} tiendas, {len(dfs['products']):,} productos |
| Periodo | {tx['transaction_date'].min().date()} a {tx['transaction_date'].max().date()} |
| Base local | `data/retail_prueba_tecnica.sqlite` |
| Dashboard | `bloque5_dashboard.html` |
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
5. Ejecuta `py scripts\\run_sqlite_block1.py --preview 5` para crear las tablas del Bloque 1.
6. Abre `data/retail_prueba_tecnica.sqlite` con SQLite Viewer y refresca las tablas.
7. Usa `apoyo_exposicion_tecnica.html` y `GUIA_SQLITE_VSC.md` para preparar la explicacion.

## SQLite en VS Code

SQLite trabaja con un archivo local. No usa `Server name`, usuario, password, certificado ni instancia de SQL Server.

### Crear o refrescar la base

```powershell
py scripts\\create_sqlite_db.py
```

### Ejecutar todo el Bloque 1 y crear tablas visibles

```powershell
py scripts\\run_sqlite_block1.py --preview 5
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
py scripts\\query_sqlite.py "SELECT * FROM bloque1_q1_ventas_comparables LIMIT 20;"
```

### Guardar una consulta como tabla para SQLite Viewer

```powershell
py scripts\\query_sqlite.py "SELECT country, format, SUM(ventas_netas_periodo_actual) AS ventas_netas FROM bloque1_q1_ventas_comparables GROUP BY country, format;" --save resumen_ventas_pais_formato
```

Despues refresca SQLite Viewer y abre `resumen_ventas_pais_formato`.

### Si VS Code muestra errores de MSSQL

Si aparecen mensajes como `Incorrect syntax near 'LIMIT'` con `owner: mssql`, no es un error de SQLite. Significa que la extension de SQL Server esta leyendo el archivo como T-SQL. Para esta solucion, los archivos de `sqlite/` se ejecutan con `py scripts\\query_sqlite.py` o con una extension SQLite. El repo incluye `.vscode/settings.json` para reducir esos diagnosticos falsos.

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
| `bloque5_dashboard.html` | Dashboard operativo regional interactivo |
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
.venv\\Scripts\\activate
pip install -r requirements.txt
py scripts\\generate_all.py
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
"""
    (ROOT / "README.md").write_text(text, encoding="utf-8")


def write_support_files() -> None:
    (ROOT / "requirements.txt").write_text("pandas>=2.0\nnumpy>=1.24\nreportlab>=4.0\n", encoding="utf-8")
    (ROOT / ".gitignore").write_text(
        ".DS_Store\n__pycache__/\n.venv/\n*.pyc\n*.db\n*.sqlite\n*.sqlite3\n*.db-*\n*.sqlite-*\n*.sqlite3-*\n",
        encoding="utf-8",
    )
    (ROOT / ".vscode" / "tasks.json").write_text(
        json.dumps(
            {
                "version": "2.0.0",
                "tasks": [
                    {
                        "label": "SQLite: crear base local",
                        "type": "shell",
                        "command": "python",
                        "args": ["scripts/create_sqlite_db.py"],
                        "windows": {
                            "command": "py",
                            "args": ["scripts\\create_sqlite_db.py"],
                        },
                        "problemMatcher": [],
                    },
                    {
                        "label": "SQLite: ejecutar Bloque 1 y crear tablas",
                        "type": "shell",
                        "command": "python",
                        "args": ["scripts/run_sqlite_block1.py", "--preview", "5"],
                        "windows": {
                            "command": "py",
                            "args": ["scripts\\run_sqlite_block1.py", "--preview", "5"],
                        },
                        "problemMatcher": [],
                    },
                    {
                        "label": "SQLite: listar tablas",
                        "type": "shell",
                        "command": "python",
                        "args": ["scripts/query_sqlite.py", "--tables"],
                        "windows": {
                            "command": "py",
                            "args": ["scripts\\query_sqlite.py", "--tables"],
                        },
                        "problemMatcher": [],
                    },
                    {
                        "label": "Proyecto: regenerar entregables",
                        "type": "shell",
                        "command": "python",
                        "args": ["scripts/generate_all.py"],
                        "windows": {
                            "command": "py",
                            "args": ["scripts\\generate_all.py"],
                        },
                        "group": "build",
                        "problemMatcher": [],
                    }
                ],
            },
            indent=2,
        ),
        encoding="utf-8",
    )


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
    write_presentation(ab, comp_store, prod, gaps, gmroi_df, retention, pareto)
    write_readme(dfs)
    write_support_files()
    print("Entregables generados en", ROOT)


if __name__ == "__main__":
    main()

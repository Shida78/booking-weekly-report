"""Недельный отчёт по бронированиям.

Читает CSV с бронированиями, чистит данные, считает ключевые показатели
за последние 7 дней (в сравнении с предыдущими 7) и сохраняет отчёт
в report.md. Ошибки в данных не скрываются, а выносятся в отдельный блок.

Запуск:
    python weekly_report.py                      # bookings.csv -> report.md
    python weekly_report.py data.csv -o out.md   # свои файлы
    python weekly_report.py --today 2026-10-19   # зафиксировать «сегодня»
"""
import argparse
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

REQUIRED = ["booking_id", "property", "channel", "check_in", "check_out", "revenue", "status"]


def load_and_clean(path: Path):
    """Возвращает (чистые данные, список замечаний по качеству данных)."""
    df = pd.read_csv(path)

    missing_cols = [c for c in REQUIRED if c not in df.columns]
    if missing_cols:
        raise SystemExit(f"В файле нет колонок: {', '.join(missing_cols)}")

    issues = []

    # 1. Дубликаты по номеру брони
    dup = df.duplicated(subset="booking_id", keep="first")
    if dup.any():
        issues.append(f"Удалено дубликатов брони: {int(dup.sum())}")
        df = df[~dup]

    # 2. Даты
    df["check_in"] = pd.to_datetime(df["check_in"], errors="coerce")
    df["check_out"] = pd.to_datetime(df["check_out"], errors="coerce")
    bad_dates = df["check_in"].isna() | df["check_out"].isna()
    if bad_dates.any():
        issues.append(f"Исключено строк с нечитаемой датой: {int(bad_dates.sum())}")
        df = df[~bad_dates]

    # 3. Выезд раньше заезда
    reversed_dates = df["check_out"] < df["check_in"]
    if reversed_dates.any():
        ids = ", ".join(df.loc[reversed_dates, "booking_id"].astype(str))
        issues.append(f"Выезд раньше заезда, брони исключены: {ids}")
        df = df[~reversed_dates]

    # 4. Пропущенная или некорректная сумма
    df["revenue"] = pd.to_numeric(df["revenue"], errors="coerce")
    no_revenue = df["revenue"].isna() | (df["revenue"] < 0)
    if no_revenue.any():
        ids = ", ".join(df.loc[no_revenue, "booking_id"].astype(str))
        issues.append(f"Нет суммы или она отрицательная, брони исключены: {ids}")
        df = df[~no_revenue]

    df["nights"] = (df["check_out"] - df["check_in"]).dt.days
    return df.reset_index(drop=True), issues


def period_stats(df: pd.DataFrame, start: pd.Timestamp, end: pd.Timestamp) -> dict:
    """Показатели по заездам в интервале [start, end)."""
    part = df[(df["check_in"] >= start) & (df["check_in"] < end)]
    confirmed = part[part["status"] == "confirmed"]
    total = len(part)
    return {
        "bookings": len(confirmed),
        "revenue": float(confirmed["revenue"].sum()),
        "nights": int(confirmed["nights"].sum()),
        "avg_check": float(confirmed["revenue"].mean()) if len(confirmed) else 0.0,
        "cancel_rate": (part["status"] == "cancelled").sum() / total * 100 if total else 0.0,
        "part": part,
        "confirmed": confirmed,
    }


def delta(cur: float, prev: float) -> str:
    if prev == 0:
        return "—"
    pct = (cur - prev) / prev * 100
    sign = "+" if pct >= 0 else ""
    return f"{sign}{pct:.1f}%"


def build_report(df: pd.DataFrame, issues: list, today: date) -> str:
    end = pd.Timestamp(today) + pd.Timedelta(days=1)
    mid = end - pd.Timedelta(days=7)
    start = mid - pd.Timedelta(days=7)

    cur = period_stats(df, mid, end)
    prev = period_stats(df, start, mid)

    lines = []
    lines.append(f"# Недельный отчёт по бронированиям")
    lines.append(f"Период: {(mid).date():%d.%m.%Y} – {today:%d.%m.%Y} "
                 f"(сравнение с {start.date():%d.%m.%Y} – {(mid - pd.Timedelta(days=1)).date():%d.%m.%Y})")
    lines.append("")
    lines.append("## Ключевые показатели")
    lines.append("")
    lines.append("| Показатель | Эта неделя | Прошлая | Изменение |")
    lines.append("|---|---:|---:|---:|")
    lines.append(f"| Подтверждённых броней | {cur['bookings']} | {prev['bookings']} | {delta(cur['bookings'], prev['bookings'])} |")
    lines.append(f"| Выручка, € | {cur['revenue']:,.0f} | {prev['revenue']:,.0f} | {delta(cur['revenue'], prev['revenue'])} |")
    lines.append(f"| Ночей | {cur['nights']} | {prev['nights']} | {delta(cur['nights'], prev['nights'])} |")
    lines.append(f"| Средний чек, € | {cur['avg_check']:,.0f} | {prev['avg_check']:,.0f} | {delta(cur['avg_check'], prev['avg_check'])} |")
    lines.append(f"| Доля отмен, % | {cur['cancel_rate']:.1f} | {prev['cancel_rate']:.1f} | {cur['cancel_rate'] - prev['cancel_rate']:+.1f} п.п. |")
    lines.append("")

    # По каналам
    lines.append("## Выручка по каналам (эта неделя)")
    lines.append("")
    by_channel = (
        cur["confirmed"].groupby("channel")["revenue"].agg(["count", "sum"])
        .sort_values("sum", ascending=False)
    )
    if by_channel.empty:
        lines.append("Нет подтверждённых броней за период.")
    else:
        total_rev = by_channel["sum"].sum()
        lines.append("| Канал | Броней | Выручка, € | Доля |")
        lines.append("|---|---:|---:|---:|")
        for ch, row in by_channel.iterrows():
            lines.append(f"| {ch} | {int(row['count'])} | {row['sum']:,.0f} | {row['sum'] / total_rev * 100:.0f}% |")
    lines.append("")

    # Топ объектов
    lines.append("## Топ-5 объектов по выручке (эта неделя)")
    lines.append("")
    top = (
        cur["confirmed"].groupby("property")["revenue"].sum()
        .sort_values(ascending=False).head(5)
    )
    if top.empty:
        lines.append("Нет данных.")
    else:
        for i, (prop, rev) in enumerate(top.items(), 1):
            lines.append(f"{i}. {prop}: {rev:,.0f} €")
    lines.append("")

    # Объекты без заездов
    all_props = set(df["property"].unique())
    active = set(cur["confirmed"]["property"].unique())
    idle = sorted(all_props - active)
    lines.append("## Объекты без заездов на этой неделе")
    lines.append("")
    lines.append(", ".join(idle) if idle else "Таких нет.")
    lines.append("")

    # Качество данных
    lines.append("## Качество данных")
    lines.append("")
    if issues:
        lines.extend(f"- {i}" for i in issues)
    else:
        lines.append("Замечаний нет.")
    lines.append("")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Недельный отчёт по бронированиям")
    parser.add_argument("input", nargs="?", default="bookings.csv", help="CSV с бронированиями")
    parser.add_argument("-o", "--output", default="report.md", help="куда сохранить отчёт")
    parser.add_argument("--today", help="дата отчёта YYYY-MM-DD (по умолчанию сегодня)")
    args = parser.parse_args()

    today = date.fromisoformat(args.today) if args.today else date.today()
    df, issues = load_and_clean(Path(args.input))
    report = build_report(df, issues, today)
    Path(args.output).write_text(report, encoding="utf-8")
    print(report)


if __name__ == "__main__":
    main()

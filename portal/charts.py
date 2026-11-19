"""Server-rendered SVG charts (no JavaScript library, nothing for the CSP to allow).

Python computes geometry only; ``templates/portal/charts/*.html`` draws it with auto-escaping, so labels that
come from data (branch names, categories) can never inject markup. Every chart is single-series in the brand
hue, has a native SVG ``<title>`` tooltip on each mark and a data table for screen readers and printing.
"""

from __future__ import annotations

import datetime as dt
import math
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from django.db.models import Count, DateTimeField, QuerySet, Sum
from django.db.models.functions import TruncMonth

Number = int | float | Decimal


@dataclass
class Chart:
    title: str
    kind: str  # "bar" (vertical, time or few categories), "hbar" (ranked categories), "line" (trend)
    points: list[tuple[str, Number]]
    unit: str = ""
    note: str = ""
    geometry: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        builder = {"bar": vertical_bars, "hbar": horizontal_bars, "line": line}[self.kind]
        self.geometry = builder(self.points)

    @property
    def is_empty(self) -> bool:
        return not self.points or all(not v for _, v in self.points)

    @property
    def rows(self) -> list[tuple[str, str]]:
        return [(label, fmt(value, self.unit)) for label, value in self.points]


def fmt(value: Number, unit: str = "") -> str:
    if isinstance(value, Decimal | float) and value != int(value):
        text = f"{value:,.2f}"
    else:
        text = f"{int(value):,}"
    if unit == "%":
        return f"{text}%"
    return f"{text} {unit}".strip()


def nice_max(value: float) -> float:
    if value <= 0:
        return 1
    exponent = math.floor(math.log10(value))
    base = 10**exponent
    for step in (1, 2, 2.5, 5, 10):
        if value <= step * base:
            return step * base
    return 10 * base  # pragma: no cover


W, H = 640, 240
PAD_L, PAD_R, PAD_T, PAD_B = 48, 12, 16, 40


def _ticks(top: float) -> list[dict[str, Any]]:
    plot_h = H - PAD_T - PAD_B
    ticks = []
    for i in range(5):
        value = top * i / 4
        ticks.append({"y": round(PAD_T + plot_h - plot_h * i / 4, 1), "label": fmt(value)})
    return ticks


def vertical_bars(points: list[tuple[str, Number]]) -> dict[str, Any]:
    n = max(len(points), 1)
    top = nice_max(float(max((v for _, v in points), default=0) or 0))
    plot_w, plot_h = W - PAD_L - PAD_R, H - PAD_T - PAD_B
    slot = plot_w / n
    bar_w = max(4.0, min(36.0, slot * 0.6))
    bars = []
    label_every = 1 if n <= 12 else math.ceil(n / 12)
    for i, (label, value) in enumerate(points):
        h = plot_h * float(value) / top if top else 0
        x = PAD_L + slot * i + (slot - bar_w) / 2
        bars.append(
            {
                "x": round(x, 1),
                "y": round(PAD_T + plot_h - h, 1),
                "w": round(bar_w, 1),
                "h": round(max(h, 0), 1),
                "label": label,
                "value": value,
                "cx": round(x + bar_w / 2, 1),
                "show_label": i % label_every == 0,
                "hit_x": round(PAD_L + slot * i, 1),
                "hit_w": round(slot, 1),
            }
        )
    return {
        "w": W,
        "h": H,
        "bars": bars,
        "ticks": _ticks(top),
        "base_y": H - PAD_B,
        "label_y": H - PAD_B + 18,
        "x0": PAD_L,
        "x1": W - PAD_R,
        "plot_top": PAD_T,
        "plot_h": plot_h,
    }


def horizontal_bars(points: list[tuple[str, Number]]) -> dict[str, Any]:
    top = float(max((v for _, v in points), default=0) or 0) or 1
    rows = []
    for label, value in points:
        rows.append({"label": label, "value": value, "pct": round(float(value) * 100 / top, 1)})
    row_h = 28
    return {"rows": rows, "row_h": row_h, "h": max(row_h * len(rows), row_h), "w": 100}


def line(points: list[tuple[str, Number]]) -> dict[str, Any]:
    geom = vertical_bars(points)
    plot_h = geom["plot_h"]
    top = nice_max(float(max((v for _, v in points), default=0) or 0))
    n = max(len(points), 1)
    slot = (W - PAD_L - PAD_R) / n
    coords = []
    for i, (label, value) in enumerate(points):
        x = PAD_L + slot * i + slot / 2
        y = PAD_T + plot_h - (plot_h * float(value) / top if top else 0)
        coords.append({"x": round(x, 1), "y": round(y, 1), "label": label, "value": value})
    geom["dots"] = coords
    geom["path"] = " ".join(f"{'M' if i == 0 else 'L'}{c['x']},{c['y']}" for i, c in enumerate(coords))
    return geom


# ------------------------------------------------------------------------------------------- helpers
def month_starts(start: dt.date, end: dt.date) -> list[dt.date]:
    cur = start.replace(day=1)
    months = []
    while cur <= end:
        months.append(cur)
        cur = (cur.replace(day=28) + dt.timedelta(days=4)).replace(day=1)
    return months


def monthly_series(
    qs: QuerySet, date_field: str, start: dt.date, end: dt.date, *, sum_field: str | None = None
) -> list[tuple[str, Number]]:
    """Count (or sum) rows per month between start and end, filling empty months with 0."""
    agg = Sum(sum_field) if sum_field else Count("pk")
    lookup = date_field
    if isinstance(qs.model._meta.get_field(date_field), DateTimeField):
        lookup = f"{date_field}__date"  # compare calendar days in the ministry's time zone
    rows = (
        qs.filter(**{f"{lookup}__gte": start, f"{lookup}__lte": end})
        .annotate(rlm_bucket=TruncMonth(date_field))
        .values("rlm_bucket")
        .annotate(total=agg)
        .order_by("rlm_bucket")
    )
    totals = {}
    for row in rows:
        month = row["rlm_bucket"]
        if isinstance(month, dt.datetime):
            month = month.date()
        totals[month] = row["total"] or 0
    return [(m.strftime("%b %y"), totals.get(m, 0)) for m in month_starts(start, end)]


def grouped_counts(
    qs: QuerySet, field_name: str, labels: dict[Any, str] | None = None, limit: int = 10
) -> list:
    rows = qs.values(field_name).annotate(total=Count("pk")).order_by("-total")[:limit]
    out = []
    for row in rows:
        key = row[field_name]
        out.append(((labels or {}).get(key, key) if key not in (None, "") else "Not set", row["total"]))
    return out


def timeline(
    rows: list[dict[str, Any]], start: dt.date | None = None, end: dt.date | None = None
) -> dict[str, Any]:
    """Gantt-style geometry. rows: {"label", "start", "end", "progress" (0-100 or None), "url", "late"}.

    Positions are percentages of the visible range, so the template can draw them in a fluid SVG.
    """
    dated = [r for r in rows if r.get("start") and r.get("end")]
    if not dated:
        return {"rows": [], "months": []}
    start = start or min(r["start"] for r in dated)
    end = end or max(r["end"] for r in dated)
    span = max((end - start).days, 1)

    def pct(day: dt.date) -> float:
        return round(max(0.0, min(100.0, (day - start).days * 100 / span)), 2)

    out = []
    for r in dated:
        x = pct(r["start"])
        w = max(1.0, pct(r["end"]) - x)
        progress = r.get("progress")
        out.append({**r, "x": x, "w": round(w, 2), "done_w": round(w * (progress or 0) / 100, 2)})
    today = dt.date.today()
    months = [{"x": pct(m), "label": m.strftime("%b %y")} for m in month_starts(start, end)][
        :: max(1, len(month_starts(start, end)) // 8)
    ]
    return {
        "rows": out,
        "months": months,
        "today": pct(today) if start <= today <= end else None,
        "start": start,
        "end": end,
    }

"""Espande la lista di pagine di una specifica in pagine concrete (con date, se annuale)."""

from __future__ import annotations

import calendar
import datetime as dt

from .i18n import labels
from .spec import Variant

SECTION_TITLE_KEY = {
    "year": "year_overview", "monthly": "month", "weekly": "week", "daily": "daily",
    "habit": "habits", "budget": "budget", "checklist": "checklist",
    "goals": "goals", "notes": "notes",
}


def _first_weekday(week_start: str) -> int:
    return calendar.MONDAY if week_start == "monday" else calendar.SUNDAY


def month_grid(year: int | None, month: int | None, week_start: str) -> list[list[int | None]]:
    """Settimane del mese come liste di 7 giorni (None = cella vuota). Senza anno: 5x7 vuoto."""
    if year is None or month is None:
        return [[None] * 7 for _ in range(5)]
    cal = calendar.Calendar(firstweekday=_first_weekday(week_start))
    return [[d or None for d in week] for week in cal.monthdayscalendar(year, month)]


def year_weeks(year: int, week_start: str) -> list[list[dt.date]]:
    """Settimane (7 date) che coprono l'intero anno."""
    start = dt.date(year, 1, 1)
    offset = (start.weekday() - _first_weekday(week_start)) % 7
    start -= dt.timedelta(days=offset)
    weeks = []
    while start <= dt.date(year, 12, 31):
        weeks.append([start + dt.timedelta(days=i) for i in range(7)])
        start += dt.timedelta(days=7)
    return weeks


def expand_pages(variant: Variant) -> list[dict]:
    spec = variant.spec
    lab = labels(variant.lang, spec.week_start)
    year = spec.year
    pages: list[dict] = []
    sections: list[dict] = []

    def add(ptype: str, title: str, section: str | None = None, **data) -> None:
        pid = f"p{len(pages) + 1}"
        if section:
            sections.append({"title": section, "id": pid})
        pages.append({"type": ptype, "id": pid, "title": title, **data})

    for ps in spec.pages:
        t = ps.type
        opts = ps.options
        if t == "cover":
            add("cover", variant.name, subtitle=variant.subtitle, year=year)
        elif t == "index":
            add("index", lab["contents"])
        elif t == "year":
            months = [{"name": lab["months"][m - 1],
                       "grid": month_grid(year, m if year else None, spec.week_start)}
                      for m in range(1, 13)]
            add("year", f"{lab['year_overview']}{f' {year}' if year else ''}",
                section=lab["year_overview"], months=months)
        elif t == "monthly":
            if year:
                for m in range(1, 13):
                    name = f"{lab['months'][m - 1]} {year}"
                    add("monthly", name, section=name, grid=month_grid(year, m, spec.week_start))
            else:
                for i in range(ps.repeat):
                    add("monthly", lab["month"], section=lab["month"] if i == 0 else None,
                        grid=month_grid(None, None, spec.week_start))
        elif t == "weekly":
            if year:
                for n, week in enumerate(year_weeks(year, spec.week_start), start=1):
                    days = [{"name": lab["days"][i], "date": d.day,
                             "month": lab["months"][d.month - 1][:3]} for i, d in enumerate(week)]
                    rng = (f"{week[0].day} {lab['months'][week[0].month - 1][:3]} – "
                           f"{week[-1].day} {lab['months'][week[-1].month - 1][:3]}")
                    add("weekly", f"{lab['week']} {n}", subtitle=rng, days=days,
                        section=f"{lab['week']} 1" if n == 1 else None)
            else:
                for i in range(ps.repeat):
                    days = [{"name": d, "date": None, "month": None} for d in lab["days"]]
                    add("weekly", lab["week"], subtitle="", days=days,
                        section=lab["week"] if i == 0 else None)
        else:
            title = opts.get("title", {}).get(variant.lang) if isinstance(opts.get("title"), dict) else None
            title = title or lab[SECTION_TITLE_KEY[t]]
            for i in range(ps.repeat):
                add(t, title, section=title if i == 0 else None, options=opts)

    for p in pages:
        if p["type"] == "index":
            p["sections"] = sections
    return pages

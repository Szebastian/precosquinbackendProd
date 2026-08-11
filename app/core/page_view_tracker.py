import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from collections import defaultdict

DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"
DATA_DIR.mkdir(exist_ok=True)
PAGE_VIEWS_FILE = DATA_DIR / "page_views.json"


def _load() -> dict:
    if PAGE_VIEWS_FILE.exists():
        try:
            return json.loads(PAGE_VIEWS_FILE.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def _save(data: dict):
    PAGE_VIEWS_FILE.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


def record_view(path: str, visitor_id: str = "anon"):
    data = _load()
    now = datetime.now(timezone.utc)
    today = now.strftime("%Y-%m-%d")
    hour = now.strftime("%H")

    if today not in data:
        data[today] = {}
    if hour not in data[today]:
        data[today][hour] = {}
    if path not in data[today][hour]:
        data[today][hour][path] = {"count": 0, "visitors": []}

    entry = data[today][hour][path]
    entry["count"] += 1
    if visitor_id not in entry["visitors"]:
        entry["visitors"].append(visitor_id)
        if len(entry["visitors"]) > 1000:
            entry["visitors"] = entry["visitors"][-500:]
    _save(data)


def _migrate_old_format(data: dict) -> dict:
    """Migrate old format {date: {path: {count, visitors}}} to new {date: {hour: {path: ...}}}"""
    migrated = {}
    for date_str, day_data in data.items():
        if not isinstance(day_data, dict):
            continue
        first_val = next(iter(day_data.values()), None) if day_data else None
        if first_val and isinstance(first_val, dict) and "count" in first_val:
            migrated[date_str] = {"_unsorted": day_data}
        else:
            migrated[date_str] = day_data
    return migrated


def get_daily_views(days: int = 30) -> list:
    data = _load()
    data = _migrate_old_format(data)
    today = datetime.now(timezone.utc).date()
    result = []
    for i in range(days - 1, -1, -1):
        d = (today - timedelta(days=i)).strftime("%Y-%m-%d")
        day_data = data.get(d, {})
        total_views = 0
        unique_visitors = set()
        for hour_key, hour_data in day_data.items():
            if hour_key.startswith("_"):
                hour_data_copy = hour_data
            else:
                hour_data_copy = hour_data
            if isinstance(hour_data_copy, dict):
                for pv_path, pv_info in hour_data_copy.items():
                    if isinstance(pv_info, dict) and "count" in pv_info:
                        total_views += pv_info["count"]
                        unique_visitors.update(pv_info.get("visitors", []))
        result.append({
            "date": d,
            "total_views": total_views,
            "unique_visitors": len(unique_visitors),
            "pages": sum(
                len(hour_data)
                for hd in day_data.values()
                if isinstance(hd, dict)
                for hour_data in [hd]
            ),
        })
    return result


def get_hourly_views(date_str: str = None) -> list:
    """Return hourly breakdown for a given date. Returns list of {hour, views, unique_visitors, pages}."""
    data = _load()
    data = _migrate_old_format(data)
    if not date_str:
        date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    day_data = data.get(date_str, {})

    result = []
    for h in range(24):
        hour_key = f"{h:02d}"
        hour_data = day_data.get(hour_key, {})
        if not isinstance(hour_data, dict):
            hour_data = {}

        views = 0
        visitors = set()
        pages = 0

        for pv_path, pv_info in hour_data.items():
            if isinstance(pv_info, dict) and "count" in pv_info:
                views += pv_info["count"]
                visitors.update(pv_info.get("visitors", []))
                pages += 1

        result.append({
            "hour": h,
            "hour_label": f"{h:02d}:00",
            "views": views,
            "unique_visitors": len(visitors),
            "pages": pages,
        })

    return result


def get_daily_views_with_hours(days: int = 7) -> list:
    """Return daily data with hourly sub-breakdown."""
    data = _load()
    data = _migrate_old_format(data)
    today = datetime.now(timezone.utc).date()
    result = []

    for i in range(days - 1, -1, -1):
        d = (today - timedelta(days=i)).strftime("%Y-%m-%d")
        hourly = get_hourly_views(d)
        total_views = sum(h["views"] for h in hourly)
        unique_visitors = sum(h["unique_visitors"] for h in hourly)

        result.append({
            "date": d,
            "total_views": total_views,
            "unique_visitors": unique_visitors,
            "hourly": hourly,
        })

    return result

"""A tiny JSON memory of every grant we've already emailed."""
import datetime as dt
import difflib
import json
import os

from .agents import norm_url


def load(path):
    if not os.path.exists(path):
        return {}
    with open(path) as f:
        return json.load(f)


def save(path, store):
    with open(path, "w") as f:
        json.dump(store, f, indent=2, sort_keys=True)


def _same_title(a, b):
    return difflib.SequenceMatcher(None, a.lower(), b.lower()).ratio() >= 0.9


def split_new(grants, store):
    """Grants we have never emailed before (same link OR almost the same title)."""
    old_titles = [item["title"] for item in store.values()]
    return [g for g in grants if norm_url(g["url"]) not in store
            and not any(_same_title(g["title"], t) for t in old_titles)]


def remember(store, grants, today):
    for g in grants:
        store[norm_url(g["url"])] = {
            "title": g["title"],
            "url": g["url"],
            "funder": g.get("funder", ""),
            "deadline": str(g["deadline"]),
            "fit": g["fit"],
            "route": g["route"],
            "first_seen": str(today),
        }


def closing_soon(store, today, days):
    """Grants we emailed before whose deadline is within `days` (code date math)."""
    soon = []
    for item in store.values():
        deadline = dt.date.fromisoformat(item["deadline"])
        if today < deadline <= today + dt.timedelta(days=days):
            soon.append(dict(item, days_left=(deadline - today).days))
    return sorted(soon, key=lambda x: x["days_left"])

"""Sub-agents (one per channel) and the coordinator that runs them."""
import difflib
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlsplit

from . import channels, config, jev_checks
from .budget import Budget


def norm_url(url):
    parts = urlsplit(url)
    host = parts.netloc.lower().removeprefix("www.")
    return (host + parts.path.rstrip("/")).lower()


def sub_agent(channel, angle, seen):
    """Mini loop for ONE channel: search -> Jev filter -> Jev 'dig deeper?'."""
    search, templates = channels.CHANNELS[channel]
    budget = Budget(queries=config.MAX_QUERIES_PER_CHANNEL, jev=config.MAX_JEV_PER_CHANNEL)
    found, log = [], []
    topic = config.ANGLES[angle]
    kw = channels.GRANTS_GOV_KEYWORDS[angle]
    for template in templates:
        if not budget.take("queries"):
            log.append("query budget used up")
            break
        query = template.format(topic=topic, kw=kw)
        try:
            leads = search(query)
        except Exception as err:  # a broken channel must not stop the others
            log.append(f"search error: {type(err).__name__}")
            break
        new = [x for x in leads if norm_url(x["url"]) not in seen]
        good = []
        for item in new:
            p = jev_checks.is_grant(item, budget)
            if p is None:
                log.append("Jev budget used up")
                break
            if p >= config.GRANT_P:
                good.append(dict(item, grant_p=round(p, 2)))
        found += good
        dig = jev_checks.dig_deeper(query, new, len(good), budget)
        log.append(f"'{query[:45]}': {len(leads)} results, {len(good)} grants, dig={dig:.2f}")
        if dig < config.DIG_P:
            log.append("Jev: stop digging")
            break
    # Dig deeper on web channels: find pages similar to the best hit.
    if found and channel in ("tavily", "duckduckgo") and budget.left("jev") > 3:
        best = max(found, key=lambda x: x["grant_p"])
        try:
            for item in channels.find_similar(best["url"], 4):
                p = jev_checks.is_grant(item, budget)
                if p is not None and p >= config.GRANT_P:
                    found.append(dict(item, grant_p=round(p, 2)))
            log.append("dug deeper with Exa find-similar")
        except Exception as err:
            log.append(f"find-similar error: {type(err).__name__}")
    return {"channel": channel, "found": found, "log": log, "budget": repr(budget)}


def run_sub_agents(angle, seen, channel_names=None):
    names = channel_names or list(channels.CHANNELS)
    with ThreadPoolExecutor(max_workers=len(names)) as pool:
        return list(pool.map(lambda ch: sub_agent(ch, angle, seen), names))


def merge(reports, seen, budget=None):
    """Dedupe by URL, then ask Jev about look-alike titles."""
    merged = {}
    for report in reports:
        for item in report["found"]:
            key = norm_url(item["url"])
            if key in seen:
                continue
            if key in merged:
                merged[key]["channels"].add(item["channel"])
                continue
            twin = None
            for other in merged.values():
                ratio = difflib.SequenceMatcher(
                    None, item["title"].lower(), other["title"].lower()
                ).ratio()
                if ratio > 0.6 and jev_checks.same_grant(item, other, budget) >= 0.7:
                    twin = other
                    break
            if twin:
                twin["channels"].add(item["channel"])
            else:
                merged[key] = dict(item, channels={item["channel"]})
    return list(merged.values())


def verify_and_score(item, today, budget):
    """Deadline (code + Jev), amount, open/eligible/fit. Returns an enriched dict."""
    text = item["snippet"]
    if item["channel"] != "grants_gov":
        if not budget.take("fetches"):
            return dict(item, route="skip", reason="fetch budget")
        try:
            text = channels.fetch_page(item["url"])
        except Exception:
            return dict(item, route="skip", reason="page unreadable")
    deadline, deadline_p = item.get("deadline"), 1.0
    if deadline is None:
        deadline, deadline_p = jev_checks.find_deadline(text, today, budget)
    if deadline is None or deadline <= today:  # CODE does the date math
        return dict(item, route="skip", reason="no future deadline")
    scores = jev_checks.assess(item, text, budget) or {}
    if item["channel"] == "grants_gov" and scores:
        scores["open_p"] = 1.0  # structured data: status "posted" means open
    amount = jev_checks.find_amount(text, budget) if item["channel"] != "grants_gov" else ""
    funder = item.get("funder") or urlsplit(item["url"]).netloc.removeprefix("www.")
    out = dict(item, deadline=deadline, deadline_p=round(deadline_p, 2), amount=amount, funder=funder, **scores)
    out["route"] = route(out)
    return out


def route(g):
    """Code turns Jev's numbers into a decision."""
    if not g.get("fit_conf"):
        return "skip"
    confident = (
        g["deadline_p"] >= config.DEADLINE_P
        and g["fit_conf"] >= config.CONF_MIN
        and g["eligible_p"] >= config.ELIGIBLE_P
        and g["open_p"] >= 0.5
    )
    if g["fit"] >= config.FIT_MIN and confident:
        return "Open"
    if g["fit"] >= 1.5:
        return "Needs Review"
    return "skip"


def coordinator(today=None, seen=None, channel_names=None, verbose=True):
    """Plan angles -> parallel sub-agents -> merge -> verify/score -> stop?"""
    today = today or config.TODAY
    seen = set(seen or [])
    budget = Budget(jev=config.MAX_TOTAL_JEV, fetches=config.MAX_PAGE_FETCHES)
    tried, results = set(), []
    for round_no in range(1, config.MAX_ROUNDS + 1):
        angle, conf = jev_checks.pick_angle(config.PROFILE, tried, budget)
        if angle is None:
            break
        tried.add(angle)
        if verbose:
            print(f"\n=== Round {round_no}: Jev picked angle '{angle}' (conf {conf:.2f})")
        reports = run_sub_agents(angle, seen, channel_names)
        if verbose:
            for r in reports:
                print(f"  [{r['channel']}] {len(r['found'])} leads | {r['budget']}")
                for line in r["log"]:
                    print(f"      {line}")
        leads = merge(reports, seen, budget)
        seen |= {norm_url(x["url"]) for x in leads}
        with ThreadPoolExecutor(max_workers=6) as pool:
            checked = list(pool.map(lambda x: verify_and_score(x, today, budget), leads))
        new_good = [g for g in checked if g["route"] != "skip"]
        results += new_good
        good = sum(1 for g in results if g["route"] == "Open")
        if verbose:
            print(f"  merged {len(leads)} leads -> {len(new_good)} kept "
                  f"({good} Open so far) | budget {budget}")
        p_stop = jev_checks.enough(good, config.TARGET_GOOD_GRANTS, round_no, len(new_good), budget)
        if verbose:
            print(f"  Jev 'enough?' = {p_stop:.2f}")
        if p_stop >= 0.5:
            break
    return sorted(results, key=lambda g: (g["route"] != "Open", -g["fit"])), budget

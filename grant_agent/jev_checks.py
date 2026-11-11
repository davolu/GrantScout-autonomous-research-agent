"""Every judgment call is a typed Jev question. No text generation anywhere."""
import re
import datetime as dt

from typesafe_sdk import Choice, Noul, Score, TypeSafeClient

from . import config

jev = TypeSafeClient()

GRANT_Q = Noul(
    instructions="Is this a specific grant funding opportunity that nonprofits can apply to?",
    criteria={
        "true": "Describes one specific grant or funding program with an application process.",
        "false": "A blog post, video, database or list of many grants, advice, or event.",
    },
)
DIG_Q = Noul(
    instructions="Would one more search on this channel likely find more real grants?",
    criteria={
        "true": "Several results are real, specific grant opportunities.",
        "false": "Results are mostly irrelevant, lists, ads or articles.",
    },
)
OPEN_Q = Noul(
    instructions="Does the page say applications are currently being accepted or upcoming?",
    criteria={
        "true": "Applications are open now or will open soon.",
        "false": "Closed, already awarded, or the page does not say.",
    },
)
ELIGIBLE_Q = Noul(
    instructions="Could a small US 501(c)(3) community nonprofit apply for this?",
    criteria={
        "true": "Nonprofit or 501(c)(3) organizations are eligible applicants.",
        "false": "Only individuals, universities, governments, tribes or businesses.",
    },
)
FIT_Q = Score(
    instructions=f"How well does this grant fit this nonprofit? {config.PROFILE}",
    criteria=["no fit", "weak fit", "partial fit", "good fit", "excellent fit"],
)
DEADLINE_CRITERIA = {
    "true": "The date is when applications, proposals or letters of inquiry are due.",
    "false": "The date is an event, award date, grant period or publication date.",
}
SAME_Q = Noul(
    instructions="Do these two results describe the same grant program?",
    criteria={
        "true": "Same funder and same program, even if worded differently.",
        "false": "Different programs or different funders.",
    },
)
ENOUGH_Q = Noul(
    instructions="Do we already have enough good, open grants to stop searching?",
    criteria={
        "true": "The goal number is reached or new rounds keep finding nothing new.",
        "false": "Clearly fewer good grants than the goal, and angles are left to try.",
    },
)


def ask(state, questions, budget=None):
    """One Jev call. Optionally charge it to a Budget under 'jev'."""
    if budget is not None and not budget.take("jev"):
        return None
    return jev.system_one(state=state, questions=questions)


def is_grant(lead, budget=None):
    state = {"title": lead["title"], "url": lead["url"], "snippet": lead["snippet"]}
    r = ask(state, {"is_grant": GRANT_Q}, budget)
    return None if r is None else r.nouls["is_grant"].noul


def dig_deeper(query, leads, good_count, budget=None):
    state = {
        "query": query,
        "result_titles": [x["title"] for x in leads][:10],
        "real_grants_found": good_count,
    }
    r = ask(state, {"dig": DIG_Q}, budget)
    return 0.0 if r is None else r.nouls["dig"].noul


def pick_angle(profile, tried, budget=None):
    left = {k: v for k, v in config.ANGLES.items() if k not in tried}
    if not left:
        return None, 0.0
    if len(left) == 1:
        return next(iter(left)), 1.0
    q = Choice(instructions="Which funding search angle should we try next?", criteria=left)
    r = ask({"nonprofit": profile, "already_tried": sorted(tried)}, {"angle": q}, budget)
    if r is None:
        return None, 0.0
    return r.choices["angle"].choice, r.choices["angle"].confidence


def enough(good, goal, rounds_done, new_last_round, budget=None):
    state = {
        "good_open_grants": good,
        "goal": goal,
        "rounds_done": rounds_done,
        "new_grants_last_round": new_last_round,
    }
    r = ask(state, {"enough": ENOUGH_Q}, budget)
    return 1.0 if r is None else r.nouls["enough"].noul


MONTHS = (
    "January|February|March|April|May|June|July|August|September|October|"
    "November|December|Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec"
)
DATE_RE = re.compile(
    rf"\b(?:{MONTHS})\.?\s+\d{{1,2}}(?:st|nd|rd|th)?,?\s+20\d\d\b"
    r"|\b\d{1,2}/\d{1,2}/20\d\d\b"
)


def parse_date(text):
    clean = re.sub(r"(\d)(st|nd|rd|th)", r"\1", text)
    clean = clean.replace(".", "").replace(",", "").replace("Sept", "Sep")
    for fmt in ("%B %d %Y", "%b %d %Y", "%m/%d/%Y"):
        try:
            return dt.datetime.strptime(clean, fmt).date()
        except ValueError:
            pass
    return None


def future_dates(text, today, limit=8, max_years=3):
    """CODE finds every date after today (Jev never does date math)."""
    found = []
    for m in DATE_RE.finditer(text):
        day = parse_date(m.group(0))
        if not day or day <= today or (day - today).days > 365 * max_years:
            continue
        if any(day == f["date"] for f in found):
            continue
        snippet = text[max(0, m.start() - 150) : m.end() + 40].replace("\n", " ")
        found.append({"text": m.group(0), "date": day, "snippet": snippet})
    return found[:limit]


def find_deadline(text, today, budget=None):
    """One Jev yes/no per future date, all in ONE call. Best date wins."""
    dates = future_dates(text, today)
    if not dates:
        return None, 0.0
    questions = {
        f"d{i}": Noul(
            instructions=f"In snippet d{i}, is {d['text']} the application deadline?",
            criteria=DEADLINE_CRITERIA,
        )
        for i, d in enumerate(dates)
    }
    state = {f"d{i}": d["snippet"] for i, d in enumerate(dates)}
    r = ask(state, questions, budget)
    if r is None:
        return None, 0.0
    best = max(questions, key=lambda k: r.nouls[k].noul)
    return dates[int(best[1:])]["date"], r.nouls[best].noul


AMOUNT_RE = re.compile(r"\$\s?\d[\d,]*(?:\.\d+)?\s?(?:[KkMm]\b|million|thousand)?")


def find_amount(text, budget=None):
    """Code finds dollar amounts; Jev says which one is the award size."""
    seen, cands = set(), []
    for m in AMOUNT_RE.finditer(text):
        value = m.group(0).strip()
        if value in seen:
            continue
        seen.add(value)
        cands.append((value, text[max(0, m.start() - 100) : m.end() + 40]))
        if len(cands) == 6:
            break
    if not cands:
        return ""
    questions = {
        f"a{i}": Noul(
            instructions=f"In snippet a{i}, is {v} the size of the grant award?",
            criteria={
                "true": "The amount a grantee can receive.",
                "false": "A budget limit, total fund size, fee or unrelated number.",
            },
        )
        for i, (v, _) in enumerate(cands)
    }
    r = ask({f"a{i}": s for i, (_, s) in enumerate(cands)}, questions, budget)
    if r is None:
        return ""
    best = max(questions, key=lambda k: r.nouls[k].noul)
    return cands[int(best[1:])][0] if r.nouls[best].noul >= 0.5 else ""


def assess(lead, text, budget=None):
    """Open? Eligible? Fit? Three questions, one Jev call."""
    state = {"title": lead["title"], "funder": lead.get("funder", ""), "page": text[:6000]}
    r = ask(state, {"open": OPEN_Q, "eligible": ELIGIBLE_Q, "fit": FIT_Q}, budget)
    if r is None:
        return None
    return {
        "open_p": round(r.nouls["open"].noul, 2),
        "eligible_p": round(r.nouls["eligible"].noul, 2),
        "fit": round(r.scores["fit"].score, 2),
        "fit_conf": round(r.scores["fit"].confidence, 2),
    }


def same_grant(a, b, budget=None):
    state = {"a": {"title": a["title"], "url": a["url"]}, "b": {"title": b["title"], "url": b["url"]}}
    r = ask(state, {"same": SAME_Q}, budget)
    return 0.0 if r is None else r.nouls["same"].noul

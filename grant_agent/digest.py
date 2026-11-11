"""Build the HTML digest in code (no LLM) and send ONE email via Composio Gmail."""
import html

from . import config
from .channels import run_tool

CSS_CELL = "padding:8px 10px;border-bottom:1px solid #E2E8F0;font-size:14px;"
CSS_HEAD = CSS_CELL + "background:#F1F5F9;text-align:left;color:#17324D;"


def _table(rows, columns):
    head = "".join(f'<th style="{CSS_HEAD}">{html.escape(c)}</th>' for c, _ in columns)
    body = ""
    for r in rows:
        cells = "".join(f'<td style="{CSS_CELL}">{fn(r)}</td>' for _, fn in columns)
        body += f"<tr>{cells}</tr>"
    return f'<table style="border-collapse:collapse;width:100%"><tr>{head}</tr>{body}</table>'


def _link(r):
    return f'<a href="{html.escape(r["url"])}" style="color:#0F766E">Apply / details</a>'


GRANT_COLUMNS = [
    ("Grant", lambda r: f"<b>{html.escape(r['title'][:90])}</b>"),
    ("Funder", lambda r: html.escape((r.get("funder") or "-")[:50])),
    ("Amount", lambda r: html.escape(r.get("amount") or "See page")),
    ("Deadline", lambda r: str(r["deadline"])),
    ("Fit (0-4)", lambda r: f"{r['fit']:.1f}"),
    ("Link", _link),
]
SOON_COLUMNS = [
    ("Grant", lambda r: html.escape(r["title"][:90])),
    ("Deadline", lambda r: str(r["deadline"])),
    ("Days left", lambda r: str(r["days_left"])),
    ("Link", _link),
]


def build_digest(new_grants, closing, today):
    """Return (subject, html_body). Pure code: easy to test, nothing generated."""
    ready = [g for g in new_grants if g["route"] == "Open"]
    review = [g for g in new_grants if g["route"] == "Needs Review"]
    subject = f"Grant digest {today}: {len(ready)} new, {len(review)} to review, {len(closing)} closing soon"
    parts = [
        '<div style="font-family:Arial,sans-serif;max-width:900px;color:#17324D">',
        f'<h2 style="color:#0F766E">Grant digest for {today}</h2>',
        f"<p>{html.escape(config.PROFILE)}</p>",
        f"<h3>New grants ready to apply ({len(ready)})</h3>",
        _table(ready, GRANT_COLUMNS) if ready else "<p>No new high-confidence grants today.</p>",
        f"<h3>Needs review ({len(review)})</h3>",
        "<p style='color:#526477'>Decent fit, but Jev was not confident enough to file "
        "these automatically. Please check them yourself.</p>",
        _table(review, GRANT_COLUMNS) if review else "<p>Nothing to review.</p>",
        f"<h3>Closing soon ({len(closing)})</h3>",
        _table(closing, SOON_COLUMNS) if closing else "<p>No earlier grants close in the next two weeks.</p>",
        '<p style="color:#94A3B8;font-size:12px">Built by grant_agent.py: Jev decides, '
        "Python loops, Composio acts. No LLM wrote this email.</p></div>",
    ]
    return subject, "\n".join(parts)


def my_address():
    """The connected Gmail account's OWN address. We only ever send to this."""
    data = run_tool("GMAIL_GET_PROFILE", {"user_id": "me"}, user_id=config.GMAIL_USER_ID)
    return data["emailAddress"]


def mask(address):
    name, _, domain = address.partition("@")
    return f"{name[:1]}***@{domain}"


def send_digest(subject, body):
    """Send exactly one email, to yourself."""
    to = my_address()
    run_tool(
        "GMAIL_SEND_EMAIL",
        {"recipient_email": to, "subject": subject, "body": body, "is_html": True},
        user_id=config.GMAIL_USER_ID,
    )
    return mask(to)

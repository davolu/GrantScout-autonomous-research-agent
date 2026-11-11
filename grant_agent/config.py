"""All the knobs in one place. Keys come from the environment, never from code."""
import datetime as dt
import os

# GRANT_TODAY lets you test "what if it were another day?" (e.g. 2027-01-05).
TODAY = (dt.date.fromisoformat(os.environ["GRANT_TODAY"]) if os.environ.get("GRANT_TODAY")
         else dt.date.today())

PROFILE = (
    "Bright Futures Community Center: a US 501(c)(3) nonprofit running "
    "after-school youth education and a weekly food pantry for low-income "
    "families. Annual budget under $1M."
)

# Composio user ids. Search tools need no login, so "default" is fine.
USER_ID = os.environ.get("COMPOSIO_USER_ID", "default")
# The Composio user id that owns your connected Gmail account.
GMAIL_USER_ID = os.environ.get("GMAIL_USER_ID", USER_ID)

# Local memory so the daily run never emails the same grant twice.
STORE_PATH = os.environ.get("GRANT_STORE", "seen_grants.json")
CLOSING_SOON_DAYS = 14

# Search angles Jev can choose from (plain-English descriptions).
ANGLES = {
    "youth_education": "grants for youth education and after-school programs",
    "food_security": "grants for food pantries, hunger relief and food security",
    "community_foundation": "local community foundation grants for small nonprofits",
    "corporate": "corporate and company foundation giving programs for nonprofits",
}

# Jev thresholds (tune these in Episode 20).
GRANT_P = 0.70  # "is this a real grant?" yes-probability to keep a lead
DIG_P = 0.50  # "dig deeper?" yes-probability to run the next query
DEADLINE_P = 0.60  # "is this date the deadline?" to trust a deadline
FIT_MIN = 2.0  # fit score (0-4) to auto-file as Open
CONF_MIN = 0.45  # fit confidence to auto-file
ELIGIBLE_P = 0.60  # "eligible?" yes-probability to auto-file

# Hard budgets enforced by code.
MAX_ROUNDS = 3
MAX_QUERIES_PER_CHANNEL = 2
MAX_JEV_PER_CHANNEL = 25
MAX_PAGE_FETCHES = 30
MAX_TOTAL_JEV = 250
TARGET_GOOD_GRANTS = 8

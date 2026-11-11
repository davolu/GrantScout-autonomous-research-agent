"""Grant Research Agent: run the whole system from the terminal.

    python grant_agent.py            # search, score, email ONE digest to yourself
    python grant_agent.py --dry-run  # search + score, save digest.html, send nothing
"""
import argparse
import json
import os
import sys
import time



def load_env_file(path=".env"):
    """Read KEY=value lines from .env into the environment (never printed)."""
    if not os.path.exists(path):
        return
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                os.environ.setdefault(key.strip(), value.strip().strip('"'))


load_env_file()
from grant_agent import config  # noqa: E402  (after .env is loaded)


def check_keys():
    missing = [k for k in ("COMPOSIO_API_KEY", "TYPESAFE_API_KEY") if not os.environ.get(k)]
    if missing:
        sys.exit(f"Missing environment variables: {', '.join(missing)} (see .env.example)")
    print("Keys found in environment (values never printed).")


def main():
    parser = argparse.ArgumentParser(description="Find open nonprofit grants.")
    parser.add_argument("--dry-run", action="store_true", help="don't send the email")
    parser.add_argument("--html", default="digest.html", help="also save the digest here")
    parser.add_argument("--json", default="", help="also save raw results to this file")
    args = parser.parse_args()
    check_keys()

    from grant_agent import agents, digest, store

    today = config.TODAY
    memory = store.load(config.STORE_PATH)
    print(f"Today: {today} | grants already emailed before: {len(memory)}")

    start = time.time()
    grants, budget = agents.coordinator(today=today, seen=set(memory))
    print(f"\nFinished in {time.time() - start:.0f}s | budget used: {budget}")

    new = store.split_new(grants, memory)
    closing = store.closing_soon(memory, today, config.CLOSING_SOON_DAYS)
    print(f"\n{'STATUS':<13} {'FIT':>4}  {'DEADLINE':<10}  TITLE")
    for g in new:
        print(f"{g['route']:<13} {g['fit']:>4}  {g['deadline']}  {g['title'][:60]}")
        print(f"{'':<31}{g['url']}")
    print(f"Closing soon (from earlier runs): {len(closing)}")

    subject, body = digest.build_digest(new, closing, today)
    with open(args.html, "w") as f:
        f.write(body)
    print(f"\nSubject: {subject}\nSaved the email preview to {args.html}")
    if args.json:
        with open(args.json, "w") as f:
            json.dump(new, f, indent=2, default=lambda o: sorted(o) if isinstance(o, set) else str(o))

    if args.dry_run:
        print("Dry run: no email sent, memory not updated.")
        return
    sent_to = digest.send_digest(subject, body)
    store.remember(memory, new, today)
    store.save(config.STORE_PATH, memory)
    print(f"Sent ONE digest email to {sent_to}. Memory now holds {len(memory)} grants.")


if __name__ == "__main__":
    main()

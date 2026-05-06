#!/usr/bin/env python3
"""
Check Gmail inbox for replies from faculty in outreach_tracker.csv and update the status column.
Run from outreach_ra_profs_v1: python ghostwriter/check_inbox_and_update_tracker.py

Uses Gmail API read-only scope. On first run you may need to authorize in the browser.
Token is stored in token_inbox.json (separate from send token).
"""
import os
import sys
import csv

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)
if os.getcwd() != PROJECT_ROOT:
    os.chdir(PROJECT_ROOT)

DATA_DIR = "data"
TRACKER_CSV = os.path.join(DATA_DIR, "outreach_tracking.csv")
TRACKER_COLUMNS = ["faculty_name", "department", "email_id", "date_email_sent", "status"]
TOKEN_PATH = os.path.join(PROJECT_ROOT, "token_inbox.json")
CREDENTIALS_PATH = os.path.join(PROJECT_ROOT, "credentials.json")
SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]


def get_gmail_service():
    """Build Gmail API service with read-only scope."""
    try:
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
        from google.auth.transport.requests import Request
        from googleapiclient.discovery import build
    except ImportError as e:
        print(f"Gmail API deps missing: {e}. Install: pip install google-auth-oauthlib google-api-python-client")
        return None

    creds = None
    if os.path.exists(TOKEN_PATH):
        creds = Credentials.from_authorized_user_file(TOKEN_PATH, SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not os.path.exists(CREDENTIALS_PATH):
                print(f"Error: {CREDENTIALS_PATH} not found. Add Gmail API credentials for inbox read.")
                return None
            flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_PATH, SCOPES)
            creds = flow.run_local_server(port=0)
        with open(TOKEN_PATH, "w") as f:
            f.write(creds.to_json())

    return build("gmail", "v1", credentials=creds)


def get_replied_addresses(service, max_messages=200):
    """
    Search INBOX for messages; return set of sender email addresses (lowercase).
    Treats any message in inbox as a potential 'reply' from that sender.
    """
    replied = set()
    try:
        # List messages in INBOX (recent first)
        result = service.users().messages().list(userId="me", labelIds=["INBOX"], maxResults=max_messages).execute()
        messages = result.get("messages", [])
        for msg_ref in messages:
            try:
                msg = service.users().messages().get(userId="me", id=msg_ref["id"], format="metadata", metadataHeaders=["From"]).execute()
                headers = msg.get("payload", {}).get("headers", [])
                for h in headers:
                    if h.get("name", "").lower() == "from":
                        from_val = h.get("value", "")
                        # Extract email: "Name <email@uw.edu>" -> email@uw.edu
                        if "<" in from_val and ">" in from_val:
                            from_val = from_val.split("<")[1].split(">")[0].strip()
                        from_val = from_val.strip().lower()
                        if from_val and "@" in from_val:
                            replied.add(from_val)
                        break
            except Exception:
                continue
    except Exception as e:
        print(f"Error listing inbox: {e}")
    return replied


def load_tracker():
    """Load tracker CSV into list of dicts."""
    if not os.path.exists(TRACKER_CSV):
        return []
    rows = []
    with open(TRACKER_CSV, "r", encoding="utf-8") as f:
        r = csv.DictReader(f)
        if r.fieldnames:
            for row in r:
                rows.append(dict(row))
    return rows


def save_tracker(rows):
    """Write tracker CSV from list of dicts."""
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(TRACKER_CSV, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=TRACKER_COLUMNS, extrasaction="ignore")
        w.writeheader()
        for row in rows:
            w.writerow({k: row.get(k, "") for k in TRACKER_COLUMNS})


def main(dry_run=False):
    if not os.path.exists(TRACKER_CSV):
        print(f"No tracker found at {TRACKER_CSV}. Run generate_faculty_emails.py first to create it.")
        return

    rows = load_tracker()
    if not rows:
        print("Tracker is empty. Nothing to update.")
        return

    print(f"Tracker: {len(rows)} row(s) loaded from {TRACKER_CSV}")
    print("Connecting to Gmail (read-only)...")
    service = get_gmail_service()
    if not service:
        print("Skipping inbox check (no Gmail connection). Tracker CSV is ready for when you add credentials.")
        return

    print("Checking inbox for messages from tracked faculty...")
    replied_addresses = get_replied_addresses(service)
    print(f"  Inbox: found {len(replied_addresses)} unique sender(s).")

    updated = 0
    for row in rows:
        email_id = (row.get("email_id") or "").strip().lower()
        status = (row.get("status") or "").strip()
        if not email_id or status:
            continue
        if email_id in replied_addresses:
            row["status"] = "Replied"
            updated += 1
            if not dry_run:
                print(f"  -> {row.get('faculty_name')} ({email_id}): Replied")

    if dry_run:
        print(f"  [Dry run] Would update {updated} row(s) to status 'Replied'.")
        return

    if updated > 0:
        save_tracker(rows)
        print(f"Updated tracker: {updated} row(s) set to 'Replied'. Saved to {TRACKER_CSV}.")
    else:
        print("No new replies from tracked faculty. Tracker unchanged.")


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser(description="Check Gmail inbox and update outreach_tracker status.")
    p.add_argument("--dry-run", action="store_true", help="Only report what would be updated")
    args = p.parse_args()
    main(dry_run=args.dry_run)

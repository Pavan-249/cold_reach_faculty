#!/usr/bin/env python3
"""
Check Gmail inbox for replies from faculty in outreach_tracking.csv and update the status column.
Run periodically (e.g. daily) to mark "Replied" for faculty who have responded.

Requires: credentials.json (Gmail OAuth), and token_inbox.json (created on first run).
Scope: gmail.readonly (read inbox only; does not send email).

Usage (from outreach_ra_profs_v1):
  python ghostwriter/check_inbox_replies.py          # check inbox and update CSV
  python ghostwriter/check_inbox_replies.py --dry-run # show what would be updated, don't write
"""
import os
import sys
import csv
import re

# Project root
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)
if os.getcwd() != PROJECT_ROOT:
    os.chdir(PROJECT_ROOT)

DATA_DIR = "data"
TRACKING_CSV = os.path.join(DATA_DIR, "outreach_tracking.csv")
TOKEN_PATH = os.path.join(PROJECT_ROOT, "token_inbox.json")
CREDENTIALS_PATH = os.path.join(PROJECT_ROOT, "credentials.json")
SCOPES_READ = ["https://www.googleapis.com/auth/gmail.readonly"]


def get_gmail_service():
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build

    creds = None
    if os.path.exists(TOKEN_PATH):
        creds = Credentials.from_authorized_user_file(TOKEN_PATH, SCOPES_READ)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not os.path.exists(CREDENTIALS_PATH):
                print("Missing credentials.json. Download OAuth client credentials from Google Cloud Console.")
                return None
            flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_PATH, SCOPES_READ)
            creds = flow.run_local_server(port=0)
        with open(TOKEN_PATH, "w") as token:
            token.write(creds.to_json())
    return build("gmail", "v1", credentials=creds)


def list_inbox_sender_emails(service, max_messages=200):
    """List unique sender emails from inbox (recent messages)."""
    try:
        results = service.users().messages().list(userId="me", labelIds=["INBOX"], maxResults=max_messages).execute()
        messages = results.get("messages", [])
    except Exception as e:
        print(f"Gmail API error: {e}")
        return set()

    senders = set()
    for msg_ref in messages:
        try:
            msg = service.users().messages().get(userId="me", id=msg_ref["id"], format="metadata", metadataHeaders=["From"]).execute()
            for h in msg.get("payload", {}).get("headers", []):
                if h.get("name", "").lower() == "from":
                    raw = h.get("value", "")
                    # Parse "Name <email@uw.edu>" or just "email@uw.edu"
                    match = re.search(r"[\w._%+-]+@[\w.-]+\.\w+", raw)
                    if match:
                        senders.add(match.group(0).lower())
                    break
        except Exception:
            continue
    return senders


def load_tracking_rows():
    if not os.path.exists(TRACKING_CSV):
        return [], []
    with open(TRACKING_CSV, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames or []
        rows = list(reader)
    return fieldnames, rows


def save_tracking(fieldnames, rows):
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(TRACKING_CSV, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)


def main(dry_run=False):
    if not os.path.exists(TRACKING_CSV):
        print(f"No tracking file at {TRACKING_CSV}. Run generate_faculty_emails.py first to create it.")
        return

    fieldnames, rows = load_tracking_rows()
    if not rows:
        print("Tracking CSV is empty. Nothing to update.")
        return

    print("Connecting to Gmail (read-only)...")
    service = get_gmail_service()
    if not service:
        return

    print("Listing recent inbox senders...")
    inbox_senders = list_inbox_sender_emails(service)

    updated = 0
    for row in rows:
        email_id = (row.get("email_id") or "").strip().lower()
        if not email_id:
            continue
        current_status = (row.get("status") or "").strip()
        if current_status:
            continue  # already has a status
        if email_id in inbox_senders:
            row["status"] = "Replied"
            updated += 1
            print(f"  -> Replied: {row.get('faculty_name')} ({email_id})")

    if dry_run:
        print(f"[DRY RUN] Would mark {updated} row(s) as Replied. Run without --dry-run to update CSV.")
        return

    if updated:
        save_tracking(fieldnames, rows)
        print(f"Updated {TRACKING_CSV}: {updated} row(s) set to status 'Replied'.")
    else:
        print("No new replies found. Status column unchanged.")


if __name__ == "__main__":
    dry_run = "--dry-run" in sys.argv
    main(dry_run=dry_run)

# cold_reach_faculty

Toolkit to scrape faculty listings, draft personalized cold emails with Gemini, send through Gmail, and optionally sync inbox replies into a tracking CSV. The codebase was built around University of Washington department pages, but you can adapt the scout scripts and CSV columns to your school.

## What is included

- **`scout/`** scripts that fetch faculty names, bios, and emails into `data/*_faculty_all.csv` files (you run these locally; CSVs are gitignored until you generate them).
- **`ghostwriter/daily_outreach.py`** selects a resume, drafts mail with Gemini, sends via Gmail, and appends `data/sent_log.csv` and `data/outreach_tracking.csv`.
- **`ghostwriter/check_inbox_and_update_tracker.py`** and **`ghostwriter/check_inbox_replies.py`** read Gmail (read-only OAuth) and update reply status in the tracker.
- **`scout/extract_resumes.py`** reads PDFs from `resume/` and writes `data/resumes_extracted.json` (gitignored).

## Requirements

- Python 3.10 or newer recommended
- A Google Cloud project with **Gmail API** enabled and a **Desktop** OAuth client downloaded as `credentials.json` in the project root
- A **Gemini API key** for drafting (`GEMINI_API_KEY`)

Install dependencies (from the repo root):

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Configuration

1. Copy **`.env.example`** to **`.env`** and set at least `GEMINI_API_KEY`. Optionally set `NOTIFICATION_EMAIL`, `OUTREACH_SIGN_NAME`, `OUTREACH_ROLE_LINE`, `OUTREACH_SKILLS_BLURB`, and `TEST_OUTREACH_EMAIL` (see the example file).
2. Download OAuth client JSON from Google Cloud and save it as **`credentials.json`** in the project root (never commit this file).
3. Add two PDFs under **`resume/`** named `resume_data_scientist.pdf` and `resume_data_engineering.pdf`, or point to your files with `data/resume_paths.json` (gitignored) as a map of those logical names to absolute paths.
4. Create faculty CSVs under **`data/`** using the column expectations in **`data/README.md`**, or run the relevant `scout/*.py` scripts.

First Gmail send or inbox check will open a browser; tokens are stored as **`token.json`** (send) and **`token_inbox.json`** (read-only inbox). Both are gitignored.

## Running outreach

Always run commands from the repository root.

Dry run (no Gmail send):

```bash
python ghostwriter/daily_outreach.py
```

Live send with daily logic:

```bash
python ghostwriter/daily_outreach.py --live
```

Send a test message to your own address (uses `TEST_OUTREACH_EMAIL` from `.env` unless you pass `--test`):

```bash
python ghostwriter/daily_outreach.py --test your-address@example.com
```

Optional wrapper:

```bash
chmod +x run_outreach.sh
./run_outreach.sh          # dry run
./run_outreach.sh 10       # live, up to 10 sends this run
```

## Inbox sync

From the repo root:

```bash
python ghostwriter/check_inbox_and_update_tracker.py
```

or:

```bash
python ghostwriter/check_inbox_replies.py
python ghostwriter/check_inbox_replies.py --dry-run
```

## Scheduled runs (macOS)

See **`com.user.outreach.plist.example`**. Copy it, replace the placeholder paths, install with `launchctl` as you would for any LaunchAgent, and point it at **`run_daily_outreach.sh`**. Set **`PYTHON_BIN`** in the environment if `python3` is not on the default PATH for launchd.

## Security

If you ever committed API keys or OAuth secrets, rotate them in Google Cloud and regenerate `credentials.json`. This repository’s `.gitignore` is meant to keep `.env`, tokens, resumes, and private CSV logs out of git.

## License

Use at your own risk. Respect your institution’s and each faculty member’s communication preferences, anti-spam rules, and applicable law.

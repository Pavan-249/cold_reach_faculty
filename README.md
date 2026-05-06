# cold_reach_faculty

Toolkit to scrape faculty listings, draft personalized cold emails with **Google Gemini**, send through **Gmail**, and optionally sync inbox replies into a tracking CSV. The scout scripts target some UW pages by default; you can adapt them to your school.

## Ollama: do you need it?

**No.** This repository does **not** install or require **Ollama**.

If you use `ghostwriter/daily_outreach.py`, the code can **optionally** call a local Ollama server (`http://localhost:11434`, model `llama3`) **only when** Gemini fails or reports quota exceeded. If you never install Ollama, drafting still works as long as Gemini is configured; you just will not get that automatic fallback.

To use the fallback later: install Ollama from [ollama.com](https://ollama.com), run `ollama pull llama3`, keep `ollama serve` running, then run outreach as usual.

---

## What you need before setup

| Item | Purpose |
|------|---------|
| Python 3.10+ | Run scripts |
| **Gemini API key** | Draft emails (`GEMINI_API_KEY` in `.env`) |
| **Gmail OAuth client** | Send mail and optional inbox sync (`credentials.json`) |
| Two resume PDFs | Attached to outreach emails (see below) |
| Faculty CSVs in `data/` | Built by `scout/` scripts or your own exports |

---

## Setup (step by step)

Do these from the **repository root** (the folder that contains `ghostwriter/` and `requirements.txt`).

### 1. Python environment

```bash
cd cold_reach_faculty
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Gemini API key

Gemini is used to draft subjects and bodies. Keys come from **Google AI Studio** (not the same file as Gmail `credentials.json`).

1. Open **[Google AI Studio](https://aistudio.google.com/apikey)** while signed into your Google account.
2. Click **Create API key** and choose or create a Google Cloud project if prompted.
3. Copy the key string.

Create your env file and paste the key:

```bash
cp .env.example .env
```

Edit `.env` and set:

```bash
GEMINI_API_KEY=paste_your_key_here
```

Save the file. The scripts load `.env` automatically when you run them from the project layout used in this repo (see `daily_outreach.py` / `generate_faculty_emails.py`).

**Check that the key works** (optional). After you save `.env` with `GEMINI_API_KEY`:

```bash
python scout/list_models.py
```

You should see a list of model names. If you see an error, confirm the key in `.env` and that your venv has `google-generativeai` installed.

### 3. Gmail API (send and optional inbox read)

Sending uses the Gmail API with OAuth. You need a **Desktop app** OAuth client JSON from Google Cloud.

1. Go to **[Google Cloud Console](https://console.cloud.google.com/)** and select or create a project.
2. **APIs and services** → **Library** → enable **Gmail API**.
3. **APIs and services** → **OAuth consent screen**: choose **External** (or Internal for Workspace), fill app name and your email, add scopes when asked:
   - For sending only, the app requests send scope when you run `daily_outreach.py`.
   - Inbox scripts use **read-only** Gmail scope and store a separate token file (`token_inbox.json`).
4. **APIs and services** → **Credentials** → **Create credentials** → **OAuth client ID** → Application type **Desktop app** → create.
5. Download the JSON and save it as **`credentials.json`** in the **project root** (same folder as `.env`).

**First run:** When you run live send or inbox sync, a browser opens to sign in and approve access. Tokens are saved locally:

- `token.json` … send mail (`daily_outreach.py`)
- `token_inbox.json` … read inbox (`check_inbox_*.py`)

Never commit `credentials.json` or these token files (they are in `.gitignore`).

### 4. Resumes

Place two PDFs under a **`resume/`** folder in the project root:

- `resume_data_scientist.pdf`
- `resume_data_engineering.pdf`

Or create **`data/resume_paths.json`** (gitignored) mapping those exact filenames to absolute paths on your machine. You can generate cached text with:

```bash
python scout/extract_resumes.py
```

### 5. Faculty data (`data/`)

CSV and JSON under `data/` are **not** committed to git. Create them locally:

- Run the relevant scripts in **`scout/`**, or
- Add your own CSVs following **`data/README.md`**.

Until those files exist, dry runs may print errors about missing faculty data.

### 6. Rest of `.env` (recommended)

Open `.env` and set copy used in prompts and tests:

- `OUTREACH_SIGN_NAME`, `OUTREACH_ROLE_LINE`, `OUTREACH_SKILLS_BLURB` … who you are and how you describe your skills (used in LLM prompts).
- `TEST_OUTREACH_EMAIL` … default address for `daily_outreach.py --test`.
- `NOTIFICATION_EMAIL` … optional; if set, `--live` can email you start or finish summaries.

See **`.env.example`** for all variable names.

---

## Running outreach

Always run from the **repository root** with your venv activated.

Dry run (no Gmail send):

```bash
python ghostwriter/daily_outreach.py
```

Live send:

```bash
python ghostwriter/daily_outreach.py --live
```

Send a test to yourself:

```bash
python ghostwriter/daily_outreach.py --test your-email@example.com
```

Wrapper script:

```bash
./run_outreach.sh          # dry run
./run_outreach.sh 10       # live, up to 10 sends this run
```

---

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

---

## Scheduled runs (macOS)

See **`com.user.outreach.plist.example`**. Copy it, replace placeholder paths, install with `launchctl`, and point it at **`run_daily_outreach.sh`**. Set **`PYTHON_BIN`** if `python3` is not on launchd’s PATH.

---

## Security

Rotate any API key or OAuth client secret that was ever exposed. Keep `.env`, `credentials.json`, and `token*.json` out of version control.

---

## License

Use at your own risk. Respect your institution’s policies, faculty preferences, anti-spam rules, and applicable law.

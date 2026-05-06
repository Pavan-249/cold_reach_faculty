#!/usr/bin/env python3
"""
Generate personalized email drafts for each faculty (dry run, no sending).
Writes one file per faculty under output/faculty_emails/.

Uses data/resume_paths.json for PDF paths (or data/resumes_extracted.json).
Requires GEMINI_API_KEY. Run from outreach_ra_profs_v1:
  python ghostwriter/generate_faculty_emails.py
"""
import os
import sys
import re
import json
import csv
import time
import requests
from datetime import datetime

# Load .env FIRST, using script location only (before any chdir)
_script_dir = os.path.dirname(os.path.abspath(__file__))
_project_root = os.path.dirname(_script_dir)
_env_path = os.path.join(_project_root, ".env")
if os.path.isfile(_env_path):
    try:
        with open(_env_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip().strip("\ufeff")  # BOM
                if not line or line.startswith("#"):
                    continue
                if "=" in line:
                    key, _, value = line.partition("=")
                    key = key.strip()
                    value = value.strip().strip("'\"")
                    if key and value:
                        os.environ.setdefault(key, value)
                        if key.upper() == "GEMINI_API_KEY":
                            os.environ["GEMINI_API_KEY"] = value  # SDK expects this exact name
    except Exception:
        pass

# Ensure we can import from project root
PROJECT_ROOT = _project_root
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)
if os.getcwd() != PROJECT_ROOT:
    os.chdir(PROJECT_ROOT)

OUTREACH_SIGN_NAME = (os.getenv("OUTREACH_SIGN_NAME") or "Your Name").strip()

# Config (must match daily_outreach)
DATA_DIR = "data"
ALLEN_CSV = os.path.join(DATA_DIR, "allen_faculty_all.csv")
ESCIENCE_CSV = os.path.join(DATA_DIR, "escience_faculty_all.csv")
RESUMES_EXTRACTED_JSON = os.path.join(DATA_DIR, "resumes_extracted.json")
RESUME_PATHS_JSON = os.path.join(DATA_DIR, "resume_paths.json")
RESUME_DATA_SCIENTIST = "resume_data_scientist.pdf"
RESUME_DATA_ENGINEERING = "resume_data_engineering.pdf"
ALLOWED_RESUMES = [RESUME_DATA_SCIENTIST, RESUME_DATA_ENGINEERING]
OUTPUT_DIR = "output/faculty_emails"
TRACKING_CSV = os.path.join(DATA_DIR, "outreach_tracking.csv")
TRACKING_COLUMNS = ["faculty_name", "department", "email_id", "date_email_sent", "status"]

# Gemini (no Gmail deps) — key is read from .env above
try:
    import google.generativeai as genai
    API_KEY = os.getenv("GEMINI_API_KEY")
    model = genai.GenerativeModel("gemini-flash-latest") if API_KEY else None
    if not API_KEY:
        print(f"Warning: GEMINI_API_KEY not set. Add to .env as: GEMINI_API_KEY=your_key")
        print(f"  (Looked for .env at: {_env_path})")
    else:
        print("Using GEMINI_API_KEY from .env")
except Exception as e:
    print(f"Warning: Could not load Gemini: {e}")
    model = None

try:
    from pypdf import PdfReader
except ImportError:
    PdfReader = None


def load_faculty(file_path):
    if not os.path.exists(file_path):
        return []
    with open(file_path, "r", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def load_resumes():
    """Load resume text from resume_paths.json (PDF paths), then resume/ folder, then resumes_extracted.json."""
    # 1) Try paths from config (e.g. Cursor workspace PDFs)
    if os.path.exists(RESUME_PATHS_JSON) and PdfReader:
        with open(RESUME_PATHS_JSON, "r", encoding="utf-8") as f:
            paths = json.load(f)
        result = {}
        for logical_name, path in paths.items():
            if logical_name not in ALLOWED_RESUMES:
                continue
            if os.path.exists(path):
                try:
                    reader = PdfReader(path)
                    text = "".join(p.extract_text() or "" for p in reader.pages)
                    result[logical_name] = text.strip()
                except Exception as e:
                    print(f"Warning: Could not read {path}: {e}")
            else:
                print(f"Warning: Resume path not found: {path}")
        if result:
            return result
    # 2) Try resume/ folder with expected filenames
    if PdfReader:
        resume_folder = "resume"
        if os.path.isdir(resume_folder):
            result = {}
            for fname in ALLOWED_RESUMES:
                path = os.path.join(resume_folder, fname)
                if os.path.exists(path):
                    try:
                        reader = PdfReader(path)
                        text = "".join(p.extract_text() or "" for p in reader.pages)
                        result[fname] = text.strip()
                    except Exception as e:
                        print(f"Warning: Could not read {path}: {e}")
            if result:
                return result
    # 3) Extracted JSON
    if os.path.exists(RESUMES_EXTRACTED_JSON):
        with open(RESUMES_EXTRACTED_JSON, "r", encoding="utf-8") as f:
            data = json.load(f)
        return {k: v for k, v in data.items() if k in ALLOWED_RESUMES} or data
    return {}


# Rate limit: ~6 RPM → wait 11s between LLM calls to stay under limit
LLM_DELAY_SECONDS = 11

def call_llm(prompt, delay_after=True):
    if not model:
        return None
    try:
        response = model.generate_content(prompt)
        out = response.text.strip() if response and response.text else None
        if delay_after and out is not None:
            time.sleep(LLM_DELAY_SECONDS)
        return out
    except Exception as e:
        print(f"  LLM error: {e}")
        return None


def select_best_resume(prof_bio, resumes_dict):
    allowed = {k: v for k, v in resumes_dict.items() if k in ALLOWED_RESUMES}
    if not allowed:
        return next(iter(resumes_dict.keys()), RESUME_DATA_SCIENTIST) if resumes_dict else RESUME_DATA_SCIENTIST
    if len(allowed) == 1:
        return next(iter(allowed.keys()))
    resume_summaries = ""
    for name, text in allowed.items():
        resume_summaries += f"Filename: {name}\nSnippet: {text[:1500]}\n---\n"
    prompt = f"""You are an expert academic advisor. The student has exactly TWO resumes. Select THE BEST ONE that fits the professor's research.

RESUMES:
1. {RESUME_DATA_SCIENTIST} – Data Scientist: ML/modeling, statistics, data visualization, experimentation.
2. {RESUME_DATA_ENGINEERING} – Data Engineering and Architecture: distributed systems, data pipelines, cloud, scalable data architecture.

RULES: ML/data science/analytics → "{RESUME_DATA_SCIENTIST}". Systems/pipelines/infrastructure → "{RESUME_DATA_ENGINEERING}". If unclear, prefer "{RESUME_DATA_SCIENTIST}".

Professor's Bio:
{prof_bio[:1500]}

Resumes:
{resume_summaries}

Return ONLY the exact filename of the best-fitting resume. No explanation."""
    content = call_llm(prompt, delay_after=True)
    if not content:
        return next(iter(allowed.keys()))
    selected = content.replace('"', '').replace("'", "").strip()
    if selected in allowed:
        return selected
    for key in allowed:
        if key in selected or selected in key:
            return key
    return next(iter(allowed.keys()))


def draft_cover_letter(prof, resume_text):
    if not model:
        return None, None
    source_context = "Allen School" if "Allen" in prof.get("source", "") else "eScience Institute"
    prompt = f"""You are an ambitious student reaching out to a professor for research opportunities.
I have two profiles: (1) Data Scientist and (2) Data Engineering and Architecture. The resume below is the one I selected for this professor. Draft a personalized, professional cover letter email that reflects that profile.

Professor: {prof['name']} at UW {source_context}
Professor's Bio: {prof.get('bio', '')[:1000]}
My Resume Content: {resume_text[:2000]}

Return your response ONLY in JSON format with "subject" and "body" fields. Tone: respectful and concise. Sign the body with the name '{OUTREACH_SIGN_NAME}' (or "Best regards, {OUTREACH_SIGN_NAME}")."""
    content = call_llm(prompt, delay_after=True)
    if not content:
        return None, None
    if "```json" in content:
        content = content.split("```json")[1].split("```")[0].strip()
    elif "```" in content:
        content = content.split("```")[1].split("```")[0].strip()
    start, end = content.find('{'), content.rfind('}')
    if start != -1 and end != -1:
        content = content[start:end+1]
    content = "".join(c for c in content if ord(c) >= 32 or c in "\n\r\t")
    try:
        data = json.loads(content)
        return data.get("subject"), data.get("body")
    except json.JSONDecodeError:
        sm = re.search(r'"subject":\s*"(.*?)"', content, re.DOTALL)
        bm = re.search(r'"body":\s*"(.*?)"', content, re.DOTALL)
        if sm and bm:
            return sm.group(1).replace("\\n", "\n"), bm.group(1).replace("\\n", "\n").replace('\\"', '"')
    return None, None


def extract_email_from_text(text):
    if not text:
        return None
    emails = re.findall(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.edu', text)
    for e in emails:
        if 'uw.edu' in e.lower():
            return e.lower()
    return emails[0].lower() if emails else None


def fetch_email_from_faculty_page(profile_link, timeout=15):
    """Verify email by fetching faculty profile page (e.g. UW Allen School)."""
    if not profile_link or not profile_link.strip().startswith("http"):
        return ""
    try:
        resp = requests.get(profile_link.strip(), timeout=timeout, headers={"User-Agent": "Mozilla/5.0 (compatible; OutreachBot/1.0)"})
        resp.raise_for_status()
        text = resp.text
        mailtos = re.findall(r'mailto:([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.edu)', text, re.I)
        for e in mailtos:
            e = e.split("?")[0].strip().lower()
            if "uw.edu" in e or "cs.washington" in e:
                return e
        if mailtos:
            return mailtos[0].split("?")[0].strip().lower()
        email_label = re.search(r'[Ee]mail\s*[:\s*]+\s*([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.edu)', text)
        if email_label:
            return email_label.group(1).strip().lower()
        full = re.search(r'([a-zA-Z0-9._%+-]+@(?:cs\.washington\.edu|uw\.edu))', text)
        if full:
            return full.group(1).strip().lower()
    except Exception:
        pass
    return ""


def infer_email_from_profile(prof):
    """If email is missing, infer a likely UW email from profile_link (e.g. .../faculty/akarlin -> akarlin@cs.washington.edu)."""
    profile_link = (prof.get("profile_link") or "").strip()
    if not profile_link:
        return ""
    # Get last path segment (e.g. akarlin from .../faculty/akarlin or .../people/yejin)
    parts = profile_link.rstrip("/").split("/")
    username = parts[-1] if parts else ""
    if not username or " " in username:
        return ""
    source = (prof.get("source") or "").lower()
    if "allen" in source or "cs.washington" in profile_link:
        return f"{username}@cs.washington.edu"
    if "escience" in source or "escience" in profile_link:
        return f"{username}@uw.edu"
    return f"{username}@uw.edu"


def sanitize_filename(name):
    s = re.sub(r'[^\w\s-]', '', name)
    s = re.sub(r'[-\s]+', '_', s).strip('_')
    return (s[:80] if s else "unknown") + ".md"


def ensure_tracking_csv():
    """Create tracking CSV with header if it doesn't exist."""
    os.makedirs(DATA_DIR, exist_ok=True)
    if not os.path.exists(TRACKING_CSV):
        with open(TRACKING_CSV, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(TRACKING_COLUMNS)


def _load_tracker_rows():
    """Load all tracker rows as list of dicts, or [] if missing."""
    if not os.path.exists(TRACKER_CSV):
        return []
    rows = []
    with open(TRACKER_CSV, "r", encoding="utf-8") as f:
        r = csv.DictReader(f)
        for row in r:
            rows.append({k: row.get(k, "") for k in TRACKING_COLUMNS})
    return rows


def _save_tracker_rows(rows):
    """Write tracker CSV from list of dicts."""
    ensure_tracking_csv()
    with open(TRACKER_CSV, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=TRACKING_COLUMNS)
        w.writeheader()
        for row in rows:
            w.writerow({k: row.get(k, "") for k in TRACKING_COLUMNS})


def _tracker_has_row(faculty_name, email_id):
    """Return True if tracker already has a row for this faculty (same name + email)."""
    rows = _load_tracker_rows()
    for row in rows:
        if row.get("faculty_name") == faculty_name and row.get("email_id") == (email_id or ""):
            return True
    return False


def append_to_tracking(faculty_name, department, email_id, date_email_sent="", status=""):
    """Append one row or update existing row with same faculty_name if email was missing."""
    ensure_tracking_csv()
    email_id = email_id or ""
    rows = _load_tracker_rows()

    # If we already have this faculty+email, skip
    for row in rows:
        if row.get("faculty_name") == faculty_name and row.get("email_id") == email_id:
            return

    # If we have this faculty with empty email, fill it in
    for row in rows:
        if row.get("faculty_name") == faculty_name and not (row.get("email_id") or "").strip():
            row["email_id"] = email_id
            row["department"] = department
            _save_tracker_rows(rows)
            return

    # New row
    rows.append({
        "faculty_name": faculty_name,
        "department": department,
        "email_id": email_id,
        "date_email_sent": date_email_sent,
        "status": status,
    })
    _save_tracker_rows(rows)


def main(limit=None):
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    allen = load_faculty(ALLEN_CSV)
    escience = load_faculty(ESCIENCE_CSV)
    for p in allen:
        p["source"] = p.get("source", "Allen")
    for p in escience:
        p["source"] = p.get("source", "eScience")
    faculty = allen + escience

    if limit is not None and limit > 0:
        faculty = faculty[:limit]

    if not faculty:
        print("No faculty found. Add data/allen_faculty_all.csv and/or data/escience_faculty_all.csv (or run scout scripts first).")
        return

    resumes_dict = load_resumes()
    if not resumes_dict:
        print("No resumes loaded. Check data/resume_paths.json (or put PDFs in resume/ and run scout/extract_resumes.py).")
        return

    print(f"Loaded {len(faculty)} faculty, {len(resumes_dict)} resume(s). Rate limit: 1 call every {LLM_DELAY_SECONDS}s. Writing to {OUTPUT_DIR}/")
    results = []

    for i, prof in enumerate(faculty):
        name = prof.get("name", "Unknown")
        bio = prof.get("bio", "")
        print(f"  [{i+1}/{len(faculty)}] {name}...", end=" ", flush=True)

        best_resume = select_best_resume(bio, resumes_dict)
        resume_text = resumes_dict.get(best_resume, "")
        subject, body = draft_cover_letter(prof, resume_text)

        if not subject or not body:
            print("SKIP (draft failed)")
            results.append({"name": name, "resume": best_resume, "skipped": True})
            continue

        profile_link = prof.get("profile_link", "").strip()
        email = (
            prof.get("email", "").strip()
            or extract_email_from_text(bio)
            or fetch_email_from_faculty_page(profile_link)
            or infer_email_from_profile(prof)
            or ""
        )

        fname = sanitize_filename(name)
        path = os.path.join(OUTPUT_DIR, fname)
        with open(path, "w", encoding="utf-8") as f:
            f.write(f"# Email draft: {name}\n\n")
            f.write(f"- **To:** {email or '(email not found)'}\n")
            f.write(f"- **Resume used:** {best_resume}\n")
            f.write(f"- **Generated:** {datetime.now().isoformat()}\n\n---\n\n")
            f.write(f"**Subject:** {subject}\n\n**Body:**\n\n{body}\n")

        # Append to tracking CSV (date_email_sent and status empty until we actually send / check inbox)
        department = prof.get("source", "Allen")
        append_to_tracking(
            faculty_name=name,
            department=department,
            email_id=email or "",
            date_email_sent="",
            status="",
        )

        print(f"OK -> {fname}")
        results.append({"name": name, "email": email or None, "resume_used": best_resume, "subject": subject, "file": fname})

    summary_path = os.path.join(OUTPUT_DIR, "_summary.json")
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump({"generated": datetime.now().isoformat(), "count": len(results), "drafts": results}, f, indent=2)
    print(f"\nDone. {len(results)} drafts in {OUTPUT_DIR}/. Summary: {summary_path}")
    if results:
        print(f"Tracking: appended {len(results)} rows to {TRACKING_CSV}")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Generate personalized cold emails for faculty (no sending).")
    parser.add_argument("--limit", type=int, default=None, help="Max number of faculty to process (default: all)")
    args = parser.parse_args()
    main(limit=args.limit)

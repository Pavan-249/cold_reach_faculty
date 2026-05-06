import csv
import os
import json
import time
import base64
from datetime import datetime
import google.generativeai as genai
import google.auth
# Gmail API imports
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from email.message import EmailMessage
import re
import requests
from html import escape as html_escape
from pypdf import PdfReader

# Configuration
ALLEN_CSV = "data/allen_faculty_all.csv"
ESCIENCE_CSV = "data/escience_faculty_all.csv"
BIOENG_CSV = "data/bioeng_faculty_all.csv"
UWMEDICINE_CSV = "data/uwmedicine_faculty_all.csv"
DIRAC_CSV = "data/dirac_faculty_all.csv"
URBANALYTICS_CSV = "data/urbanalytics_faculty_all.csv"
MISL_CSV = "data/misl_faculty_all.csv"
NOBLE_CSV = "data/noble_faculty_all.csv"
EICHLER_CSV = "data/eichler_faculty_all.csv"
ISCHOOL_CSV = "data/ischool_faculty_all.csv"
PUBLICHEALTH_CSV = "data/publichealth_faculty_all.csv"
POPULATIONHEALTH_CSV = "data/populationhealth_faculty_all.csv"
SENT_LOG_PATH = "data/sent_log.csv"
FAILED_LOG_PATH = "data/failed_outreach.csv"
RESUMES_EXTRACTED_JSON = "data/resumes_extracted.json"
RESUME_PATHS_JSON = "data/resume_paths.json"
TRACKER_CSV = "data/outreach_tracking.csv"
TRACKER_COLUMNS = ["faculty_name", "department", "email_id", "date_email_sent", "status"]
# Resolve paths relative to outreach project root so script works from any cwd (see check_inbox_and_update_tracker.py)
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOKEN_PATH = os.path.join(_PROJECT_ROOT, 'token.json')
CREDENTIALS_PATH = os.path.join(_PROJECT_ROOT, 'credentials.json')
DAILY_LIMIT_PER_SOURCE = 7
# If modifying these scopes, delete the file token.json.
SCOPES = ['https://www.googleapis.com/auth/gmail.send']

# Load .env so GEMINI_API_KEY is available (same pattern as generate_faculty_emails.py)
_env_path = os.path.join(_PROJECT_ROOT, ".env")
if os.path.isfile(_env_path):
    try:
        with open(_env_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip().strip("\ufeff")
                if not line or line.startswith("#"):
                    continue
                if "=" in line:
                    key, _, value = line.partition("=")
                    key = key.strip()
                    value = value.strip().strip("'\"")
                    if key and value:
                        os.environ.setdefault(key, value)
                        if key.upper() == "GEMINI_API_KEY":
                            os.environ["GEMINI_API_KEY"] = value
    except Exception:
        pass

NOTIFICATION_EMAIL = (os.getenv("NOTIFICATION_EMAIL") or "").strip()
OUTREACH_SIGN_NAME = (os.getenv("OUTREACH_SIGN_NAME") or "Your Name").strip()
OUTREACH_ROLE_LINE = (
    os.getenv("OUTREACH_ROLE_LINE") or "a graduate student in data science at your university"
).strip()
OUTREACH_SKILLS_BLURB = (
    os.getenv("OUTREACH_SKILLS_BLURB")
    or "Background in data science, data engineering, and analytics. Set OUTREACH_SKILLS_BLURB in .env."
).strip()

# Exactly two resumes: Data Scientist and Data Engineering/Architecture
RESUME_DATA_SCIENTIST = "resume_data_scientist.pdf"
RESUME_DATA_ENGINEERING = "resume_data_engineering.pdf"
ALLOWED_RESUMES = [RESUME_DATA_SCIENTIST, RESUME_DATA_ENGINEERING]

# Initialize Gemini
API_KEY = os.getenv("GEMINI_API_KEY")

if API_KEY:
    genai.configure(api_key=API_KEY)
    model = genai.GenerativeModel("gemini-flash-latest") # The identifier that actually works
    print("Using GEMINI_API_KEY from .env")
else:
    print("Warning: GEMINI_API_KEY not found. LLM features will be disabled.")
    model = None

def call_ollama(prompt):
    """Backup call to local Ollama (Llama3)."""
    try:
        url = "http://localhost:11434/api/generate"
        payload = {
            "model": "llama3",
            "prompt": prompt,
            "stream": False
        }
        response = requests.post(url, json=payload, timeout=90) # Increased timeout
        if response.status_code == 200:
            return response.json().get("response", "").strip()
        else:
            print(f"Ollama error: {response.status_code}")
            return None
    except Exception as e:
        print(f"Error calling Ollama: {e}")
        return None

GEMINI_EXHAUSTED = False

def call_gemini_with_retry(prompt, max_retries=3, initial_delay=10):
    global GEMINI_EXHAUSTED
    if model and not GEMINI_EXHAUSTED:
        for i in range(max_retries):
            try:
                response = model.generate_content(prompt)
                return response.text.strip()
            except Exception as e:
                if "429" in str(e) or "Quota exceeded" in str(e):
                    GEMINI_EXHAUSTED = True
                    print(f"Gemini quota exceeded. Falling back to Ollama for the rest of the session.")
                    break
                else:
                    print(f"Gemini API error: {e}")
                    break
    
    # Fallback to Ollama if Gemini fails or is disabled
    return call_ollama(prompt)

# Email validation: single source of truth for correctness. Reject invalid local parts, URLs, malformed addresses.
def is_valid_email(email):
    if not email or not isinstance(email, str):
        return False
    e = email.strip().lower()
    if "@" not in e or e.count("@") != 1:
        return False
    local, domain = e.split("@", 1)
    # Reject if local part looks like a URL or domain
    if "www." in e or ".com@" in e or ".org@" in e or ".edu@" in e or "http" in e or "//" in e:
        return False
    if "www." in local or ".com" in local or ".org" in local or ("." in local and len(local) > 20):
        return False
    # Local part: length and no spaces
    if len(local) < 2 or len(local) > 64 or " " in local:
        return False
    # Only valid local-part characters (no ~ or other invalid chars)
    if any(c not in "abcdefghijklmnopqrstuvwxyz0123456789._%+-" for c in local):
        return False
    # Cannot start or end with . - +
    if local[0] in ".-+" or local[-1] in ".-+":
        return False
    # No consecutive dots (common typo)
    if ".." in local:
        return False
    # Domain: institutional .edu
    if not (domain.endswith(".edu") or "washington.edu" in domain or "uw.edu" in domain):
        return False
    # Domain: no leading/trailing dot or hyphen, no consecutive dots
    domain = domain.strip(".-")
    if ".." in domain or not domain:
        return False
    return True


def is_uw_email(email):
    """True only if the address is at UW: @*.uw.edu or @*.washington.edu. Rejects @cs.ubc.ca, @mit.edu, etc."""
    if not email or not isinstance(email, str):
        return False
    e = email.strip().lower()
    if "@" not in e or e.count("@") != 1:
        return False
    _, domain = e.split("@", 1)
    domain = domain.strip(".-")
    if domain == "uw.edu":
        return True
    if domain.endswith(".uw.edu"):
        return True
    if domain == "washington.edu" or domain.endswith(".washington.edu"):
        return True
    return False


def extract_email_from_text(text):
    if not text:
        return None
    # Look for common email patterns, prioritizing @cs.uw.edu or @uw.edu
    emails = re.findall(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.edu', text)
    if emails:
        for e in emails:
            e = e.lower()
            if is_valid_email(e) and ("uw.edu" in e or "washington.edu" in e):
                return e
        for e in emails:
            if is_valid_email(e):
                return e.lower()
    return None

def load_processed_names(include_today_failures=True):
    """Names we have already sent to (from sent_log). Used to exclude them from to_send list."""
    processed = set()
    # Load successful sends (sent_log: name, email, date — no header)
    if os.path.exists(SENT_LOG_PATH):
        with open(SENT_LOG_PATH, "r") as f:
            reader = csv.reader(f)
            for row in reader:
                if len(row) >= 1 and row[0].strip() and row[0].lower() != "name":
                    processed.add(row[0].strip())
    
    # Load today's failures to skip them (skip when include_today_failures=False for manual retry)
    if include_today_failures and os.path.exists(FAILED_LOG_PATH):
        with open(FAILED_LOG_PATH, "r") as f:
            reader = csv.DictReader(f)
            today = datetime.now().strftime("%Y-%m-%d")
            for row in reader:
                if row["date"] == today:
                    processed.add(row["name"])
    return processed

def load_sent_emails():
    """Return set of email addresses we have already sent to (from sent_log). Cross-check before every send to avoid duplicate emails."""
    sent_emails = set()
    if os.path.exists(SENT_LOG_PATH):
        with open(SENT_LOG_PATH, "r") as f:
            reader = csv.reader(f)
            for row in reader:
                if len(row) >= 2 and row[1].strip() and "@" in row[1] and row[1].lower() != "email":
                    sent_emails.add(row[1].strip().lower())
    return sent_emails

def update_sent_log(name, email):
    with open(SENT_LOG_PATH, "a", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([name, email, datetime.now().strftime("%Y-%m-%d")])

def log_failed_outreach(name, email, bio_link, reason):
    if not os.path.exists(FAILED_LOG_PATH):
        with open(FAILED_LOG_PATH, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["name", "email", "bio_link", "reason", "date"])
    
    with open(FAILED_LOG_PATH, "a", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([name, email, bio_link, reason, datetime.now().strftime("%Y-%m-%d")])

def load_faculty(file_path):
    if not os.path.exists(file_path):
        return []
    with open(file_path, "r", encoding="utf-8") as f:
        return list(csv.DictReader(f))

def fetch_email_from_faculty_page(profile_link, timeout=15):
    """
    Verify email by fetching the faculty profile page and extracting it.
    Looks for mailto: links and 'Email:' lines (e.g. UW Allen School pages).
    For eScience: people pages often lack email; try the /member/ URL instead of /people/.
    """
    if not profile_link or not profile_link.strip().startswith("http"):
        return ""
    link = profile_link.strip()
    urls_to_try = [link]
    if "escience.washington.edu/people/" in link:
        member_link = link.replace("/people/", "/member/")
        urls_to_try.append(member_link)
    for url in urls_to_try:
        try:
            resp = requests.get(url, timeout=timeout, headers={"User-Agent": "Mozilla/5.0 (compatible; OutreachBot/1.0)"})
            resp.raise_for_status()
            text = resp.text
            # mailto: links first (then validate: no ~, valid local part)
            mailtos = re.findall(r'mailto:([^\s"\'<>]+@[a-zA-Z0-9.-]+\.edu)', text, re.I)
            for raw in mailtos:
                e = raw.split("?")[0].strip().lower()
                if is_valid_email(e) and ("uw.edu" in e or "cs.washington" in e):
                    return e
            for raw in mailtos:
                e = raw.split("?")[0].strip().lower()
                if is_valid_email(e):
                    return e
            # "Email:" or "email:**" followed by address (Allen School format)
            email_label = re.search(r'[Ee]mail\s*[:\s*]+\s*([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.edu)', text)
            if email_label:
                e = email_label.group(1).strip().lower()
                if is_valid_email(e):
                    return e
            # Any @cs.washington.edu or @uw.edu in page
            full = re.search(r'([a-zA-Z0-9._%+-]+@(?:cs\.washington\.edu|uw\.edu))', text)
            if full:
                e = full.group(1).strip().lower()
                if is_valid_email(e):
                    return e
        except Exception:
            continue
    return ""

def infer_email_from_profile(prof):
    """Fallback: infer likely UW email from profile_link when scrape and CSV are empty. Reject URL-like slugs."""
    profile_link = (prof.get("profile_link") or "").strip()
    if not profile_link:
        return ""
    parts = profile_link.rstrip("/").split("/")
    username = (parts[-1] or "").strip()
    # Do not infer if last segment looks like a domain or URL (e.g. www.thaisaway.com, faculty-profiles)
    if not username or " " in username or len(username) > 40:
        return ""
    if "www." in username.lower() or ".com" in username.lower() or ".org" in username.lower():
        return ""
    if username.startswith("http") or "?" in username or "=" in username:
        return ""
    # Verify local part would be valid: only allow valid email local-part characters (no ~ or other invalid chars)
    # Do not strip or guess – if slug has invalid chars (e.g. ~miklau), return "" and rely on CSV/profile fetch
    if any(c not in "abcdefghijklmnopqrstuvwxyz0123456789._%+-" for c in username):
        return ""
    if username[0] in ".-+" or username[-1] in ".-+":
        return ""
    source = (prof.get("source") or "").lower()
    if "allen" in source or "cs.washington" in profile_link:
        return f"{username}@cs.washington.edu"
    if "escience" in source or "escience" in profile_link:
        return f"{username}@uw.edu"
    if "bioeng" in source or "bioe.uw" in profile_link:
        return f"{username}@uw.edu"
    if "medicine" in source or "medicine.uw" in profile_link:
        return f"{username}@uw.edu"
    if "dirac" in source or "astro.washington" in profile_link:
        return f"{username}@uw.edu"
    if "urbanalytics" in source or "urbanalytics" in profile_link:
        return f"{username}@uw.edu"
    if "misl" in source or "misl.cs" in profile_link:
        return f"{username}@cs.washington.edu"
    if "noble" in source or "noble.gs" in profile_link:
        return f"{username}@gs.washington.edu"
    if "eichler" in source or "eichler.gs" in profile_link:
        return f"{username}@gs.washington.edu"
    if "public" in source or "sph.washington" in profile_link:
        return f"{username}@uw.edu"
    if "healthdata.org" in profile_link or "people-faculty" in username:
        return ""  # IHME directory page has no per-person slug; do not infer
    if "globalhealth.uw.edu" in profile_link:
        return f"{username}@uw.edu"
    return f"{username}@uw.edu"

def get_resume_attachment_path(best_resume_name):
    """Return path to PDF for attachment: use resume_paths.json first, else resume/ folder."""
    if os.path.exists(RESUME_PATHS_JSON):
        with open(RESUME_PATHS_JSON, "r", encoding="utf-8") as f:
            paths = json.load(f)
        p = paths.get(best_resume_name)
        if p and os.path.exists(p):
            return p
    return os.path.join("resume", best_resume_name)

def _load_tracker_rows():
    if not os.path.exists(TRACKER_CSV):
        return []
    rows = []
    with open(TRACKER_CSV, "r", encoding="utf-8") as f:
        r = csv.DictReader(f)
        for row in r:
            rows.append({k: row.get(k, "") for k in TRACKER_COLUMNS})
    return rows

def _save_tracker_rows(rows):
    os.makedirs(os.path.dirname(TRACKER_CSV), exist_ok=True)
    with open(TRACKER_CSV, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=TRACKER_COLUMNS)
        w.writeheader()
        for row in rows:
            w.writerow({k: row.get(k, "") for k in TRACKER_COLUMNS})

def update_tracker_on_send(faculty_name, department, email_id, date_sent):
    """Add or update tracker row with date_email_sent when we send."""
    rows = _load_tracker_rows()
    for row in rows:
        if row.get("faculty_name") == faculty_name and row.get("email_id", "").strip().lower() == email_id.strip().lower():
            row["date_email_sent"] = date_sent
            row["department"] = department
            _save_tracker_rows(rows)
            return
    for row in rows:
        if row.get("faculty_name") == faculty_name and not (row.get("email_id") or "").strip():
            row["email_id"] = email_id
            row["department"] = department
            row["date_email_sent"] = date_sent
            _save_tracker_rows(rows)
            return
    rows.append({
        "faculty_name": faculty_name,
        "department": department,
        "email_id": email_id,
        "date_email_sent": date_sent,
        "status": "",
    })
    _save_tracker_rows(rows)

def load_resumes():
    """Load resume text. If data/resume_paths.json exists, read PDFs from those paths; else use data/resumes_extracted.json."""
    if os.path.exists(RESUME_PATHS_JSON):
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
    if not os.path.exists(RESUMES_EXTRACTED_JSON):
        return {}
    with open(RESUMES_EXTRACTED_JSON, "r", encoding="utf-8") as f:
        return json.load(f)

def select_best_resume(prof_bio, resumes_dict):
    """Choose between exactly two resumes: Data Scientist vs Data Engineering/Architecture."""
    # Restrict to allowed resumes only
    allowed = {k: v for k, v in resumes_dict.items() if k in ALLOWED_RESUMES}
    if not allowed:
        return RESUME_DATA_SCIENTIST if RESUME_DATA_SCIENTIST in resumes_dict else next(iter(resumes_dict.keys()), RESUME_DATA_SCIENTIST)
    if len(allowed) == 1:
        return next(iter(allowed.keys()))

    if not model:
        return next(iter(allowed.keys()))

    resume_summaries = ""
    for name, text in allowed.items():
        resume_summaries += f"Filename: {name}\nSnippet: {text[:1500]}\n---\n"

    prompt = f"""
    You are an expert academic advisor helping a graduate student find a Research Assistant (RA) position at the University of Washington.
    The student has exactly TWO resumes. Select THE BEST ONE that fits the professor's research interests.

    RESUMES:
    1. {RESUME_DATA_SCIENTIST} – Data Scientist: ML/modeling, statistics, data visualization, experimentation.
    2. {RESUME_DATA_ENGINEERING} – Data Engineering and Architecture: distributed systems, data pipelines, cloud, scalable data architecture, big data, structuring data.

    RULES:
    - Prefer "{RESUME_DATA_ENGINEERING}" when the professor's work involves: big data, data pipelines, data architecture, structuring/organizing data, data infrastructure, or scalable systems.
    - If the professor's work is mainly ML, data science, analytics, or experimentation (and not pipelines/architecture) → return "{RESUME_DATA_SCIENTIST}".
    - If the professor's work is mainly systems, infrastructure, data pipelines, architecture, or big data → return "{RESUME_DATA_ENGINEERING}".
    - If both fit, prefer "{RESUME_DATA_ENGINEERING}" when pipelines/architecture/big data are mentioned. If unclear, prefer "{RESUME_DATA_SCIENTIST}".

    Professor's Bio:
    {prof_bio[:1500]}

    Resumes (Filename & Content):
    {resume_summaries}

    Return ONLY the exact filename of the best-fitting resume. No explanation.
    """
    try:
        content = call_gemini_with_retry(prompt)
        if not content:
            return next(iter(allowed.keys()))
        selected = content.replace('"', '').replace("'", "").strip()
        if selected in allowed:
            return selected
        for key in allowed.keys():
            if key in selected or selected in key:
                return key
        return next(iter(allowed.keys()))
    except Exception as e:
        print(f"Error selecting best resume: {e}")
        return next(iter(allowed.keys()))


def _subject_blocklist_tokens():
    """Lowercase tokens that should not dominate the subject line (your name, etc.)."""
    tokens = []
    extra = os.getenv("OUTREACH_SUBJECT_BLOCKLIST") or ""
    for part in extra.split(","):
        w = part.strip().lower().strip("., ")
        if len(w) >= 3:
            tokens.append(w)
    for w in OUTREACH_SIGN_NAME.split():
        w = w.strip().lower().strip("., ")
        if len(w) >= 3:
            tokens.append(w)
    return tokens


def _is_bad_subject(subject):
    """Reject subject lines that are about the candidate (self-intro) instead of the professor."""
    if not subject or not isinstance(subject, str):
        return True
    t = subject.strip().lower()
    if "introduction to" in t:
        return True
    for tok in _subject_blocklist_tokens():
        if tok in t and "professor" not in t and "dr." not in t:
            return True
    if "ms data science student" in t or ("ms data science" in t and "student" in t):
        return True
    return False


def _contains_filler_placeholder(text):
    """Validation: return True if text contains any filler/placeholder (strictly prohibited in sent emails)."""
    if not text or not isinstance(text, str):
        return False
    t = text.lower()
    # Explicit instruction-style placeholders
    if "[insert" in t or "[add " in t or "[specific topic" in t or "[specific phrase" in t:
        return True
    if "[last name]" in t or "[name]" in t or "[their work]" in t or "[research area]" in t:
        return True
    if "phrase from" in t and ("bio" in t or "e.g." in t) and "[" in t:
        return True
    # Any [...] that contains instruction words
    for m in re.finditer(r"\[([^\]]*)\]", text):
        inner = m.group(1).lower()
        if any(x in inner for x in ("insert", "add ", "e.g.", "example", "specific topic", "specific phrase", "last name", "their work", "research area")):
            return True
    # Unclosed [ followed by instruction (e.g. "[insert specific topic or phrase from Professor X's bio, e.g.,")
    if re.search(r"\[[^\]]{0,120}(?:insert|add|specific topic|phrase from[^\]]*bio\s*,?\s*e\.g\.)", t):
        return True
    # Any remaining bracketed placeholder (catch-all for [something])
    if re.search(r"\[[^\]]*\]", text):
        return True
    return False


def draft_cover_letter(prof, resume_text):
    if not model:
        return None, None
    
    source_map = {
        "Allen": "Allen School of Computer Science",
        "eScience": "eScience Institute",
        "Bioengineering": "Department of Bioengineering",
        "UW Medicine": "UW Medicine / Department of Medicine",
        "DiRAC": "DiRAC Institute (Astrophysics & Cosmology)",
        "Urbanalytics": "Urbanalytics Data Studio",
        "MISL": "Molecular Information Systems Lab (MISL)",
        "Noble Lab": "Noble Research Lab (Genome Sciences)",
        "Eichler Lab": "Eichler Lab (Genome Sciences)",
        "Information School": "Information School (iSchool)",
        "Public Health": "School of Public Health",
        "Hans Rosling Center": "Hans Rosling Center for Population Health",
    }
    prof_source = prof.get("source", "")
    source_context = next((v for k, v in source_map.items() if k in prof_source), prof_source or "University of Washington")

    prompt = f"""
    Draft a short, simple email from {OUTREACH_ROLE_LINE} ({OUTREACH_SIGN_NAME}) to a professor. Use the professor's bio to mention their real research; keep language plain and natural.

    CANDIDATE (honest fit): {OUTREACH_SKILLS_BLURB} Do not claim expertise you do not have; for unfamiliar domains, say you are eager to learn and contribute with data and engineering skills.

    Professor: {prof['name']} at UW {source_context}
    Professor's Bio: {prof.get('bio', '')[:1000]}
    My Resume Content (for the selected profile): {resume_text[:2000]}

    Return ONLY JSON with 'subject' and 'body'. Address professor by first name (for example "Dear Tania,").

    TONE: Keep it simple and human. Do NOT sound like AI or a template.
    - Good opening: one sentence introducing who you are ({OUTREACH_ROLE_LINE}), then a concrete sentence tied to a real topic from their bio (no bracketed placeholders).
    - Then 1-2 short paragraphs: one on their specific research from the bio (name real topics), one on how your skills could help. End with one line offering to discuss and "Thank you for considering my inquiry." Sign with "Best regards, {OUTREACH_SIGN_NAME}" or similar.
    - Avoid: "I am reaching out to express my interest in exploring research opportunities", "I would be thrilled to discuss", "aligns with your research interests", long or flowery sentences. Prefer short, clear sentences.

    OPENING: Use concrete details FROM the bio (lab or center name, real research areas). Do not use generic phrases unless they appear in the bio.
    PROHIBITED: Any bracketed placeholders like [insert...]. Use only real content from the bio.

    SUBJECT LINE (critical): The subject must be ABOUT THE PROFESSOR and their work, not about you.
    - Good: "Professor Smith"; or "Expression of interest in working with Professor X on" plus a real topic from their bio.
    - Also fine: a question subject that names a real project from their bio, or "Research inquiry" plus the professor's real name.
    - FORBIDDEN: "Introduction to {OUTREACH_SIGN_NAME}", "MS Data Science Student", or any subject that centers on the candidate. Never use your name or "introduction to" as the subject.
    """
    try:
        content = call_gemini_with_retry(prompt)
        if not content:
            return None, None
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0].strip()
        elif "```" in content:
            content = content.split("```")[1].split("```")[0].strip()
        def clean_json_string(s):
            start = s.find('{')
            end = s.rfind('}')
            if start != -1 and end != -1:
                s = s[start:end+1]
            return "".join(char for char in s if ord(char) >= 32 or char in "\n\r\t")
        cleaned_content = clean_json_string(content)
        try:
            data = json.loads(cleaned_content)
        except json.JSONDecodeError:
            subject_match = re.search(r'"subject":\s*"(.*?)"', cleaned_content, re.DOTALL)
            body_match = re.search(r'"body":\s*"(.*?)"', cleaned_content, re.DOTALL)
            if subject_match and body_match:
                data = {
                    "subject": subject_match.group(1).replace("\\n", "\n").replace('\\"', '"'),
                    "body": body_match.group(1).replace("\\n", "\n").replace('\\"', '"')
                }
            else:
                return None, None
        if "Dear Prof." in data["body"] and "I'm interested in your work" in data["body"] and len(data["body"]) < 100:
            return None, None
        subject = (data["subject"] or "").replace("\u2014", "-").replace("\u2013", "-")
        body = (data["body"] or "").replace("\u2014", "-").replace("\u2013", "-")

        if _contains_filler_placeholder(subject) or _contains_filler_placeholder(body):
            print(f"Rejecting draft for {prof.get('name', '?')}: subject or body contained filler/placeholder (e.g. [insert...], [specific topic...]).")
            return None, None
        if _is_bad_subject(subject):
            print(f"Rejecting draft for {prof.get('name', '?')}: subject is self-intro or candidate-focused. Subject must be about the professor.")
            return None, None
        return subject, body
    except Exception as e:
        print(f"Error drafting cover letter for {prof.get('name', '?')}: {e}")
        return None, None

def get_gmail_service():
    creds = None
    if os.path.exists(TOKEN_PATH):
        creds = Credentials.from_authorized_user_file(TOKEN_PATH, SCOPES)
    
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_PATH, SCOPES)
            creds = flow.run_local_server(port=0)
        
        with open(TOKEN_PATH, 'w') as token:
            token.write(creds.to_json())
    
    return build('gmail', 'v1', credentials=creds)


def notify_run_email(service, subject, body, attachment_path=None):
    """Send summary to NOTIFICATION_EMAIL if configured."""
    if not NOTIFICATION_EMAIL:
        print("Skipping summary email (set NOTIFICATION_EMAIL in .env to enable).")
        return
    send_email(service, NOTIFICATION_EMAIL, subject, body, attachment_path=attachment_path)


def unwrap_email_body(body):
    """Unwrap lines so each paragraph is one long line. Email clients then reflow text to full width."""
    if not body or not isinstance(body, str):
        return body or ""
    paragraphs = body.split("\n\n")
    unwrapped = []
    for p in paragraphs:
        line = " ".join(p.split())
        if line:
            unwrapped.append(line)
    return "\n\n".join(unwrapped)


def _body_to_html(plain_body):
    """Convert plain body to HTML with full-width layout (no narrow column)."""
    if not plain_body:
        return ""
    paragraphs = [p.strip() for p in plain_body.split("\n\n") if p.strip()]
    # No max-width so content fills viewport like conventional email
    parts = [
        '<html><head><meta charset="utf-8"></head>',
        '<body style="margin:0; padding:0; max-width:100%; width:100%;">',
    ]
    for p in paragraphs:
        parts.append(f'<p style="margin:0 0 1em 0; max-width:100%;">{html_escape(p)}</p>')
    parts.append("</body></html>")
    return "\n".join(parts)


def send_email(service, to_email, subject, body, attachment_path=None, max_retries=3):
    """Sends an email with optional attachment and retry logic. Uses plain + HTML for full-width display."""
    body = unwrap_email_body(body)
    html_body = _body_to_html(body)
    for i in range(max_retries):
        try:
            message = EmailMessage()
            message.set_content(body)
            if html_body:
                message.add_alternative(html_body, subtype="html")
            message["To"] = to_email
            message["Subject"] = subject

            if attachment_path and os.path.exists(attachment_path):
                with open(attachment_path, 'rb') as f:
                    file_data = f.read()
                    file_name = os.path.basename(attachment_path)
                message.add_attachment(
                    file_data,
                    maintype='application',
                    subtype='pdf',
                    filename=file_name
                )

            # encoded message
            encoded_message = base64.urlsafe_b64encode(message.as_bytes()).decode()

            create_message = {
                'raw': encoded_message
            }
            
            send_message = (service.users().messages().send(userId="me", body=create_message).execute())
            print(f'Email successfully sent to {to_email}. Message Id: {send_message["id"]}')
            return True
        except Exception as e:
            if i < max_retries - 1:
                wait_time = 5 * (i + 1)
                print(f"Transient error sending to {to_email}: {e}. Retrying in {wait_time}s...")
                time.sleep(wait_time)
            else:
                print(f"Final failure sending to {to_email} after {max_retries} attempts: {e}")
                return False

# Source keyword → CSV constant mapping (for --source CLI flag)
SOURCE_CSV_MAP = {
    "allen":         ALLEN_CSV,
    "escience":      ESCIENCE_CSV,
    "bioeng":        BIOENG_CSV,
    "uwmedicine":    UWMEDICINE_CSV,
    "dirac":         DIRAC_CSV,
    "urbanalytics":  URBANALYTICS_CSV,
    "misl":          MISL_CSV,
    "noble":         NOBLE_CSV,
    "eichler":       EICHLER_CSV,
    "ischool":       ISCHOOL_CSV,
    "publichealth":  PUBLICHEALTH_CSV,
    "populationhealth": POPULATIONHEALTH_CSV,
}

def daily_outreach(dry_run=True, test_email_only=None, limit_override=None, source_filter=None, sources_list=None):
    """Run outreach. If source_filter is set, only that source. If sources_list is set (e.g. ['ischool','escience','noble','uwmedicine']), round-robin across those only."""
    # When limit_override is set (manual run), allow retrying today's failures
    sent_names = load_processed_names(include_today_failures=not limit_override)
    allen_faculty = load_faculty(ALLEN_CSV)
    escience_faculty = load_faculty(ESCIENCE_CSV)
    bioeng_faculty = load_faculty(BIOENG_CSV)
    uwmedicine_faculty = load_faculty(UWMEDICINE_CSV)
    dirac_faculty = load_faculty(DIRAC_CSV)
    urbanalytics_faculty = load_faculty(URBANALYTICS_CSV)
    misl_faculty = load_faculty(MISL_CSV)
    noble_faculty = load_faculty(NOBLE_CSV)
    eichler_faculty = load_faculty(EICHLER_CSV)
    ischool_faculty = load_faculty(ISCHOOL_CSV)
    publichealth_faculty = load_faculty(PUBLICHEALTH_CSV)
    populationhealth_faculty = load_faculty(POPULATIONHEALTH_CSV)
    all_resumes = load_resumes()
    # Use only the two allowed resumes
    resumes_dict = {k: v for k, v in all_resumes.items() if k in ALLOWED_RESUMES}
    if not resumes_dict:
        resumes_dict = all_resumes  # fallback if names don't match

    today_success_count = 0
    if os.path.exists(SENT_LOG_PATH):
        with open(SENT_LOG_PATH, "r") as f:
            reader = csv.DictReader(f)
            today = datetime.now().strftime("%Y-%m-%d")
            for row in reader:
                if row.get("date_sent") == today:
                    today_success_count += 1
    
    if limit_override:
         target_successes_needed = limit_override
         print(f"Manual override: Sending {limit_override} more emails regardless of daily quota.")
    else:
         target_successes_needed = 14 - today_success_count
         print(f"Total successes today: {today_success_count}. Target: 14. Need {target_successes_needed} more.")
         
         if target_successes_needed <= 0:
            print("Today's target already reached!")
    
    service = None
    if not dry_run or test_email_only:
        print("Authenticating with Gmail...")
        service = get_gmail_service()
    
    # Notify start of run (always send if live or test-notify)
    is_scheduled_run = not dry_run and not test_email_only
    force_notify = hasattr(sys, '_test_notify')
    
    if is_scheduled_run or force_notify:
        start_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        goal_msg = f"Goal: Send {limit_override} more emails." if limit_override else "Goal: Reach a total of 14 successes today."
        
        notify_run_email(
            service,
            f"Outreach Started: {datetime.now().strftime('%Y-%m-%d')}",
            f"The daily faculty outreach process started at {start_time}.\n{goal_msg}\nCurrent successes: {today_success_count}.\nNeed {max(0, target_successes_needed)} more.",
        )

    if not limit_override and target_successes_needed <= 0:
        print("Today's target already reached!")
        if is_scheduled_run or force_notify:
            # Send final report immediately since no work needed
            notify_run_email(
                service,
                f"Outreach Completed (Already Done): {datetime.now().strftime('%Y-%m-%d')}",
                f"The daily faculty outreach process checked at {datetime.now().strftime('%H:%M:%S')} and found the target of 14 emails was already reached for today.",
                attachment_path=SENT_LOG_PATH,
            )
        return

    if not resumes_dict:
        print("Error: No resumes found. Run extract_resumes.py and ensure resume/ contains resume_data_scientist.pdf and resume_data_engineering.pdf.")
        return
    # ── Source filter: if set, replace all_sources with just that CSV ──
    if source_filter:
        filter_csv = SOURCE_CSV_MAP.get(source_filter.lower())
        if not filter_csv:
            print(f"Unknown source '{source_filter}'. Valid options: {list(SOURCE_CSV_MAP.keys())}")
            return
        filtered = load_faculty(filter_csv)
        print(f"Source filter '{source_filter}': {len(filtered)} records from {filter_csv}")
        allen_faculty = filtered if source_filter == "allen" else []
        escience_faculty = filtered if source_filter == "escience" else []
        bioeng_faculty = filtered if source_filter == "bioeng" else []
        uwmedicine_faculty = filtered if source_filter == "uwmedicine" else []
        dirac_faculty = filtered if source_filter == "dirac" else []
        urbanalytics_faculty = filtered if source_filter == "urbanalytics" else []
        misl_faculty = filtered if source_filter == "misl" else []
        noble_faculty = filtered if source_filter == "noble" else []
        eichler_faculty = filtered if source_filter == "eichler" else []
        ischool_faculty = filtered if source_filter == "ischool" else []
        publichealth_faculty = filtered if source_filter == "publichealth" else []
        populationhealth_faculty = filtered if source_filter == "populationhealth" else []

    to_send = []

    STUDENT_KEYWORDS = ["graduate student", "phd student", "doctoral student", "postdoctoral", "postdoc"]

    # Relevance filter: prefer faculty whose work touches big data / data engineering / informatics / analytics / platforms
    RELEVANCE_KEYWORDS = [
        "big data", "data engineering", "data architecture", "data pipeline", "data platform",
        "informatics", "biomedical informatics", "health informatics", "clinical informatics",
        "streaming", "batch process", "batch processing", "real-time data", "data infrastructure",
        "analytics", "data science", "machine learning", " statistical ", "data management",
        "distributed system", "scalable", "data integration", "data warehouse", "etl",
        "visualization", "data viz", "computational", "database", "data system",
    ]

    def is_student(prof):
        bio = prof.get("bio", "").lower()
        return any(kw in bio for kw in STUDENT_KEYWORDS)

    def is_relevant(prof):
        """True if faculty bio/source suggests work in big data, data engineering, informatics, analytics, or platforms."""
        text = (prof.get("bio", "") + " " + prof.get("source", "")).lower()
        return any(kw in text for kw in RELEVANCE_KEYWORDS)

    # Map source name -> faculty list for multi-source round-robin
    SOURCE_TO_LIST = {
        "allen": allen_faculty, "escience": escience_faculty, "bioeng": bioeng_faculty,
        "uwmedicine": uwmedicine_faculty, "dirac": dirac_faculty, "urbanalytics": urbanalytics_faculty,
        "misl": misl_faculty, "noble": noble_faculty, "eichler": eichler_faculty, "ischool": ischool_faculty,
        "publichealth": publichealth_faculty,
        "populationhealth": populationhealth_faculty,
    }

    if sources_list:
        # Round-robin across specified sources only; skip already-sent and apply relevance
        pool_size = limit_override if limit_override else (target_successes_needed * 2)
        lists_by_source = []
        for s in sources_list:
            s = s.strip().lower()
            if s in SOURCE_TO_LIST and SOURCE_TO_LIST[s]:
                lists_by_source.append(SOURCE_TO_LIST[s])
        if not lists_by_source:
            print(f"No valid faculty lists for sources: {sources_list}. Valid: {list(SOURCE_CSV_MAP.keys())}")
            return
        indices = [0] * len(lists_by_source)
        skip_student = bool(source_filter)
        while len(to_send) < pool_size:
            added_any = False
            for idx, src in enumerate(lists_by_source):
                if len(to_send) >= pool_size:
                    break
                while indices[idx] < len(src):
                    prof = src[indices[idx]]
                    indices[idx] += 1
                    if prof["name"] not in sent_names and (skip_student or not is_student(prof)) and is_relevant(prof):
                        to_send.append(prof)
                        added_any = True
                        break
            if not added_any:
                break
        print(f"Round-robin across {sources_list}: {len(to_send)} candidates (skipping {len(sent_names)} already-sent)")

    elif test_email_only:
        if limit_override:
            # Test batch: up to limit_override faculty, same pool order; skip already-sent, apply relevance filter
            candidate_pool_size = limit_override
            count = 0
            for prof in allen_faculty:
                if count >= candidate_pool_size:
                    break
                if prof["name"] not in sent_names and is_relevant(prof):
                    to_send.append(prof)
                    count += 1
            for prof in escience_faculty:
                if count >= candidate_pool_size:
                    break
                if prof["name"] not in sent_names and is_relevant(prof):
                    to_send.append(prof)
                    count += 1
            new_sources = [
                bioeng_faculty, uwmedicine_faculty, dirac_faculty,
                urbanalytics_faculty, misl_faculty, noble_faculty, eichler_faculty, ischool_faculty, publichealth_faculty, populationhealth_faculty
            ]
            source_indices = [0] * len(new_sources)
            while len(to_send) < candidate_pool_size:
                added_any = False
                for idx, src in enumerate(new_sources):
                    if len(to_send) >= candidate_pool_size:
                        break
                    if source_indices[idx] < len(src):
                        prof = src[source_indices[idx]]
                        source_indices[idx] += 1
                        if prof["name"] not in sent_names and is_relevant(prof):
                            to_send.append(prof)
                            added_any = True
                if not added_any:
                    break
            print(f"TEST BATCH: Sending up to {len(to_send)} emails to {test_email_only} (skipping {len(sent_names)} already-sent)")
        else:
            # Single test: one professor (first not already sent to)
            all_sources = allen_faculty or escience_faculty or bioeng_faculty or uwmedicine_faculty or dirac_faculty or ischool_faculty or publichealth_faculty or populationhealth_faculty
            first_unsent = next((p for p in all_sources if p["name"] not in sent_names and is_relevant(p)), None)
            to_send = [first_unsent] if first_unsent else []
            print(f"TEST MODE: Sending 1 email to {test_email_only} for {to_send[0]['name']}" if to_send else "TEST MODE: No unsent, relevant faculty found.")
    elif source_filter:
        # Single source targeted (e.g. --source publichealth): use that list only, skip relevance filter
        filtered_list = SOURCE_TO_LIST.get(source_filter, [])
        candidate_pool_size = limit_override if limit_override else (target_successes_needed * 2)
        skip_student = True
        for prof in filtered_list:
            if len(to_send) >= candidate_pool_size:
                break
            if prof["name"] not in sent_names and (skip_student or not is_student(prof)):
                to_send.append(prof)
        print(f"Single source '{source_filter}': {len(to_send)} candidates (skipping {len(sent_names)} already-sent)")
    else:
        # Priority order: Allen → eScience → new sources (round-robin fill)
        candidate_pool_size = target_successes_needed * 2
        count = 0
        for prof in allen_faculty:
            if count >= candidate_pool_size:
                break
            if prof["name"] not in sent_names and is_relevant(prof):
                to_send.append(prof)
                count += 1
        if len(to_send) < candidate_pool_size:
            for prof in escience_faculty:
                if count >= candidate_pool_size:
                    break
                if prof["name"] not in sent_names and not is_student(prof) and is_relevant(prof):
                    to_send.append(prof)
                    count += 1
        new_sources = [
            bioeng_faculty, uwmedicine_faculty, dirac_faculty,
            urbanalytics_faculty, misl_faculty, noble_faculty, eichler_faculty, ischool_faculty, publichealth_faculty, populationhealth_faculty
        ]
        source_indices = [0] * len(new_sources)
        skip_student = bool(source_filter)  # when targeting one department, don't filter by student keywords
        while len(to_send) < candidate_pool_size:
            added_any = False
            for idx, src in enumerate(new_sources):
                if len(to_send) >= candidate_pool_size:
                    break
                while source_indices[idx] < len(src):
                    prof = src[source_indices[idx]]
                    source_indices[idx] += 1
                    if prof["name"] not in sent_names and (skip_student or not is_student(prof)) and is_relevant(prof):
                        to_send.append(prof)
                        added_any = True
                        break
            if not added_any:
                break

    print(f"Processing up to {len(to_send)} outreach targets (pool size; sent_names: {len(sent_names)})...")
    if len(to_send) == 0:
        print("No faculty to contact: all are in sent log or failed. Remove entries from data/sent_log.csv or data/failed_outreach.csv to retry.")
        return
    if not dry_run:
        print("Wait 2 mins before starting to clear possible rate limits...")
        time.sleep(120)
    
    daily_drafts = []
    current_success_today = today_success_count
    # If limit_override is set, we track sends in this session only for the stopping condition
    session_sends = 0
    # Cross-check with sent_log so we never send to an email we already sent to (critical: no duplicate sends)
    sent_emails = load_sent_emails()
    print(f"Duplicate check: {len(sent_names)} names and {len(sent_emails)} emails in sent_log — will not send to any of these.")

    for prof in to_send:
        if limit_override:
             if session_sends >= limit_override:
                 print(f"Reached manual limit of {limit_override} sends for this session!")
                 break
        elif current_success_today >= 14:
            print("Reached target of 14 successful sends for today!")
            break
        # 1. Get email: CSV/bio first, then verify from faculty page, then infer from URL
        raw_email = prof.get("email", "").strip()
        bio_email = extract_email_from_text(prof.get("bio", ""))
        profile_link = prof.get("profile_link", "").strip()
        verified_email = fetch_email_from_faculty_page(profile_link) if profile_link else ""
        inferred_email = infer_email_from_profile(prof)
        
        target_email = None
        if test_email_only:
            target_email = test_email_only
        elif raw_email and "@" in raw_email:
            target_email = raw_email
        elif bio_email:
            target_email = bio_email
        elif verified_email:
            target_email = verified_email
        elif inferred_email:
            target_email = inferred_email
            
        # For live sends, require valid institutional-style email (reject www.thing.com@uw.edu etc.)
        if not target_email or target_email == "placeholder@uw.edu":
            log_failed_outreach(prof['name'], target_email or "None", prof.get("profile_link"), "No valid email found")
            continue
        if not test_email_only and not is_valid_email(target_email):
            log_failed_outreach(prof['name'], target_email, prof.get("profile_link"), "Invalid email format")
            print(f"Skipping {prof['name']}: invalid email '{target_email}' (e.g. URL-like or malformed).")
            continue
        if not test_email_only and not is_uw_email(target_email):
            log_failed_outreach(prof['name'], target_email, prof.get("profile_link"), "Not a UW address (only @*.uw.edu / @*.washington.edu)")
            print(f"Skipping {prof['name']}: not UW address '{target_email}' (only @*.uw.edu or @*.washington.edu allowed).")
            continue

        # Never send to someone we already sent to (cross-check sent_log by email)
        if not test_email_only and target_email.strip().lower() in sent_emails:
            print(f"Skipping {prof['name']}: already sent to {target_email} (see sent_log).")
            continue

        # 2. Proceed with drafting only if email is found
        print(f"\nMatching and drafting for {prof['name']} ({target_email})...")
        best_resume_name = select_best_resume(prof.get("bio", ""), resumes_dict)
        resume_text = resumes_dict[best_resume_name]
        
        subject, body = draft_cover_letter(prof, resume_text)
        
        if not subject or not body:
            print(f"Skipping {prof['name']}: Personalization failed (LLM error).")
            log_failed_outreach(prof['name'], target_email, prof.get("profile_link"), "Personalization Failed")
            continue

        if service:
             resume_path = get_resume_attachment_path(best_resume_name)
             success = send_email(service, target_email, subject, body, attachment_path=resume_path)
             if success and not test_email_only:
                 update_sent_log(prof["name"], target_email)
                 sent_emails.add(target_email.strip().lower())
                 update_tracker_on_send(
                     prof["name"],
                     prof.get("source", "Allen"),
                     target_email,
                     datetime.now().strftime("%Y-%m-%d"),
                 )
                 current_success_today += 1
                 session_sends += 1
             elif not success:
                 print(f"Failed to send email to {target_email} after retries.")
                 log_failed_outreach(prof['name'], target_email, prof.get("profile_link"), "Gmail API Send Failure")
        else:
            print(f"Dry run: Skipping email to {target_email}")
        
        draft_record = {
            "name": prof["name"],
            "email": target_email,
            "resume_used": best_resume_name,
            "subject": subject,
            "body": body,
            "profile_link": prof.get("profile_link"),
            "date": datetime.now().strftime("%Y-%m-%d")
        }
        daily_drafts.append(draft_record)

        # Delay between emails (shorter for test batch to same address)
        delay_sec = 15 if test_email_only else 120
        time.sleep(delay_sec)

    # Save daily results to a file for user review
    batch_filename = f"outreach_results_{datetime.now().strftime('%Y%m%d')}.json"
    with open(f"data/{batch_filename}", "w", encoding="utf-8") as f:
        json.dump(daily_drafts, f, indent=4)
        
    print(f"\nCompleted! {len(daily_drafts)} results saved to data/{batch_filename}")

    # Notify end of run (only if we did work)
    if (not dry_run and not test_email_only) or hasattr(sys, '_test_notify'):
        end_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        new_successes = current_success_today - today_success_count
        notify_run_email(
            service,
            f"Outreach Completed: {datetime.now().strftime('%Y-%m-%d')}",
            f"The daily faculty outreach process completed at {end_time}.\nTotal successful sends today: {current_success_today}.\nNew sends in this session: {new_successes}.\n\nAttached is the current sent log.",
            attachment_path=SENT_LOG_PATH,
        )

if __name__ == "__main__":
    import sys
    if os.getcwd() != _PROJECT_ROOT:
        os.chdir(_PROJECT_ROOT)
    os.makedirs("data", exist_ok=True)

    args = sys.argv[1:]

    def get_arg(flag, default=None):
        if flag in args:
            idx = args.index(flag)
            return args[idx + 1] if idx + 1 < len(args) else default
        return default

    source  = get_arg("--source")   # e.g. bioeng
    sources = get_arg("--sources")  # e.g. ischool,escience,noble,uwmedicine
    limit   = get_arg("--limit")    # e.g. 7
    limit   = int(limit) if limit else None
    sources_list = [s.strip() for s in sources.split(",")] if sources else None

    test_email = get_arg("--test") or os.getenv("TEST_OUTREACH_EMAIL", "your-email@example.com")
    if "--test-notify" in args:
        print("Testing start/end notifications...")
        sys._test_notify = True
        daily_outreach(dry_run=False, test_email_only=test_email, limit_override=limit, source_filter=source, sources_list=sources_list)
    elif "--test" in args:
        if limit:
            print(f"Test batch: sending up to {limit} emails to {test_email}")
        else:
            print(f"Test mode: sending 1 email to {test_email}")
        daily_outreach(dry_run=False, test_email_only=test_email, limit_override=limit, source_filter=source, sources_list=sources_list)
    elif "--live" in args:
        daily_outreach(dry_run=False, limit_override=limit, source_filter=source, sources_list=sources_list)
    else:
        print("Running in DRY RUN mode. Use --live for actual sending or --test for one email.")
        print(f"Valid --source values: {list(SOURCE_CSV_MAP.keys())}")
        daily_outreach(dry_run=True, limit_override=limit, source_filter=source, sources_list=sources_list)

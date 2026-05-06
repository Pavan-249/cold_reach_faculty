"""
Scrape UW Information School faculty from https://ischool.uw.edu/people/faculty
The page is JS-rendered; this script tries requests first, then can use a saved markdown file.
"""
import csv
import os
import re
import sys

SOURCE = "Information School"
BASE_URL = "https://ischool.uw.edu"
FACULTY_URL = f"{BASE_URL}/people/faculty"
OUTPUT_CSV = "data/ischool_faculty_all.csv"

# Generic/office emails to skip if we're deduplicating
SKIP_EMAILS = {
    "ischool@uw.edu", "ihelp@uw.edu", "informatics@uw.edu", "mlis@uw.edu",
    "msim@uw.edu", "ischoolphd@uw.edu", "icareers@uw.edu", "iask@uw.edu",
    "uwcip@uw.edu", "ialumni@uw.edu", "iaffiliates@uw.edu", "igive@uw.edu",
    "ihrhelp@uw.edu", "iideas@uw.edu", "tascha@uw.edu", "iraise@uw.edu",
}


def parse_markdown_faculty_list(text):
    """Parse markdown-style content with ## Name and [email](mailto:...). Returns list of dicts."""
    blocks = re.split(r"\n## ", text)
    faculty = []
    for b in blocks[1:]:
        lines = b.strip().split("\n")
        if not lines:
            continue
        name = lines[0].strip()
        if not name or "No results found" in name:
            continue
        email = ""
        bio_lines = []
        for L in lines[1:]:
            m = re.search(r"\[([^\]]+@[^\]]+)\]\(mailto:[^)]+\)", L)
            if m:
                email = m.group(1).strip().lower()
            if L.strip() and not L.strip().startswith("["):
                bio_lines.append(L.strip())
        bio = " ".join(bio_lines)[:800] if bio_lines else "Information School faculty"
        faculty.append({
            "name": name,
            "email": email,
            "bio": bio,
            "profile_link": FACULTY_URL,
            "source": SOURCE,
        })
    return faculty


def fetch_with_requests():
    """Fetch faculty page; if JS-rendered we may get minimal HTML."""
    try:
        import urllib.request
        req = urllib.request.Request(
            FACULTY_URL,
            headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"},
        )
        with urllib.request.urlopen(req, timeout=20) as r:
            return r.read().decode("utf-8", errors="ignore")
    except Exception as e:
        print(f"Request failed: {e}")
        return ""


def scrape_ischool(markdown_file=None):
    """
    Scrape iSchool faculty. If markdown_file is provided, parse that (e.g. saved from browser).
    Otherwise fetch with requests; if the page is JS-rendered, we may get few names and you can
    save the page as text and pass it next time.
    """
    text = ""
    if markdown_file and os.path.isfile(markdown_file):
        print(f"Reading from {markdown_file}...")
        with open(markdown_file, "r", encoding="utf-8") as f:
            text = f.read()
    else:
        print("Fetching faculty page...")
        html = fetch_with_requests()
        # If the site returns a readable list (e.g. server-rendered), we could parse HTML.
        # Here we look for markdown-like or structured content; otherwise suggest saving page.
        if "## " in html or "<h2" in html:
            text = html
        # Try to parse HTML blocks: <h2>Name</h2> ... mailto:...
        if not text:
            blocks = re.split(r"<h2[^>]*>", html)
            names = re.findall(r"<h2[^>]*>([^<]+)</h2>", html)
            if len(names) > 10:
                text = html
            else:
                # Likely JS-rendered; try to extract from script or give instructions
                print("Page appears JS-rendered (few names in HTML). Use Playwright or save the page as text.")
                return []
    faculty = parse_markdown_faculty_list(text) if "## " in text else []
    if not faculty and not text:
        # Last resort: fetch again and try HTML parsing for any name-like + mailto
        html = fetch_with_requests()
        # Find all mailto and preceding name-like text (heuristic)
        for m in re.finditer(r'mailto:([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.edu)', html):
            email = m.group(1).lower()
            if email in SKIP_EMAILS:
                continue
            # Look backwards for a name (simplified)
            start = max(0, m.start() - 200)
            chunk = html[start:m.start()]
            name_match = re.search(r">([A-Za-z][A-Za-z\.\s\-',]+(?:Jr\.|III|IV)?)\s*<", chunk)
            if name_match:
                name = name_match.group(1).strip()
                if len(name) > 4 and name not in ("Highlights", "Full Results"):
                    faculty.append({
                        "name": name,
                        "email": email,
                        "bio": "Information School faculty",
                        "profile_link": FACULTY_URL,
                        "source": SOURCE,
                    })
        # Dedupe by email
        seen = set()
        faculty = [f for f in faculty if f["email"] and f["email"] not in seen and not seen.add(f["email"])]
    return faculty


def main():
    markdown_file = sys.argv[1] if len(sys.argv) > 1 else None
    faculty = scrape_ischool(markdown_file=markdown_file)
    if not faculty:
        print("No faculty parsed. Save https://ischool.uw.edu/people/faculty as text and run: python scrape_ischool.py <path_to_saved.txt>")
        return
    os.makedirs("data", exist_ok=True)
    out = os.path.join(os.path.dirname(os.path.dirname(__file__)), OUTPUT_CSV)
    with open(out, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["name", "email", "bio", "profile_link", "source"])
        writer.writeheader()
        writer.writerows(faculty)
    print(f"Saved {len(faculty)} faculty to {out}")


if __name__ == "__main__":
    main()

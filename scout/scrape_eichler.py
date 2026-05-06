import time
import csv
import os
import re
from playwright.sync_api import sync_playwright

SOURCE = "Eichler Lab"
PEOPLE_URL = "https://eichler.gs.washington.edu/people/"
BASE_URL = "https://eichler.gs.washington.edu"
OUTPUT_CSV = "data/eichler_faculty_all.csv"

SKIP_KEYWORDS = ["phd student", "graduate student", "doctoral student", "postdoctoral", "postdoc", "undergraduate", "research assistant", "technician"]
FACULTY_KEYWORDS = ["professor", "faculty", "director", "principal investigator", "research scientist", "affiliate", "lead", "pi", "staff scientist"]

def deobfuscate_email(text):
    """Convert 'user [AT] domain.edu' → 'user@domain.edu'."""
    # Pattern: word chars, then [AT] or (AT) or " AT ", then domain
    pattern = r'([a-zA-Z0-9._%+-]+)\s*[\[\(]AT[\]\)]\s*([a-zA-Z0-9.-]+\.[a-zA-Z]{2,})'
    match = re.search(pattern, text, re.IGNORECASE)
    if match:
        return f"{match.group(1)}@{match.group(2)}".lower()
    return ""

def extract_deep_profile(page, url):
    try:
        page.goto(url, timeout=30000)
        time.sleep(1)
        content = ""
        email = ""
        selectors = [".entry-content", "article", ".person-bio", "main", ".content"]
        for s in selectors:
            el = page.query_selector(s)
            if el:
                content = el.inner_text().strip()
                break
        # Try mailto: first
        email_el = page.query_selector("a[href^='mailto:']")
        if email_el:
            email = email_el.get_attribute("href").replace("mailto:", "").split("?")[0].strip()
        # Try [AT] obfuscation in page text
        if not email:
            body_text = page.inner_text("body")
            email = deobfuscate_email(body_text)
        # Plain email fallback
        if not email:
            body_text = page.inner_text("body") if not locals().get("body_text") else body_text
            emails = re.findall(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.edu', body_text)
            for e in emails:
                if "uw.edu" in e.lower() or "washington.edu" in e.lower():
                    email = e.lower()
                    break
        return content, email.strip().lower()
    except Exception as ex:
        print(f"  Error scraping {url}: {ex}")
        return "", ""

def scrape_eichler():
    member_list = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(PEOPLE_URL, timeout=30000)
        time.sleep(2)

        for _ in range(4):
            page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            time.sleep(1)

        seen = set()
        # Eichler lab: large visual cards; name in h2 inside card link
        card_links = page.query_selector_all("a[href*='/people/'], .person-card a, article a")
        for el in card_links:
            href = el.get_attribute("href") or ""
            if not href or href in seen:
                continue
            # Skip the main people listing page itself
            if href.rstrip("/") == PEOPLE_URL.rstrip("/"):
                continue
            if "/people/" not in href:
                continue
            seen.add(href)
            link = href if href.startswith("http") else BASE_URL + href
            # Get name from h2/h3 inside the card
            name_el = el.query_selector("h2, h3, h4, .name, .card-title")
            if not name_el:
                # Try text content of the link itself
                name = el.inner_text().strip().split("\n")[0]
            else:
                name = name_el.inner_text().strip()
            if not name:
                name = href.rstrip("/").split("/")[-1].replace("-", " ").title()
            member_list.append({"name": name, "profile_link": link})

        print(f"Found {len(member_list)} Eichler Lab member profile pages.")

        results = []
        for i, m in enumerate(member_list):
            print(f"[{i+1}/{len(member_list)}] Deep scraping {m['name']}...")
            bio, email = extract_deep_profile(page, m["profile_link"])
            bio_lower = bio.lower()
            is_student = any(kw in bio_lower for kw in SKIP_KEYWORDS)
            is_faculty = any(kw in bio_lower for kw in FACULTY_KEYWORDS)
            if is_student and not is_faculty:
                print(f"  -> Skipping (student/postdoc)")
                continue
            results.append({
                "name": m["name"],
                "email": email,
                "bio": bio[:3000],
                "profile_link": m["profile_link"],
                "source": SOURCE,
            })

        browser.close()

    os.makedirs("data", exist_ok=True)
    with open(OUTPUT_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["name", "email", "bio", "profile_link", "source"])
        writer.writeheader()
        writer.writerows(results)
    print(f"\nSaved {len(results)} {SOURCE} members to {OUTPUT_CSV}")

if __name__ == "__main__":
    scrape_eichler()

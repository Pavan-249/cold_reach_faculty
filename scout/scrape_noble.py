import time
import csv
import os
import re
from playwright.sync_api import sync_playwright

SOURCE = "Noble Lab"
HOME_URL = "https://noble.gs.washington.edu/"
PEOPLE_URL = "https://noble.gs.washington.edu/people/"
OUTPUT_CSV = "data/noble_faculty_all.csv"

SKIP_KEYWORDS = ["phd student", "graduate student", "doctoral student", "postdoctoral", "postdoc", "undergraduate", "research assistant"]
FACULTY_KEYWORDS = ["professor", "faculty", "director", "principal investigator", "research scientist", "affiliate", "lead", "pi"]

def extract_deep_profile(page, url):
    try:
        page.goto(url, timeout=30000)
        time.sleep(1)
        content = ""
        email = ""
        selectors = [
            ".field-name-field-person-research-statement",
            ".field-name-field-person-bio",
            "#research", ".research-statement",
            ".entry-content", "article", "main", ".content"
        ]
        for s in selectors:
            el = page.query_selector(s)
            if el:
                content = el.inner_text().strip()
                break
        email_el = page.query_selector("a[href^='mailto:']")
        if email_el:
            email = email_el.get_attribute("href").replace("mailto:", "").split("?")[0].strip()
        if not email:
            body_text = page.inner_text("body")
            emails = re.findall(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.edu', body_text)
            for e in emails:
                if "uw.edu" in e.lower() or "washington.edu" in e.lower():
                    email = e.lower()
                    break
        return content, email.strip().lower()
    except Exception as ex:
        print(f"  Error scraping {url}: {ex}")
        return "", ""

def scrape_noble():
    member_list = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        # Try dedicated /people/ page first, fall back to homepage
        for url in [PEOPLE_URL, HOME_URL]:
            try:
                page.goto(url, timeout=30000)
                time.sleep(2)
                for _ in range(3):
                    page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                    time.sleep(1)

                seen = set()
                # Noble lab uses simple li elements with bold names and links
                els = page.query_selector_all("li a, ul a, .people a, .members a")
                for el in els:
                    name = el.inner_text().strip()
                    href = el.get_attribute("href") or ""
                    if not name or not href or href in seen or len(name) < 3:
                        continue
                    if href.startswith("#") or "mailto:" in href:
                        continue
                    seen.add(href)
                    link = href if href.startswith("http") else HOME_URL.rstrip("/") + "/" + href.lstrip("/")
                    member_list.append({"name": name, "profile_link": link})

                if member_list:
                    break
            except Exception as ex:
                print(f"Could not load {url}: {ex}")

        print(f"Found {len(member_list)} Noble Lab members.")

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
    scrape_noble()

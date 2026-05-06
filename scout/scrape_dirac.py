import time
import csv
import os
import re
from playwright.sync_api import sync_playwright

SOURCE = "DiRAC"
BASE_URL = "https://dirac.astro.washington.edu"
PEOPLE_URL = f"{BASE_URL}/people/"
OUTPUT_CSV = "data/dirac_faculty_all.csv"

SKIP_KEYWORDS = ["phd student", "graduate student", "doctoral student", "postdoctoral", "postdoc", "fellow"]
FACULTY_KEYWORDS = ["professor", "faculty", "director", "principal investigator", "pi", "research scientist", "affiliate"]

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
            if not email and emails:
                email = emails[0].lower()
        return content, email.strip().lower()
    except Exception as ex:
        print(f"  Error scraping {url}: {ex}")
        return "", ""

def scrape_dirac():
    member_list = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(PEOPLE_URL, timeout=30000)
        time.sleep(2)

        for _ in range(3):
            page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            time.sleep(1)

        # DiRAC uses Bootstrap cards (.card.mb-5); name is in h3.card-title a
        # Profile link is the "Full Profile" button: a.btn.btn-dark.btn-sm
        cards = page.query_selector_all(".card.mb-5")
        seen_links = set()
        for card in cards:
            name_el = card.query_selector("h3.card-title a, h3.card-title, h4.card-title a, h4.card-title")
            profile_link_el = card.query_selector("a.btn.btn-dark.btn-sm, a.btn-dark")
            if not name_el:
                continue
            name = name_el.inner_text().strip()
            if not name or len(name) < 2:
                continue
            href = ""
            if profile_link_el:
                href = profile_link_el.get_attribute("href") or ""
            if not href:
                # Fall back to the name link itself
                href = name_el.get_attribute("href") or ""
            if not href or href in seen_links:
                continue
            seen_links.add(href)
            link = href if href.startswith("http") else BASE_URL + href
            member_list.append({"name": name, "profile_link": link})

        print(f"Found {len(member_list)} DiRAC member profiles.")

        results = []
        for i, m in enumerate(member_list):
            print(f"[{i+1}/{len(member_list)}] Deep scraping {m['name']}...")
            bio, email = extract_deep_profile(page, m["profile_link"])
            bio_lower = bio.lower()
            # Keep only faculty/researchers – skip pure student listings
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
    scrape_dirac()

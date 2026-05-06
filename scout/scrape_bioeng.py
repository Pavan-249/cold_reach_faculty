import time
import csv
import os
import re
from playwright.sync_api import sync_playwright

SOURCE = "Bioengineering"
BASE_URL = "https://bioe.uw.edu"
FACULTY_URL = f"{BASE_URL}/faculty-staff/core-faculty/"
OUTPUT_CSV = "data/bioeng_faculty_all.csv"

SKIP_KEYWORDS = ["phd student", "graduate student", "doctoral student", "postdoctoral", "postdoc", "research scientist"]

def extract_deep_profile(page, url):
    try:
        page.goto(url, timeout=30000)
        time.sleep(1)
        content = ""
        email = ""
        selectors = [".entry-content", "article", "main", ".fusion-post-content"]
        for s in selectors:
            el = page.query_selector(s)
            if el:
                content = el.inner_text().strip()
                break
        # mailto: first
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

def scrape_bioeng():
    faculty_list = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(FACULTY_URL, timeout=30000)
        # Scroll to trigger lazy loads
        for _ in range(3):
            page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            time.sleep(1)

        # Avada theme: faculty cards use fusion-portfolio-post
        cards = page.query_selector_all("div.fusion-portfolio-post h3 a, .portfolio-one .portfolio-item h3 a, .fusion-portfolio h3 a")
        if not cards:
            # Broader fallback: any prominent link with a person title
            cards = page.query_selector_all("h3 a, h2 a")
        print(f"Found {len(cards)} candidate faculty members.")

        seen = set()
        for el in cards:
            name = el.inner_text().strip()
            href = el.get_attribute("href") or ""
            if not name or name in seen:
                continue
            seen.add(name)
            link = href if href.startswith("http") else BASE_URL + href
            faculty_list.append({"name": name, "profile_link": link})

        results = []
        for i, f in enumerate(faculty_list):
            print(f"[{i+1}/{len(faculty_list)}] Deep scraping {f['name']}...")
            bio, email = extract_deep_profile(page, f["profile_link"])
            # Skip students / postdocs — check only the title/headline (first 300 chars)
            # to avoid false-positives from boilerplate content on dept pages
            bio_title = bio[:300].lower()
            if any(kw in bio_title for kw in SKIP_KEYWORDS):
                print(f"  -> Skipping (student/postdoc detected in title)")
                continue
            results.append({
                "name": f["name"],
                "email": email,
                "bio": bio[:3000],
                "profile_link": f["profile_link"],
                "source": SOURCE,
            })

        browser.close()

    os.makedirs("data", exist_ok=True)
    with open(OUTPUT_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["name", "email", "bio", "profile_link", "source"])
        writer.writeheader()
        writer.writerows(results)
    print(f"\nSaved {len(results)} {SOURCE} faculty to {OUTPUT_CSV}")

if __name__ == "__main__":
    scrape_bioeng()

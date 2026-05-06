import time
import csv
import os
import re
from playwright.sync_api import sync_playwright

SOURCE = "UW Medicine"
BASE_URL = "https://medicine.uw.edu"
FACULTY_URL = f"{BASE_URL}/people"
OUTPUT_CSV = "data/uwmedicine_faculty_all.csv"

SKIP_KEYWORDS = ["phd student", "graduate student", "doctoral student", "postdoctoral", "postdoc"]

def extract_deep_profile(page, url):
    try:
        page.goto(url, timeout=30000)
        time.sleep(1)
        content = ""
        email = ""
        selectors = [".field--name-body", ".views-field-body", "article", "main", ".layout-container"]
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

def scrape_uwmedicine():
    member_list = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(FACULTY_URL, timeout=30000)
        time.sleep(2)

        # Scroll to load all lazy-loaded content
        for _ in range(5):
            page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            time.sleep(1)

        # Try multiple selectors for UW Medicine people listing
        selectors_to_try = [
            "a[aria-label]",
            ".views-row h3 a",
            ".person-card a",
            ".views-field-title a",
        ]
        seen = set()
        for sel in selectors_to_try:
            els = page.query_selector_all(sel)
            for el in els:
                name = (el.get_attribute("aria-label") or el.inner_text()).strip()
                href = el.get_attribute("href") or ""
                if not name or name in seen or len(name) < 3:
                    continue
                seen.add(name)
                link = href if href.startswith("http") else BASE_URL + href
                member_list.append({"name": name, "profile_link": link})
            if member_list:
                break

        print(f"Found {len(member_list)} people on UW Medicine people page.")

        results = []
        for i, m in enumerate(member_list):
            print(f"[{i+1}/{len(member_list)}] Deep scraping {m['name']}...")
            bio, email = extract_deep_profile(page, m["profile_link"])
            bio_lower = bio.lower()
            if any(kw in bio_lower for kw in SKIP_KEYWORDS):
                print(f"  -> Skipping (student/postdoc detected)")
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
    print(f"\nSaved {len(results)} {SOURCE} faculty to {OUTPUT_CSV}")

if __name__ == "__main__":
    scrape_uwmedicine()

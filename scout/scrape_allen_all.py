import json
import time
import csv
import os
import re
from playwright.sync_api import sync_playwright

def extract_deep_profile(page, url):
    try:
        page.goto(url, timeout=30000)
        time.sleep(1)
        
        content = ""
        email = ""
        
        # Looking for Research Statement, Bio, or similar
        selectors = [
            ".field-name-field-person-research-statement",
            ".field-name-field-person-bio",
            "#research",
            ".research-statement",
            "article", "main"
        ]
        for s in selectors:
            el = page.query_selector(s)
            if el:
                content += el.inner_text().strip() + "\n"
                break # Take the first good one
        
        # Email extraction
        email_el = page.query_selector("a[href^='mailto:']")
        if email_el:
            email = email_el.get_attribute("href").replace("mailto:", "").split("?")[0]
        
        if not email:
            body_text = page.inner_text("body")
            emails = re.findall(r'[a-zA-Z0-9._%+-]+@(cs\.)?washington\.edu', body_text)
            if emails:
                email = emails[0][0] if isinstance(emails[0], tuple) else emails[0]

        return content.strip(), email.strip()
    except Exception as e:
        print(f"Error scraping {url}: {e}")
        return "", ""

def scrape_allen_all():
    url = "https://www.cs.washington.edu/people/faculty-members/"
    faculty_list = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(url)

        # Scroll to bottom to ensure all elements are loaded
        page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        time.sleep(2)

        # Extract faculty items
        faculty_elements = page.query_selector_all('a[aria-label^="Read the bio for"]')
        print(f"Found {len(faculty_elements)} faculty members on main page.")
        
        for el in faculty_elements:
            name = el.inner_text().strip()
            href = el.get_attribute("href")
            link = href if href.startswith("http") else "https://www.cs.washington.edu" + href
            faculty_list.append({"name": name, "profile_link": link})

        # Now deep scrape EACH
        results = []
        for i, faculty in enumerate(faculty_list):
            print(f"[{i+1}/{len(faculty_list)}] Deep scraping {faculty['name']}...")
            bio, email = extract_deep_profile(page, faculty["profile_link"])
            results.append({
                "name": faculty["name"],
                "email": email,
                "bio": bio,
                "profile_link": faculty["profile_link"],
                "source": "Allen School"
            })

        browser.close()

    # Save to CSV
    os.makedirs("data", exist_ok=True)
    with open("data/allen_faculty_all.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["name", "email", "bio", "profile_link", "source"])
        writer.writeheader()
        writer.writerows(results)
    
    print(f"Saved {len(results)} Allen School faculty to data/allen_faculty_all.csv")

if __name__ == "__main__":
    scrape_allen_all()

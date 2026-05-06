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
        
        # Looking for Bio, Interests, etc.
        selectors = [".member-bio", ".member-interests", ".entry-content", "article", "main"]
        for s in selectors:
            el = page.query_selector(s)
            if el:
                content += el.inner_text().strip() + "\n"
                break
        
        # Email extraction
        email_el = page.query_selector("a[href^='mailto:']")
        if email_el:
            email = email_el.get_attribute("href").replace("mailto:", "").split("?")[0]
        
        if not email:
            body_text = page.inner_text("body")
            emails = re.findall(r'[a-zA-Z0-9._%+-]+@uw\.edu', body_text)
            if emails:
                email = emails[0]

        return content.strip(), email.strip()
    except Exception as e:
        print(f"Error scraping {url}: {e}")
        return "", ""

def scrape_escience_all():
    url = "https://escience.washington.edu/people/escience-team/"
    member_list = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(url)

        # Click 'All' filter
        all_filter = page.query_selector("a#all_cats")
        if all_filter:
            all_filter.click()
            page.wait_for_timeout(3000)

        # Scroll to bottom multiple times to ensure all members load
        print("Scrolling to load all members...")
        for _ in range(5):
            page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            page.wait_for_timeout(1000)

        # Extract items
        items = page.query_selector_all("a.member")
        print(f"Found {len(items)} members in eScience list after filtering for 'All'.")
        
        member_list = []
        for el in items:
            name_el = el.query_selector("div div")
            name = name_el.inner_text().strip() if name_el else ""
            link = el.get_attribute("href")
            if link and not link.startswith("http"):
                 link = "https://escience.washington.edu" + link
            
            if name and "People" not in name and link:
                member_list.append({"name": name, "profile_link": link})

        print(f"Total unique members to deep scrape: {len(member_list)}")

        # Deep scrape
        results = []
        for i, member in enumerate(member_list):
            print(f"[{i+1}/{len(member_list)}] Deep scraping {member['name']}...")
            bio, email = extract_deep_profile(page, member["profile_link"])
            results.append({
                "name": member["name"],
                "email": email,
                "bio": bio,
                "profile_link": member["profile_link"],
                "source": "eScience"
            })

        browser.close()

    # Save to CSV
    os.makedirs("data", exist_ok=True)
    with open("data/escience_faculty_all.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["name", "email", "bio", "profile_link", "source"])
        writer.writeheader()
        writer.writerows(results)
    
    print(f"Saved {len(results)} eScience members to data/escience_faculty_all.csv")

if __name__ == "__main__":
    scrape_escience_all()

import json
import time
from playwright.sync_api import sync_playwright

def scrape_escience():
    url = "https://escience.washington.edu/people/escience-team/"
    team_data = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(url)

        # Click 'All' filter if it exists
        all_filter = page.query_selector("a#filter-all, .filter-item[data-filter='all']")
        if all_filter:
            all_filter.click()
            time.sleep(2)

        # Scroll to bottom
        page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        time.sleep(2)

        # Wait for member cards
        page.wait_for_selector("a.member", timeout=5000, state="attached")

        # Extract team items
        items = page.query_selector_all("a.member")
        
        for el in items:
            name_el = el.query_selector(".member-desc div")
            title_el = el.query_selector(".member-desc div:last-child")
            
            name = name_el.inner_text().strip() if name_el else ""
            title = title_el.inner_text().strip() if title_el else ""
            link = el.get_attribute("href")
            
            if link and not link.startswith("http"):
                 link = "https://escience.washington.edu" + link
            
            if name and link:
                team_data.append({
                    "name": name,
                    "title": title,
                    "profile_link": link,
                    "source": "eScience"
                })

        browser.close()
    
    return team_data

if __name__ == "__main__":
    data = scrape_escience()
    with open("data/escience_team.json", "w") as f:
        json.dump(data, f, indent=4)
    print(f"Scraped {len(data)} members from eScience.")

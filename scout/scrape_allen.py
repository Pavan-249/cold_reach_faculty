import json
import time
from playwright.sync_api import sync_playwright

def scrape_allen_school():
    url = "https://www.cs.washington.edu/people/faculty-members/"
    faculty_data = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(url)

        # Scroll to bottom to ensure all elements are loaded
        page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        time.sleep(2)  # Wait for lazy loading

        # Extract faculty items
        faculty_elements = page.query_selector_all('a[aria-label^="Read the bio for"]')
        
        for el in faculty_elements:
            name = el.inner_text().strip()
            href = el.get_attribute("href")
            link = href if href.startswith("http") else "https://www.cs.washington.edu" + href
            
            # Title typically follows or is nearby - let's try to find title through parent
            parent_handle = el.evaluate_handle("el => el.closest('.views-row')")
            parent = parent_handle.as_element()
            title = ""
            if parent:
                title_el = parent.query_selector(".views-field-field-person-title")
                title = title_el.inner_text().strip() if title_el else ""
                
            faculty_data.append({
                "name": name,
                "title_department": title,
                "profile_link": link,
                "source": "Allen School"
            })

        browser.close()
    
    return faculty_data

if __name__ == "__main__":
    data = scrape_allen_school()
    with open("data/allen_school_faculty.json", "w") as f:
        json.dump(data, f, indent=4)
    print(f"Scraped {len(data)} faculty members from Allen School.")

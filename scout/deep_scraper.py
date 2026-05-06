import json
import time
from playwright.sync_api import sync_playwright

def extract_deep_profile(page, url, source):
    try:
        page.goto(url, timeout=30000)
        time.sleep(1)
        
        content = ""
        email = ""
        
        if source == "Allen School":
            # Looking for Research Statement, Bio, or similar
            selectors = [
                ".field-name-field-person-research-statement",
                ".field-name-field-person-bio",
                "#research",
                ".research-statement"
            ]
            for s in selectors:
                el = page.query_selector(s)
                if el:
                    content += el.inner_text().strip() + "\n"
            
            # Email extraction for Allen School
            email_el = page.query_selector("a[href^='mailto:']")
            if email_el:
                email = email_el.get_attribute("href").replace("mailto:", "").split("?")[0]
        
        elif source == "eScience":
            # Looking for Special Interest Group, Bio, etc.
            selectors = [
                ".member-bio",
                ".member-interests",
                ".entry-content"
            ]
            for s in selectors:
                el = page.query_selector(s)
                if el:
                    content += el.inner_text().strip() + "\n"
            
            # Email extraction for eScience
            email_el = page.query_selector("a[href^='mailto:']")
            if email_el:
                email = email_el.get_attribute("href").replace("mailto:", "").split("?")[0]
        
        # Fallback for email: look for text containing @uw.edu or @cs.washington.edu
        if not email:
            body_text = page.inner_text("body")
            import re
            emails = re.findall(r'[a-zA-Z0-9._%+-]+@(cs\.)?washington\.edu', body_text)
            if emails:
                if isinstance(emails[0], tuple):
                    email = emails[0][0] # Simple regex match
                else:
                    email = emails[0]

        # Fallback for content: just get the main content area text if specific selectors fail
        if not content.strip():
            main = page.query_selector("article, main, .content, #main-content")
            if main:
                content = main.inner_text().strip()

        return content.strip(), email.strip()
    except Exception as e:
        print(f"Error scraping {url}: {e}")
        return "", ""

def deep_scrape():
    all_faculty = []
    
    # Load Allen School data
    try:
        with open("data/allen_school_faculty.json", "r") as f:
            all_faculty.extend(json.load(f))
    except FileNotFoundError:
        pass
        
    # Load eScience data
    try:
        with open("data/escience_team.json", "r") as f:
            all_faculty.extend(json.load(f))
    except FileNotFoundError:
        pass

    if not all_faculty:
        print("No faculty data found to deep scrape.")
        return

    print(f"Deep scraping {len(all_faculty)} profiles...")
    
    results = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()
        page = context.new_page()
        
        # Process the first 20 as requested by the original loop, 
        # but we can do more if needed.
        for i, faculty in enumerate(all_faculty[:20]):
            print(f"[{i+1}/20] Scraping {faculty['name']}...")
            deep_text, email = extract_deep_profile(page, faculty["profile_link"], faculty["source"])
            faculty["deep_profile_text"] = deep_text
            faculty["email"] = email
            results.append(faculty)
            
        browser.close()

    with open("data/faculty_deep_profiles.json", "w") as f:
        json.dump(results, f, indent=4)
    print(f"Saved {len(results)} deep profiles to data/faculty_deep_profiles.json")

    # Export to CSV as requested
    import csv
    with open("data/faculty_data.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["name", "email", "deep_profile_text", "profile_link", "source"])
        writer.writeheader()
        for row in results:
            writer.writerow({
                "name": row.get("name", ""),
                "email": row.get("email", ""),
                "deep_profile_text": row.get("deep_profile_text", ""),
                "profile_link": row.get("profile_link", ""),
                "source": row.get("source", "")
            })
    print(f"Exported {len(results)} profiles to data/faculty_data.csv")

if __name__ == "__main__":
    deep_scrape()

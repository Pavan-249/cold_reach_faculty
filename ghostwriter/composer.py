import json
import csv
import os
from datetime import datetime

# Logic for the Composer Agent (Ghostwriter)
# This script drafts 15 emails daily and maintains a sent log.

SENT_LOG_PATH = "data/sent_log.csv"
MATCHES_PATH = "data/matches.json"
DAILY_LIMIT = 15

def load_sent_log():
    if not os.path.exists(SENT_LOG_PATH):
        with open(SENT_LOG_PATH, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["name", "email", "date_sent"])
        return set()
    
    with open(SENT_LOG_PATH, "r") as f:
        reader = csv.DictReader(f)
        return {row["name"] for row in reader}

def update_sent_log(name, email):
    with open(SENT_LOG_PATH, "a", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([name, email, datetime.now().strftime("%Y-%m-%d")])

# Exactly two resumes: Data Scientist and Data Engineering
RESUME_LABELS = {
    "resume_data_scientist.pdf": "Data Scientist",
    "resume_data_engineering.pdf": "Data Engineering and Architecture",
}

def draft_email(prof, resume_key):
    # This would normally call an LLM (Gemini) with the matching_logic.md skill
    # For now, we'll generate a high-quality template-based draft.
    label = RESUME_LABELS.get(resume_key, resume_key)

    subject = f"Inquiry regarding your research – {label} background – [Your Name]"
    body = f"""Dear Prof. {prof['name']},

I hope this email finds you well. I have been following your recent work at the Allen School, particularly your contributions to {prof.get('title', 'computer science')}.

My experience in {label} can specifically help your team with the technical challenges mentioned in your latest papers. I am particularly interested in how your research handles [Scraped Project Task/Bottleneck].

I've attached my resume ({label}) for your reference and would love to discuss potential opportunities in your lab.

Best regards,
[Your Name]
"""
    return subject, body

def ghostwriter():
    sent_names = load_sent_log()
    with open(MATCHES_PATH, "r") as f:
        matches = json.load(f)
    
    drafted_count = 0
    for match in matches:
        if drafted_count >= DAILY_LIMIT:
            break
        
        if match["name"] in sent_names:
            continue
            
        email = match.get("email", "placeholder@uw.edu")
        if not email or "@" not in email:
            email = "placeholder@uw.edu"

        subject, body = draft_email(match, match["selected_resume"])
        
        print(f"--- DRAFTING FOR {match['name']} ({email}) ---")
        print(f"Subject: {subject}")
        print(f"Resume: {match['selected_resume']}")
        print(body)
        print("-" * 30)
        
        # In a real integration, this would call the Gmail API to create a draft
        # For now, we simulate the 'sent' status
        update_sent_log(match["name"], email)
        drafted_count += 1

    print(f"Successfully drafted {drafted_count} emails today.")

if __name__ == "__main__":
    ghostwriter()

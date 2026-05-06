import csv
import os
import json
import time
from datetime import datetime
import google.generativeai as genai
import sys

# Add the project root to path so we can import from ghostwriter if needed, 
# but for simplicity I'll copy the core logic here with the test override.

SENT_LOG_PATH = "data/sent_log.csv"
ALLEN_CSV = "data/allen_faculty_all.csv"
ESCIENCE_CSV = "data/escience_faculty_all.csv"
RESUMES_EXTRACTED_JSON = "data/resumes_extracted.json"
TEST_EMAIL = os.getenv("TEST_OUTREACH_EMAIL", "your-email@example.com")

# Exactly two resumes
RESUME_DATA_SCIENTIST = "resume_data_scientist.pdf"
RESUME_DATA_ENGINEERING = "resume_data_engineering.pdf"
ALLOWED_RESUMES = [RESUME_DATA_SCIENTIST, RESUME_DATA_ENGINEERING]

# Initialize Gemini
API_KEY = os.getenv("GEMINI_API_KEY")
genai.configure(api_key=API_KEY)
model = genai.GenerativeModel("gemini-flash-latest")

def load_faculty(file_path):
    if not os.path.exists(file_path):
        return []
    with open(file_path, "r", encoding="utf-8") as f:
        return list(csv.DictReader(f))

def load_resumes():
    with open(RESUMES_EXTRACTED_JSON, "r", encoding="utf-8") as f:
        all_resumes = json.load(f)
    return {k: v for k, v in all_resumes.items() if k in ALLOWED_RESUMES} or all_resumes

def select_best_resume(prof_bio, resumes_dict):
    allowed = {k: v for k, v in resumes_dict.items() if k in ALLOWED_RESUMES} or resumes_dict
    resume_options = "\n".join([f"- {name}: {text[:300]}..." for name, text in allowed.items()])
    prompt = f"""
    You are an expert career counselor. I have exactly TWO resumes. Select the ONE filename that best matches the professor's research.
    Resumes: (1) {RESUME_DATA_SCIENTIST} – Data Scientist. (2) {RESUME_DATA_ENGINEERING} – Data Engineering and Architecture.
    Pick Data Scientist for ML/analytics/experimentation; pick Data Engineering for systems/pipelines/infrastructure.

    Professor's Bio:
    {prof_bio[:1000]}

    My Resume Options:
    {resume_options}

    Return ONLY the exact filename of the best matching resume.
    """
    response = model.generate_content(prompt)
    selected = response.text.strip().replace('"', '').replace("'", "")
    for key in allowed.keys():
        if key in selected or selected in key:
            return key
    return next(iter(allowed.keys()))

def draft_cover_letter(prof, resume_text):
    source_context = "Allen School" if "Allen" in prof.get("source", "") else "eScience Institute"
    prompt = f"""
    You are an ambitious student reaching out to a professor for research opportunities.
    I have two profiles: Data Scientist and Data Engineering/Architecture. The resume below is the one I selected for this professor. Draft a personalized cover letter that reflects that profile.

    Professor: {prof['name']} at UW {source_context}
    Professor's Bio: {prof.get('bio', '')[:1000]}
    My Resume Content: {resume_text[:2000]}

    Return your response in JSON format with 'subject' and 'body' fields.
    Ensure the tone is respectful and concise. Use [Your Name] as placeholder.
    """
    response = model.generate_content(prompt)
    content = response.text.strip()
    if "```json" in content:
        content = content.split("```json")[1].split("```")[0].strip()
    data = json.loads(content)
    return data["subject"], data["body"]

def run_single_test():
    allen_faculty = load_faculty(ALLEN_CSV)
    resumes_dict = load_resumes()
    
    if not allen_faculty:
        print("No faculty found.")
        return

    # Pick the first professor for the test
    prof = allen_faculty[0]
    print(f"--- TEST RUN FOR {prof['name']} ---")
    
    print("Matching best resume...")
    best_resume_name = select_best_resume(prof.get("bio", ""), resumes_dict)
    print(f"Selected Resume: {best_resume_name}")
    
    print("Drafting personalized cover letter...")
    subject, body = draft_cover_letter(prof, resumes_dict[best_resume_name])
    
    print(f"\nTARGET EMAIL (OVERRIDDEN): {TEST_EMAIL}")
    print(f"SUBJECT: {subject}")
    print("\nBODY:")
    print(body)
    print("\n--- TEST RUN COMPLETE ---")

if __name__ == "__main__":
    run_single_test()

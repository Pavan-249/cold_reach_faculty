import os
import json
from pypdf import PdfReader

def extract_resumes():
    resume_folder = "resume"
    output_file = "data/resumes_extracted.json"
    
    if not os.path.exists(resume_folder):
        print(f"Error: {resume_folder} not found.")
        return
    
    resumes = {}
    for filename in os.listdir(resume_folder):
        if filename.endswith(".pdf"):
            print(f"Extracting {filename}...")
            path = os.path.join(resume_folder, filename)
            try:
                reader = PdfReader(path)
                text = ""
                for page in reader.pages:
                    text += page.extract_text() + "\n"
                resumes[filename] = text.strip()
            except Exception as e:
                print(f"Could not read {filename}: {e}")
    
    os.makedirs("data", exist_ok=True)
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(resumes, f, indent=4)
    
    print(f"Successfully extracted {len(resumes)} resumes to {output_file}")

if __name__ == "__main__":
    extract_resumes()

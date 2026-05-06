import json
import os
from typing import List, Dict

# Note: In a real scenario, we'd use gemini embeddings or similar.
# For this agentic implementation, we will use a dedicated "Matchmaker" logic
# that leverages the LLM's reasoning to score the match.

def load_data(file_path):
    try:
        with open(file_path, "r") as f:
            return json.load(f)
    except FileNotFoundError:
        return []

def matchmaker():
    profiles = load_data("data/faculty_deep_profiles.json")
    
    # Two resumes: Data Scientist and Data Engineering/Architecture
    resumes = {
        "resume_data_scientist.pdf": "Data Scientist: Statistical analysis, ML/modeling, data visualization, experimentation. Proficient in Python, R, and data science tools.",
        "resume_data_engineering.pdf": "Data Engineering and Architecture: Distributed systems, data pipelines, cloud infrastructure, and scalable data architecture. Experience with data platforms and engineering."
    }

    print(f"Ranking {len(profiles)} profiles against {len(resumes)} resumes (Data Scientist vs Data Engineering)...")
    
    matches = []
    
    # In this step, the agent uses its internal "intelligence" (Gemini)
    # to perform the semantic scoring for each professor.
    for prof in profiles:
        # We'll simulate the scoring here, but the Composer Agent
        # will use these scores to select the best resume.
        
        # Simple keyword matching as a fallback/simulation
        scores = {}
        for key, text in resumes.items():
            score = 0
            words = text.lower().split()
            bio = (prof.get("deep_profile_text", "") + " " + prof.get("name", "")).lower()
            for word in words:
                if len(word) > 4 and word in bio:
                    score += 1
            scores[key] = score
        
        best_resume = max(scores, key=scores.get)
        matches.append({
            "name": prof["name"],
            "email": prof.get("email", ""),
            "title": prof.get("title_department", ""),
            "selected_resume": best_resume,
            "alignment_reason": f"Matches key concepts in {best_resume}",
            "profile_link": prof["profile_link"]
        })

    with open("data/matches.json", "w") as f:
        json.dump(matches, f, indent=4)
        
    print(f"Matchmaking complete. Results saved to data/matches.json")
    return matches

if __name__ == "__main__":
    matchmaker()

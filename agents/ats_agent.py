import json
import re
from tools.llm import claude

def ats_agent(resume_text: str, job_description: str, api_key: str = None) -> dict:
    """
    Analyzes a resume against a job description.
    Returns a dictionary with ATS score, keywords analysis, and improvement suggestions.
    """
    print("ATS Agent: Scoring resume and extracting keywords...")
    
    prompt = f"""You are an expert ATS (Applicant Tracking System) and executive recruiter.
Analyze the following resume against the job description.

RESUME TEXT:
{resume_text[:2000]}

JOB DESCRIPTION:
{job_description[:2000]}

Please perform the following tasks:
1. Extract critical technical skills and keywords from the job description.
2. Cross-reference these with the resume. Identify which keywords are matching (present in the resume) and which are missing (critical in the job description but not in the resume).
3. Compute an overall ATS Match Score (0 to 100) based on skills overlap, experience matching, and role fit.
4. Score these individual sections from 0 to 100:
   - Work Experience (based on impact, metrics, and role match)
   - Skills (based on keyword match and core technical skills)
   - Education & Certifications (based on requirements)
   - Formatting & Readability (grammar, structure)
5. Provide 3-5 concrete, actionable bullet-point suggestions to improve the resume for this specific job.

Return ONLY a valid JSON object. Start your response with {{ and end with }}. Do not include markdown code block formatting (like ```json).

Use this EXACT JSON structure:
{{
  "score": 85,
  "matched_keywords": ["Python", "Docker", "REST APIs"],
  "missing_keywords": ["Kubernetes", "TypeScript", "Redis"],
  "section_scores": {{
    "experience": 80,
    "skills": 75,
    "education": 90,
    "formatting": 85
  }},
  "suggestions": [
    "Incorporate quantitative metrics to your work experience bullets (e.g., 'scaled systems by X%').",
    "Add 'Kubernetes' and 'Redis' to your skills section if you have experience with them, as they are prominently featured in the job description.",
    "Refine your professional summary to highlight backend architecture rather than general web development."
  ]
}}"""

    try:
        response = claude(prompt, max_tokens=1000, api_key=api_key)
        # Clean the response to ensure it only has JSON
        response = response.strip()
        # Remove markdown code blocks if any
        response = re.sub(r'```json\s*', '', response)
        response = re.sub(r'```\s*', '', response)
        response = response.strip()
        
        # Extract the JSON boundaries
        start = response.find('{')
        end = response.rfind('}')
        if start != -1 and end != -1:
            json_str = response[start:end+1]
            data = json.loads(json_str)
            return data
        else:
            raise ValueError("Could not locate JSON in response")
    except Exception as e:
        print(f"ATS Agent failed: {e}")
        return {
            "score": 50,
            "matched_keywords": ["Programming"],
            "missing_keywords": ["Specific Tech Stack"],
            "section_scores": {
                "experience": 50,
                "skills": 50,
                "education": 50,
                "formatting": 50
            },
            "suggestions": [
                "Ensure your resume matches the job keywords.",
                "Review the job description to match technical experience.",
                "Format your resume sections clearly."
            ]
        }

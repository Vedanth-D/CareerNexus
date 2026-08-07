import json
import re
from tools.llm import claude

def email_agent(resume_text: str, job_title: str, company: str, job_description: str, api_key: str = None) -> dict:
    """
    Generates application outreach assets: Cover Letter, Recruiter Cold Email, and LinkedIn Connection Note.
    """
    print(f"Email Agent: Generating outreach assets for {job_title} at {company}...")
    
    prompt = f"""You are a professional outreach writer and job search advisor.
Based on the candidate's resume and target job details, generate:
1. A tailored Cover Letter (approx. 250 words).
2. A Recruiter Cold Email (compelling subject line, short elevator pitch, Call to Action, under 150 words).
3. A LinkedIn Connection Note (under 300 characters, ideal for sending with an invite to a hiring manager/recruiter).

CANDIDATE RESUME:
{resume_text[:1500]}

JOB ROLE: {job_title} at {company}
JOB DESCRIPTION:
{job_description[:1000]}

Please output your response as a valid JSON object. Start your response with {{ and end with }}. Do not include markdown code block formatting.

JSON Structure:
{{
  "cover_letter": "Dear Hiring Team... [Full Cover Letter Body] ...Sincerely, Candidate",
  "recruiter_email": {{
    "subject": "Inquiry: Senior Backend Engineer - [Candidate Name]",
    "body": "Hi [Recruiter Name],\\n\\nI noticed you are hiring for... [Cold Email Body] ...\\n\\nBest regards,\\n[Candidate Name]"
  }},
  "linkedin_note": "Hi [Name], saw you are hiring for the Backend Engineer role. My experience building APIs with Python & Go matches what you are looking for. Would love to connect! - [Name]"
}}"""

    try:
        response = claude(prompt, max_tokens=1000, api_key=api_key)
        # Clean response
        response = response.strip()
        response = re.sub(r'```json\s*', '', response)
        response = re.sub(r'```\s*', '', response)
        response = response.strip()
        
        start = response.find('{')
        end = response.rfind('}')
        if start != -1 and end != -1:
            return json.loads(response[start:end+1])
        else:
            raise ValueError("No JSON boundaries found in response")
    except Exception as e:
        print(f"Email Agent failed: {e}")
        # Return fallbacks
        return {
            "cover_letter": f"Dear Hiring Team at {company},\n\nI am writing to express my interest in the {job_title} position. Given my background, I am confident I would be a great fit for your team.\n\nBest regards,\nCandidate",
            "recruiter_email": {
                "subject": f"Application for {job_title} - Candidate",
                "body": f"Hi Hiring Team,\n\nI recently applied for the {job_title} position and wanted to reach out. I have experience that aligns with your tech stack.\n\nBest regards,\nCandidate"
            },
            "linkedin_note": f"Hi, I recently saw the open {job_title} role at {company} and wanted to connect. I would love to discuss how my background aligns. Thanks!"
        }

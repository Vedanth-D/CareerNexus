import json
import re
import requests
from tools.llm import claude

def fetch_wikipedia_summary(company_name: str) -> str:
    """
    Queries Wikipedia API for a summary of the company.
    """
    try:
        search_url = "https://en.wikipedia.org/w/api.php"
        # Search for page title
        search_params = {
            "action": "query",
            "list": "search",
            "srsearch": company_name,
            "format": "json"
        }
        res = requests.get(search_url, params=search_params, timeout=8)
        search_results = res.json().get("query", {}).get("search", [])
        if not search_results:
            return ""
        
        # Retrieve the first page's title
        page_title = search_results[0]["title"]
        summary_params = {
            "action": "query",
            "prop": "extracts",
            "exintro": True,
            "explaintext": True,
            "titles": page_title,
            "format": "json"
        }
        res = requests.get(search_url, params=summary_params, timeout=8)
        pages = res.json().get("query", {}).get("pages", {})
        for page_id, page_data in pages.items():
            return page_data.get("extract", "")
    except Exception as e:
        print(f"Wikipedia fetch error: {e}")
    return ""

def company_agent(company_name: str, resume_profile: str = "", api_key: str = None) -> dict:
    """
    Researches a company using Wikipedia and Groq LLM.
    Optionally tailors a pitch tactic to the user's resume.
    """
    print(f"Company Agent: Researching {company_name}...")
    wiki_info = fetch_wikipedia_summary(company_name)
    
    prompt = f"""You are an elite business analyst and executive coach.
Compile a detailed intelligence dossier for the company '{company_name}'.

WIKIPEDIA SUMMARY OBTAINED:
{wiki_info[:1500]}

CANDIDATE RESUME PROFILE (IF AVAILABLE):
{resume_profile[:1000] if resume_profile else "No resume uploaded."}

Based on the Wikipedia information and your comprehensive knowledge, construct a detailed company profile.
Estimate values if not strictly specified (use reasonable approximations for modern tech companies).

Your output must be a valid JSON object. Start your response with {{ and end with }}. Do not include markdown code block formatting.

Required JSON Structure:
{{
  "name": "Stripe",
  "tagline": "Fintech • Payment Processing",
  "match_score": 92,
  "employees": "~8,000 Employees",
  "revenue": "Est. Revenue: $14B (2022)",
  "stage": "Late Stage Private / Pre-IPO",
  "mission": "Increase the GDP of the internet.",
  "culture_tags": ["Developer-First", "Writing Culture"],
  "tech_stack": {{
    "matching": ["Go", "React", "TypeScript", "Python"],
    "missing": ["Ruby", "Java"]
  }},
  "hq": "San Francisco, CA & Dublin, IRE",
  "branches": "Seattle, New York, London, Tokyo",
  "cheat_sheet": [
    {{
      "area": "Systems Design",
      "question": "How would you design a distributed rate limiter for API requests?"
    }},
    {{
      "area": "Product Sense",
      "question": "Identify a friction point in a common checkout flow and explain how to fix it."
    }},
    {{
      "area": "Behavioral",
      "question": "Tell me about a time you had to dive deep into an undocumented system."
    }}
  ],
  "culture_vibe": "Collaborative, high-velocity, and engineering-led.",
  "competitors": ["Adyen", "PayPal", "Checkout.com"],
  "recent_funding": "Raised $6.5B at $50B valuation (March 2023) to provide liquidity to employees.",
  "pitch_tactic": "With my background in distributed systems and Python, I am highly aligned with Stripe's focus on developer experience..."
}}"""

    try:
        response = claude(prompt, max_tokens=1200, api_key=api_key)
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
        print(f"Company Agent failed: {e}")
        # Fallback profile
        return {
            "name": company_name,
            "tagline": "Technology • Software Services",
            "match_score": 80,
            "employees": "1,000+ Employees",
            "revenue": "Private",
            "stage": "Growth Stage",
            "mission": "Innovating software solutions for global clients.",
            "culture_tags": ["Flexible", "Innovation-Driven"],
            "tech_stack": {
                "matching": ["Python", "JavaScript", "HTML"],
                "missing": ["Docker", "AWS"]
            },
            "hq": "Global",
            "branches": "Remote",
            "cheat_sheet": [
                {
                    "area": "Technical",
                    "question": "Explain a complex engineering problem you solved recently."
                }
            ],
            "culture_vibe": "Fast-paced, startup environment.",
            "competitors": ["Other Tech Firms"],
            "recent_funding": "Self-sustaining revenue growth.",
            "pitch_tactic": "I bring general software skills and Python backend developer experience that can immediately help scale your core products."
        }

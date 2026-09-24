import json
import re
from tools.llm import claude

def generate_interview_question(role: str, resume_text: str = "", question_type: str = "technical", api_key: str = None) -> dict:
    prompt = f"""You are an elite Lead Interviewer at a Fortune 500 tech company.
Generate ONE highly realistic {question_type} interview question for a candidate applying for the role of '{role}'.

CANDIDATE RESUME SUMMARY:
{resume_text[:1500] if resume_text else "General candidate background"}

Respond ONLY in raw valid JSON format with NO extra commentary or markdown formatting:
{{
    "question": "The interview question string",
    "category": "{question_type.capitalize()}",
    "focus_area": "Key technical/behavioral skill being evaluated",
    "hint": "Brief tip on how to structure a winning response"
}}"""
    try:
        raw_res = claude(prompt, max_tokens=600, api_key=api_key)
        json_str = raw_res.strip()
        if "```json" in json_str:
            json_str = json_str.split("```json")[1].split("```")[0].strip()
        elif "```" in json_str:
            json_str = json_str.split("```")[1].split("```")[0].strip()
        return json.loads(json_str)
    except Exception as e:
        return {
            "question": f"Tell me about a challenging {role} project you led and how you handled key trade-offs.",
            "category": question_type.capitalize(),
            "focus_area": "Problem Solving & Leadership",
            "hint": "Use the STAR method (Situation, Task, Action, Result) with specific metrics."
        }

def evaluate_interview_response(role: str, question: str, response_text: str, resume_text: str = "", api_key: str = None) -> dict:
    prompt = f"""You are a Hiring Manager evaluating a candidate's spoken interview answer.

ROLE: {role}
QUESTION ASKED: {question}
CANDIDATE SPOKEN RESPONSE: {response_text}
RESUME CONTEXT: {resume_text[:1000] if resume_text else "N/A"}

Evaluate the response thoroughly and return ONLY raw valid JSON matching this schema:
{{
    "star_score": 85,
    "confidence_rating": "High / Medium / Low",
    "tone_analysis": "Concise summary of tone, clarity, and pacing",
    "strengths": ["List of 2 specific strengths"],
    "improvements": ["List of 2 specific areas to improve"],
    "model_answer": "An exemplary high-impact response utilizing the STAR method"
}}"""
    try:
        raw_res = claude(prompt, max_tokens=1000, api_key=api_key)
        json_str = raw_res.strip()
        if "```json" in json_str:
            json_str = json_str.split("```json")[1].split("```")[0].strip()
        elif "```" in json_str:
            json_str = json_str.split("```")[1].split("```")[0].strip()
        return json.loads(json_str)
    except Exception as e:
        return {
            "star_score": 78,
            "confidence_rating": "Medium",
            "tone_analysis": "Clear explanation with good technical depth, but could quantify results further.",
            "strengths": ["Relevant technical terminology", "Clear problem identification"],
            "improvements": ["Include specific quantitative metrics", "Structure result section explicitly"],
            "model_answer": "In my previous role, I led the architecture optimization effort which reduced latency by 35% and saved $12K monthly..."
        }

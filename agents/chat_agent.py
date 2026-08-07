from tools.llm import get_client

def chat_agent(messages: list, resume_text: str = "", job_description: str = "", api_key: str = None) -> str:
    """
    Career AI Chat Agent that acts as a mentor/coach.
    It takes the conversation history, user's resume, and current job description,
    and returns a helpful response.
    """
    system_prompt = """You are CareerNexus AI, an elite career mentor and job application assistant.
Your goal is to help the user optimize their resume, prepare for interviews, write outreach messages, and solve any issues they describe.

You have access to the user's details:
"""
    
    if resume_text:
        system_prompt += f"\n--- USER RESUME PROFILE ---\n{resume_text[:2000]}\n"
    else:
        system_prompt += "\nNo resume uploaded yet. Advise the user to upload their resume for personalized support.\n"
        
    if job_description:
        system_prompt += f"\n--- TARGET JOB DESCRIPTION ---\n{job_description[:2000]}\n"
    
    system_prompt += """
Keep your advice professional, encouraging, and highly actionable. Reference specific parts of the resume or job description if they are relevant.
Keep replies concise, clean, and directly related to the user's request. Avoid overly wordy templates unless requested."""

    # Reconstruct the messages list with system prompt injected at the start
    groq_messages = [{"role": "system", "content": system_prompt}] + messages

    client = get_client(api_key)
    if not client:
         return "No Groq API key configured. Provide an API key in your Settings tab to chat!"

    try:
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=groq_messages,
            max_tokens=600,
            temperature=0.7
        )
        return response.choices[0].message.content
    except Exception as e:
        print(f"Chat Agent error: {e}")
        return f"I'm sorry, I encountered an error while processing your request: {e}. Please try again!"

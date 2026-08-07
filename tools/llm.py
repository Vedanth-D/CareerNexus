import os
from dotenv import load_dotenv
from groq import Groq

load_dotenv()

default_api_key = os.getenv("GROQ_API_KEY")
if not default_api_key:
    print("Warning: GROQ_API_KEY not found in .env file!")
else:
    print(f"Groq API key loaded: {default_api_key[:12]}...")

default_client = Groq(api_key=default_api_key) if default_api_key else None

def get_client(api_key: str = None) -> Groq:
    if api_key:
        return Groq(api_key=api_key)
    return default_client

def claude(prompt: str, max_tokens: int = 2000, api_key: str = None) -> str:
    client = get_client(api_key)
    if not client:
        raise ValueError("No Groq API key configured. Provide an API key or set GROQ_API_KEY in .env.")
    
    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "user", "content": prompt}],
        max_tokens=max_tokens,
        temperature=0.7
    )
    return response.choices[0].message.content
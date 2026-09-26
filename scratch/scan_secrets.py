import os
import re

patterns = [
    (r"gsk_[A-Za-z0-9_]{15,}", "Groq API Key"),
    (r"sk-[A-Za-z0-9_]{15,}", "OpenAI API Key"),
    (r"AIza[0-9A-Za-z-_]{35}", "Google API Key"),
    (r"mongodb(\+srv)?://[^\s'\"]+", "MongoDB URI"),
    (r"api[_-]?key[\"'\s:=]+[\"']([A-Za-z0-9_\-]{20,})[\"']", "Hardcoded API Key"),
    (r"secret[\"'\s:=]+[\"']([A-Za-z0-9_\-]{15,})[\"']", "Hardcoded Secret"),
    (r"password[\"'\s:=]+[\"']([A-Za-z0-9_\-]{10,})[\"']", "Hardcoded Password"),
]

ignore_dirs = {".git", "venv", "__pycache__", "node_modules"}
ignore_files = {".env.example", "scan_secrets.py"}

findings = []

for root, dirs, files in os.walk("."):
    dirs[:] = [d for d in dirs if d not in ignore_dirs]
    for file in files:
        if file in ignore_files or file.endswith(".pyc"):
            continue
        filepath = os.path.join(root, file)
        try:
            with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()
            for pattern, name in patterns:
                matches = re.findall(pattern, content, re.IGNORECASE)
                if matches:
                    findings.append((filepath, name, matches[:2]))
        except Exception as e:
            pass

print("==================================================")
print("CODEBASE SECRET & CREDENTIAL SCAN REPORT")
print("==================================================")
if not findings:
    print("[SUCCESS] Zero hardcoded secrets or credentials detected!")
else:
    for fp, name, match in findings:
        print(f"[EXPOSED SECRET] {name} in {fp}: {match}")
print("==================================================")

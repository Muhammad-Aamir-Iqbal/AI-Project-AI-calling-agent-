# test_models.py - save and run
import requests
import os
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.getenv('OPENROUTER_API_KEY')

if not API_KEY:
    print("ERROR: Add OPENROUTER_API_KEY to .env file!")
    exit(1)

print(f"Testing with key: {API_KEY[:20]}...")

# Try these exact model IDs
models = [
    "google/gemini-2.0-flash-001",
    "google/gemini-2.0-flash-exp",
    "google/gemini-pro",
    "google/gemini-2.5-flash-preview",
    "mistralai/mistral-7b-instruct",
    "mistralai/mistral-7b-instruct-v0.3",
    "meta-llama/llama-3-8b-instruct",
    "meta-llama/llama-3.1-8b-instruct",
    "nousresearch/hermes-3-llama-3.1-405b",
    "microsoft/wizardlm-2-8x22b",
]

headers = {
    "Authorization": f"Bearer {API_KEY}",
    "Content-Type": "application/json",
    "HTTP-Referer": "http://localhost:3000",
}

working_models = []

for model in models:
    print(f"\n{'='*50}")
    print(f"Testing: {model}")
    try:
        resp = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers=headers,
            json={
                "model": model,
                "messages": [{"role": "user", "content": "Say hi"}],
                "max_tokens": 10
            },
            timeout=15
        )
        
        print(f"Status: {resp.status_code}")
        
        if resp.status_code == 200:
            reply = resp.json()['choices'][0]['message']['content']
            print(f"✅ SUCCESS: {reply[:50]}")
            working_models.append(model)
        else:
            err = resp.json().get('error', {}).get('message', resp.text[:100])
            print(f"❌ FAILED: {err}")
            
    except Exception as e:
        print(f"❌ ERROR: {e}")

print(f"\n{'='*50}")
print("WORKING MODELS:")
for m in working_models:
    print(f"  ✅ {m}")
print(f"\nUse any of these in your code!")
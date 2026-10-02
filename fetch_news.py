import os
from google import genai

api_key = os.environ.get("GEMINI_API_KEY")
# Hämtar modell från miljövariabeln, eller använder gemini-3.8-flash som standard
model_name = os.environ.get("GEMINI_MODEL", "gemini-3.8-flash")

if not api_key:
    raise ValueError("GEMINI_API_KEY saknas! Se till att den skickas med i GitHub Actions.")

client = genai.Client(api_key=api_key)

response = client.models.generate_content(
    model=model_name,
    contents="Skriv en kort sammanfattning av dagens viktigaste nyheter."
)

print(response.text)

with open("latest_news.md", "w", encoding="utf-8") as f:
    f.write(response.text)

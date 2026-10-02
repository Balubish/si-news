import os
from google import genai

# Hämta nyckeln från miljövariablerna
api_key = os.environ.get("GEMINI_API_KEY")

if not api_key:
    raise ValueError("GEMINI_API_KEY saknas! Se till att den skickas med i GitHub Actions.")

# Initiera Gemini-klienten med nyckeln
client = genai.Client(api_key=api_key)

# Test-anrop eller ditt vanliga nyhetsskript
response = client.models.generate_content(
    model="gemini-2.5-flash",
    contents="Skriv en kort sammanfattning av dagens viktigaste nyheter."
)

print(response.text)

# Spara resultat till fil om det behövs
with open("latest_news.md", "w", encoding="utf-8") as f:
    f.write(response.text)

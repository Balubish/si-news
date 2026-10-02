import os
import json
import time
import feedparser
from google import genai
from google.genai.errors import ServerError, APIError

# Nyhetskällor
RSS_FEEDS = [
    "https://www.svt.se/nyheter/rss.xml",
    "http://feeds.bbci.co.uk/news/rss.xml",
    "https://techcrunch.com/feed/"
]

def fetch_rss_data():
    raw_articles = []
    for url in RSS_FEEDS:
        try:
            feed = feedparser.parse(url)
            source_name = feed.feed.get("title", "Omvärldsnyheter")
            for entry in feed.entries[:5]:  # Hämtar de 5 senaste per källa
                raw_articles.append({
                    "title": entry.get("title", ""),
                    "summary": entry.get("summary", entry.get("description", "")),
                    "link": entry.get("link", ""),
                    "source": source_name
                })
        except Exception as e:
            print(f"Fel vid hämtning från {url}: {e}")
    return raw_articles

def generate_with_retry_and_fallback(client, prompt, primary_model):
    # Lista på giltiga och aktuella modeller att prova i ordning
    models_to_try = [primary_model, "gemini-2.5-flash", "gemini-2.0-flash", "gemini-2.5-pro"]
    # Ta bort dubbletter
    models_to_try = list(dict.fromkeys(models_to_try))

    for model in models_to_try:
        print(f"Försöker med modell: {model}")
        max_retries = 3
        for attempt in range(max_retries):
            try:
                print(f"  Anropar {model} (försök {attempt + 1}/{max_retries})...")
                return client.models.generate_content(
                    model=model,
                    contents=prompt
                )
            except ServerError as e:
                # 503 / Överbelastning - vänta och försök igen
                wait_time = (attempt + 1) * 15
                print(f"  Serverbelastning hos Google ({e}). Väntar {wait_time}s...")
                time.sleep(wait_time)
            except APIError as e:
                # Om modellen inte finns (404) eller liknande - hoppa direkt till nästa modell
                print(f"  API-fel för {model}: {e}. Hoppar vidare till nästa modell...")
                break
            except Exception as e:
                print(f"  Oväntat fel för {model}: {e}. Hoppar vidare...")
                break

    raise RuntimeError("Alla modeller och återförsök misslyckades.")

def main():
    api_key = os.environ.get("GEMINI_API_KEY")
    primary_model = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")

    if not api_key:
        raise ValueError("GEMINI_API_KEY saknas i miljövariablerna!")

    client = genai.Client(api_key=api_key)
    articles = fetch_rss_data()

    prompt = f"""
    Du är chefredaktör för den autonoma nyhetskanalen SI News.
    Här är råa nyhetsnotiser från olika RSS-flöden:
    {json.dumps(articles, ensure_ascii=False, indent=2)}

    Uppgift:
    1. Välj ut de 6 viktigaste och mest intressanta nyheterna.
    2. Översätt och skriv om nyheterna till professionell, engagerande och lättläst svenska.
    3. Returnera ETT giltigt JSON-objekt med strukturen:
       {{
         "updated_at": "YYYY-MM-DD HH:MM UTC",
         "articles": [
           {{
             "title": "Belysande rubrik på svenska",
             "category": "Teknik/Världen/Ekonomi/Vetenskap",
             "summary": "En kärnfull sammanfattning på 2-3 meningar.",
             "source": "Ursprunglig källa",
             "url": "Direktlänk"
           }}
         ]
       }}

    Viktigt: Svara ENBART med ren JSON utan formatblock (som ```json).
    """

    response = generate_with_retry_and_fallback(client, prompt, primary_model)

    cleaned_text = response.text.strip()
    if cleaned_text.startswith("```"):
        cleaned_text = cleaned_text.split("\n", 1)[1].rsplit("```", 1)[0].strip()

    news_data = json.loads(cleaned_text)
    
    with open("news.json", "w", encoding="utf-8") as f:
        json.dump(news_data, f, ensure_ascii=False, indent=2)

    print("Framgångsrikt uppdaterat news.json med nya nyheter!")

if __name__ == "__main__":
    main()

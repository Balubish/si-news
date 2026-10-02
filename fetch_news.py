import os
import json
import re
import time
from datetime import datetime, timezone
import feedparser
from google import genai
from google.genai.errors import ServerError, APIError

# RSS-källor (Blandat globalt, Sverige och lokalt)
RSS_FEEDS = [
    "https://www.svt.se/nyheter/rss.xml",
    "https://sverigesradio.se/rssfeed/rssfeed.aspx?elfeed=2",
    "http://feeds.bbci.co.uk/news/world/rss.xml",
    "https://rss.nytimes.com/services/xml/rss/nyt/World.xml",
    "https://feeds.a.dj.com/rss/RSSWorldNews.xml"
]

def fetch_rss_entries():
    raw_entries = []
    for feed_url in RSS_FEEDS:
        try:
            feed = feedparser.parse(feed_url)
            feed_title = feed.feed.get("title", "Okänd källa")
            for entry in feed.entries[:10]:
                raw_entries.append({
                    "title": entry.get("title", ""),
                    "summary": entry.get("summary", entry.get("description", "")),
                    "link": entry.get("link", ""),
                    "source": feed_title
                })
        except Exception as e:
            print(f"Fel vid hämtning av RSS-flöde {feed_url}: {e}")
    return raw_entries

def process_with_gemini(client, raw_entries, primary_model):
    prompt = f"""
    Du är en professionell nyhetsredaktör. Här är en lista på dagsaktuella nyheter från olika källor:
    {json.dumps(raw_entries, ensure_ascii=False, indent=2)}

    Gör följande:
    1. Välj ut de 20 viktigaste och mest relevanta nyheterna (både stora världshändelser och viktiga svenska/lokala nyheter).
    2. Översätt alla titlar och sammanfattningar till klar och tydlig svenska.
    3. Ge varje artikel en passande kategori på svenska (t.ex. "Världen", "Sverige", "Ekonomi", "Teknik", "Klimat", "Kultur").
    4. Sammanfattningen ska vara 2-3 meningar lång.

    Svara BARA med ett giltigt JSON-objekt i följande format utan någon markdown-kod eller extra text runt omkring:
    [
      {{
        "title": "Titel på svenska",
        "summary": "Kort sammanfattning på svenska.",
        "category": "Kategori",
        "source": "Källans namn",
        "url": "Direktlänk till artikeln"
      }}
    ]
    """

    models_to_try = [
        primary_model,
        "gemini-3.5-flash-lite",
        "gemini-3.5-flash",
        "gemini-3-flash",
        "gemini-3.1-pro-preview",
        "gemini-2.5-flash"
    ]
    models_to_try = list(dict.fromkeys(models_to_try))

    for model in models_to_try:
        print(f"Försöker med modell: {model}")
        max_retries = 3
        for attempt in range(max_retries):
            try:
                print(f"  Anropar {model} (försök {attempt + 1}/{max_retries})...")
                response = client.models.generate_content(
                    model=model,
                    contents=prompt
                )
                text = response.text.strip()
                if text.startswith("```"):
                    text = re.sub(r"^```[a-zA-Z]*\n?", "", text)
                    text = re.sub(r"\n?```$", "", text).strip()
                return json.loads(text)
            except ServerError as e:
                wait_time = (attempt + 1) * 15
                print(f"  Serverbelastning hos Google ({e}). Väntar {wait_time}s...")
                time.sleep(wait_time)
            except APIError as e:
                print(f"  API-fel för {model}: {e}. Hoppar vidare till nästa modell...")
                break
            except Exception as e:
                print(f"  Oväntat fel för {model}: {e}. Hoppar vidare...")
                break

    raise RuntimeError("Alla modeller och återförsök misslyckades.")

def main():
    api_key = os.environ.get("GEMINI_API_KEY")
    primary_model = os.environ.get("GEMINI_MODEL", "gemini-3.5-flash-lite")

    if not api_key:
        raise ValueError("GEMINI_API_KEY saknas i miljövariablerna!")

    client = genai.Client(api_key=api_key)

    print("Hämtar nyheter från RSS...")
    raw_entries = fetch_rss_entries()
    
    print("Bearbetar och väljer ut top 20 med Gemini...")
    new_articles = process_with_gemini(client, raw_entries, primary_model)
    
    # Läs in befintliga nyheter om news.json redan finns
    existing_articles = []
    if os.path.exists("news.json"):
        try:
            with open("news.json", "r", encoding="utf-8") as f:
                old_data = json.load(f)
                existing_articles = old_data.get("articles", [])
        except Exception as e:
            print(f"Kunde inte läsa befintlig news.json: {e}")

    # Kombinera nya och gamla nyheter, och ta bort dubbletter baserat på URL/Länk
    seen_urls = set()
    combined_articles = []

    # Lägg till de nyaste först
    for article in new_articles:
        url = article.get("url")
        if url and url not in seen_urls:
            seen_urls.add(url)
            combined_articles.append(article)

    # Fyll på med äldre nyheter upp till max 50 st
    for article in existing_articles:
        url = article.get("url")
        if url and url not in seen_urls:
            seen_urls.add(url)
            combined_articles.append(article)

    # Spara max 50 artiklar totalt
    final_articles = combined_articles[:50]

    now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    
    output_data = {
        "updated_at": now_utc,
        "articles": final_articles
    }

    with open("news.json", "w", encoding="utf-8") as f:
        json.dump(output_data, f, ensure_ascii=False, indent=2)

    print(f"Sparade {len(final_articles)} artiklar till news.json framgångsrikt!")

if __name__ == "__main__":
    main()

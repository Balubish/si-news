import os
import json
import re
import time
from datetime import datetime, timezone
import feedparser
from google import genai
from google.genai.errors import ServerError, APIError

# Allmänna nyhetskällor
GENERAL_RSS_FEEDS = [
    "https://www.svt.se/nyheter/rss.xml",
    "https://sverigesradio.se/rssfeed/rssfeed.aspx?elfeed=2",
    "http://feeds.bbci.co.uk/news/world/rss.xml",
    "https://rss.nytimes.com/services/xml/rss/nyt/World.xml",
    "https://feeds.a.dj.com/rss/RSSWorldNews.xml"
]

# Dedikerade AI- & Robotikkällor
AI_RSS_FEEDS = [
    "https://techcrunch.com/category/artificial-intelligence/feed/",
    "https://www.theverge.com/ai-artificial-intelligence/rss/index.xml",
    "https://www.wired.com/feed/category/ai/latest/rss",
    "https://rss.nytimes.com/services/xml/rss/nyt/Technology.xml"
]

def fetch_rss_entries(feed_urls, limit_per_feed=25):
    raw_entries = []
    for feed_url in feed_urls:
        try:
            feed = feedparser.parse(feed_url)
            feed_title = feed.feed.get("title", "Okänd källa")
            # Ökat limit till 25 per flöde för att ha en större pool av nyheter
            for entry in feed.entries[:limit_per_feed]:
                
                # --- NYTT: Försök extrahera en bildlänk ---
                image_url = ""
                if 'media_content' in entry and len(entry.media_content) > 0:
                    image_url = entry.media_content[0].get('url', '')
                elif 'links' in entry:
                    for link in entry.links:
                        if link.get('rel') == 'enclosure' and 'image' in link.get('type', ''):
                            image_url = link.get('href', '')
                            break
                
                raw_entries.append({
                    "title": entry.get("title", ""),
                    "summary": entry.get("summary", entry.get("description", "")),
                    "published": entry.get("published", entry.get("updated", "Idag")),
                    "link": entry.get("link", ""),
                    "image_url": image_url, # Skickar med bilden
                    "source": feed_title
                })
        except Exception as e:
            print(f"Fel vid hämtning av RSS-flöde {feed_url}: {e}")
    return raw_entries

def process_general_news(client, raw_entries, primary_model):
    prompt = f"""
    Du är en chefredaktör. Här är allmänna nyheter från RSS (inklusive eventuella bildlänkar):
    {json.dumps(raw_entries, ensure_ascii=False, indent=2)}

    Gör följande:
    1. Skapa en "executive_briefing" med exakt 3 korta, kärnfulla punkter för dagsläget.
    2. Välj ut de 40 viktigaste DAGSAKTUELLA nyheterna för dagens datum. Slå ihop artiklar om de handlar om exakt samma händelse.
    3. Översätt alla titlar och sammanfattningar till klar svenska.
    4. I "summary": Markera 1-2 av de absolut viktigaste nyckelorden eller personerna i **fetstil**.
    5. Skriv en kort, kärnfull förklaring till varför händelsen är betydelsefull i fältet "why_it_matters".
    6. Ge varje artikel en kategori ("Sverige", "Världen", "Ekonomi", "Teknik", "Klimat", "Kultur", "Sport").
    7. SPARA "image_url" exakt som den kom in från raw_entries.

    Svara BARA med ett giltigt JSON-objekt:
    {{
      "executive_briefing": ["Punkt 1...", "Punkt 2...", "Punkt 3..."],
      "articles": [
        {{
          "title": "Titel på svenska",
          "summary": "Kort sammanfattning på 2-3 meningar där **nyckelord** är i fetstil.",
          "why_it_matters": "Kort förklaring till varför denna nyhet spelar roll.",
          "category": "Kategori",
          "source": "Källans namn",
          "url": "Direktlänk",
          "image_url": "Eventuell bildlänk från datan, annars tom sträng"
        }}
      ]
    }}
    """
    return call_gemini(client, prompt, primary_model)

def process_ai_news(client, raw_entries, primary_model):
    prompt = f"""
    Du är en specialiserad redaktör för AI, LLM, humanoid robotik och framtidsteknik.
    Här är de senaste nyhetsnotiserna:
    {json.dumps(raw_entries, ensure_ascii=False, indent=2)}

    Gör följande:
    1. Välj ut de 20 viktigaste uppdateringarna inom AI, LLM-utveckling, robotik, AI-hårdvara och AGI-forskning.
    2. Översätt titlar och sammanfattningar till klar, tekniskt korrekt svenska.
    3. I "summary": Markera 1-2 av de absolut viktigaste nyckelorden/modellerna (t.ex. OpenAI, Tesla Optimus) i **fetstil**.
    4. Skriv en kort förklaring i "why_it_matters" varför tekniken eller uppdateringen är viktig.
    5. Kategorisera som: "LLM & Modeller", "Humanoid Robotik", "AI-Hårdvara", "AGI & Forskning" eller "Säkerhet & Etik".
    6. SPARA "image_url" exakt som den kom in.

    Svara BARA med ett giltigt JSON-objekt:
    {{
      "articles": [
        {{
          "title": "Titel på svenska",
          "summary": "Kort sammanfattning på 2-3 meningar där **nyckelord** är i fetstil.",
          "why_it_matters": "Kort teknisk/framtidsfokuserad förklaring till varför detta spelar roll.",
          "category": "Kategori",
          "source": "Källans namn",
          "url": "Direktlänk",
          "image_url": "Eventuell bildlänk från datan, annars tom sträng"
        }}
      ]
    }}
    """
    return call_gemini(client, prompt, primary_model)

def call_gemini(client, prompt, primary_model):
    models_to_try = [
        primary_model,
        "gemini-3.5-flash-lite",
        "gemini-3.5-flash",
        "gemini-3-flash",
        "gemini-2.5-flash"
    ]
    models_to_try = list(dict.fromkeys(models_to_try))

    for model in models_to_try:
        max_retries = 3
        for attempt in range(max_retries):
            try:
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
                time.sleep((attempt + 1) * 10)
            except Exception as e:
                break
    raise RuntimeError("Alla Gemini-modeller misslyckades.")

def main():
    api_key = os.environ.get("GEMINI_API_KEY")
    primary_model = os.environ.get("GEMINI_MODEL", "gemini-3.5-flash-lite")

    if not api_key:
        raise ValueError("GEMINI_API_KEY saknas!")

    client = genai.Client(api_key=api_key)
    today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    # 1. HÄMTA OCH BEARBETA ALLMÄNNA NYHETER
    print("Hämtar allmänna nyheter...")
    gen_raw = fetch_rss_entries(GENERAL_RSS_FEEDS)
    gen_data = process_general_news(client, gen_raw, primary_model)
    gen_articles = gen_data.get("articles", [])
    for a in gen_articles: a["date"] = today_str

    with open("news.json", "w", encoding="utf-8") as f:
        json.dump({"updated_at": now_utc, "executive_briefing": gen_data.get("executive_briefing", []), "articles": gen_articles}, f, ensure_ascii=False, indent=2)

    # 2. HÄMTA OCH BEARBETA AI & ROBOTIK
    print("Hämtar AI & Robotik-nyheter...")
    ai_raw = fetch_rss_entries(AI_RSS_FEEDS)
    ai_data = process_ai_news(client, ai_raw, primary_model)
    ai_articles = ai_data.get("articles", [])
    for a in ai_articles: a["date"] = today_str

    with open("ai_news.json", "w", encoding="utf-8") as f:
        json.dump({"updated_at": now_utc, "articles": ai_articles}, f, ensure_ascii=False, indent=2)

    # 3. SPARA I HUVUDARKIV (archive.json)
    archive_articles = []
    if os.path.exists("archive.json"):
        try:
            with open("archive.json", "r", encoding="utf-8") as f:
                archive_articles = json.load(f).get("articles", [])
        except Exception: pass

    all_new_articles = gen_articles + ai_articles
    seen_urls = {art.get("url") for art in all_new_articles if art.get("url")}
    combined_archive = list(all_new_articles)

    for art in archive_articles:
        url = art.get("url")
        if url and url not in seen_urls:
            seen_urls.add(url)
            combined_archive.append(art)

    with open("archive.json", "w", encoding="utf-8") as f:
        json.dump({"updated_at": now_utc, "total_articles": len(combined_archive), "articles": combined_archive}, f, ensure_ascii=False, indent=2)

    # --- NYTT: 4. SPARA I DAGLIGT DATUMARKIV FÖR KALENDERFUNKTIONEN ---
    print("Sparar dagens datumarkiv...")
    os.makedirs("archive", exist_ok=True) # Skapar mappen "archive" om den inte finns
    daily_archive_filename = f"archive/news_{today_str}.json"
    
    with open(daily_archive_filename, "w", encoding="utf-8") as f:
        json.dump({"updated_at": now_utc, "articles": all_new_articles}, f, ensure_ascii=False, indent=2)

    print(f"Klar! news.json, ai_news.json, archive.json och {daily_archive_filename} är uppdaterade.")

if __name__ == "__main__":
    main()

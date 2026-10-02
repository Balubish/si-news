import json
import os
import feedparser
from google import genai

# Initiera Gemini API (hämtar nyckel automatiskt från GEMINI_API_KEY)
client = genai.Client()

# Källor: AI-forskning, tech-nyheter och officiella YouTube-flöden
SOURCES = [
    # Webbsidor & RSS
    {"type": "rss", "url": "http://export.arxiv.org/rss/cs.AI"},
    {"type": "rss", "url": "https://techcrunch.com/category/artificial-intelligence/feed/"},
    {"type": "rss", "url": "https://www.technologyreview.com/topic/artificial-intelligence/feed/"},
    # YouTube-kanaler (RSS-flöden)
    {"type": "youtube", "url": "https://www.youtube.com/feeds/videos.xml?channel_id=UCXZCJLdBC09xxGZ6gcdrc6A"}, # OpenAI
    {"type": "youtube", "url": "https://www.youtube.com/feeds/videos.xml?channel_id=UCP7QIoy2mldICKrmvU0pE7g"}, # Google DeepMind
    {"type": "youtube", "url": "https://www.youtube.com/feeds/videos.xml?channel_id=UCOqREe8S9n2y4r7-A96XWUA"}, # NVIDIA
]

def load_existing_news():
    if os.path.exists("news.json"):
        try:
            with open("news.json", "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            return []
    return []

def fetch_feed_items():
    items = []
    for source in SOURCES:
        try:
            feed = feedparser.parse(source["url"])
            for entry in feed.entries[:5]: # Max 5 senaste per källa
                item = {
                    "id": entry.get("id", entry.get("link")),
                    "title": entry.get("title", ""),
                    "summary": entry.get("summary", entry.get("description", "")),
                    "link": entry.get("link", ""),
                    "is_video": source["type"] == "youtube",
                    "video_id": entry.get("yt_videoid", "") if source["type"] == "youtube" else ""
                }
                items.append(item)
        except Exception as e:
            print(f"Fel vid hämtning från {source['url']}: {e}")
    return items

def analyze_with_gemini(item):
    prompt = f"""
    Du är chefsredaktör för den autonoma nyhetsbyrån 'SI News — Driven by AI'.
    Analysera följande nyhet eller video:
    Titel: {item['title']}
    Innehåll: {item['summary']}
    
    Klassificera nyheten i EXAKT EN av dessa kategorier:
    - AI-Modeller & AGI
    - Robotik & Fysiska system
    - Vetenskap & Material
    - Samhälle & Infrastruktur
    - Kod & Utveckling
    
    Avgör om detta är ett viktigt framsteg inom AI eller dess tillämpningar (relevant: true/false).
    Om relevant, skapa en fängslande rubrik och en kort sammanfattning (max 3 meningar) översatt till följande språk: 
    svenska (sv), engelska (en), spanska (es), tyska (de).
    
    Svara ENBART i strikt JSON-format:
    {{
      "relevant": true,
      "category": "Kategori här",
      "impact_score": 1,
      "translations": {{
        "en": {{"title": "...", "summary": "..."}},
        "sv": {{"title": "...", "summary": "..."}},
        "es": {{"title": "...", "summary": "..."}},
        "de": {{"title": "...", "summary": "..."}}
      }}
    }}
    """
    
    try:
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=prompt,
            config={'response_mime_type': 'application/json'}
        )
        return json.loads(response.text)
    except Exception as e:
        print(f"Fel vid AI-analys: {e}")
        return None

def main():
    existing_news = load_existing_news()
    existing_ids = {n["id"] for n in existing_news}
    
    raw_items = fetch_feed_items()
    new_articles = []
    
    for item in raw_items:
        if item["id"] in existing_ids:
            continue
            
        print(f"Analyserar: {item['title']}...")
        analysis = analyze_with_gemini(item)
        
        if analysis and analysis.get("relevant"):
            article = {
                "id": item["id"],
                "source_url": item["link"],
                "is_video": item["is_video"],
                "video_id": item["video_id"],
                "category": analysis["category"],
                "impact_score": analysis.get("impact_score", 5),
                "translations": analysis["translations"]
            }
            new_articles.append(article)
            existing_ids.add(item["id"])
            
    if new_articles:
        updated_news = new_articles + existing_news
        updated_news = updated_news[:50] # Behåll de 50 senaste
        
        with open("news.json", "w", encoding="utf-8") as f:
            json.dump(updated_news, f, ensure_ascii=False, indent=2)
        print(f"Sparade {len(new_articles)} nya artiklar!")
    else:
        print("Inga nya relevanta artiklar hittades just nu.")

if __name__ == "__main__":
    main()

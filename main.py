import os
import time
import requests
import logging

# Configuration des logs pour voir l'exécution dans GitHub Actions
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# Récupération de l'URL du Webhook
WEBHOOK_URL = (
    os.environ.get("DISCORD_WEBHOOK_URL") 
    or os.environ.get("WEBHOOK_URL") 
    or os.environ.get("DISCORD_BOT_TOKEN")
)

# 🎯 NOUVELLE LISTE DE MARQUES À SURVEILLER
BRANDS = [
    "stone island",
    "tommy hilfiger",
    "lacoste",
    "jack and jones",
    "stussy",
    "levis",
    "bershka",
    "h&m",
    "zara",
    "the north face"
]

# ⚠️ INDICATEURS DE CONTREFAÇON
FAKE_KEYWORDS = ["copie", "réplique", "replica", "ua", "1:1", "imitation", "fausse", "faux", "master quality"]

# ✅ INDICATEURS D'AUTHENTICITÉ
AUTH_KEYWORDS = ["facture", "ticket", "certificat", "authentique", "boite d'origine", "receipt", "boîte", "preuve d'achat"]

def get_field(item, field_name, default=None):
    if isinstance(item, dict):
        return item.get(field_name, default)
    return getattr(item, field_name, default)

def extract_price(item):
    price_raw = get_field(item, 'price')
    if isinstance(price_raw, dict):
        return price_raw.get('amount') or price_raw.get('numeric') or "N/C"
    if price_raw is not None and str(price_raw).strip() != "":
        return str(price_raw)
    return "N/C"

def extract_photo_url(item):
    photo = get_field(item, 'photo') or get_field(item, 'photos')
    if not photo:
        return None
    
    if isinstance(photo, str) and photo.startswith("http"):
        return photo
    
    if isinstance(photo, dict):
        return photo.get('url') or photo.get('full_size_url')
    
    if isinstance(photo, list) and len(photo) > 0:
        first = photo[0]
        if isinstance(first, str) and first.startswith("http"):
            return first
        if isinstance(first, dict):
            return first.get('url') or first.get('full_size_url')
        if hasattr(first, 'url'):
            return getattr(first, 'url')
            
    if hasattr(photo, 'url'):
        return getattr(photo, 'url')
        
    return None

def analyze_authenticity(description, title):
    full_text = f"{title or ''} {description or ''}".lower()
    
    for fake_word in FAKE_KEYWORDS:
        if fake_word in full_text:
            return "❌ RISQUE ÉLEVÉ", f"Mot-clé suspect trouvé : '{fake_word}'", 15158332

    has_proof = any(auth_word in full_text for auth_word in AUTH_KEYWORDS)
    if has_proof:
        return "✅ PREUVE D'AUTHENTICITÉ", "Facture / Certificat / Preuve d'achat mentionné.", 3066993

    return "⚠️ À VÉRIFIER", "Aucun document d'authenticité mentionné dans le texte.", 16776960

def send_discord(title, price, brand, link, photo_url, auth_status_title, auth_status_desc, color, description):
    if not WEBHOOK_URL:
        logging.error("❌ Erreur : WEBHOOK_URL introuvable.")
        return

    article_url = link if (link and str(link).startswith("http")) else "https://www.vinted.fr"

    payload = {
        "embeds": [{
            "title": f"🛍️ [{brand.upper()}] {title or 'Article Vinted'}",
            "url": article_url,
            "description": (description[:250] + "...") if description and len(description) > 250 else (description or "Pas de description disponible"),
            "color": color,
            "fields": [
                {
                    "name": "🛡️ Analyse d'Authenticité",
                    "value": f"**{auth_status_title}**\n{auth_status_desc}",
                    "inline": False
                },
                {
                    "name": "💰 Prix",
                    "value": f"{price} €" if price != "N/C" else "N/C",
                    "inline": True
                },
                {
                    "name": "🏷️ Marque",
                    "value": brand.capitalize(),
                    "inline": True
                }
            ],
            "footer": {"text": "Bot Vinted • Alerte Pépites"}
        }]
    }

    if photo_url and isinstance(photo_url, str) and photo_url.startswith("http"):
        payload["embeds"][0]["thumbnail"] = {"url": photo_url}

    try:
        r = requests.post(WEBHOOK_URL, json=payload, timeout=10)
        if r.status_code in [200, 204]:
            logging.info(f"✅ Notification envoyée pour : {title}")
        else:
            logging.error(f"❌ Échec envoi Discord (Code HTTP {r.status_code}) : {r.text}")
    except Exception as e:
        logging.error(f"❌ Erreur réseau lors de l'envoi Discord : {e}")

def main():
    if not WEBHOOK_URL:
        logging.critical("❌ ARRÊT : Secret DISCORD_WEBHOOK_URL manquant.")
        return

    try:
        from vinted_scraper import VintedScraper
    except ImportError:
        logging.critical("❌ 'vinted-scraper' non installé.")
        return

    logging.info("Connexion à Vinted...")
    try:
        scraper = VintedScraper("https://www.vinted.fr")
    except Exception as e:
        logging.error(f"❌ Impossible d'initialiser VintedScraper : {e}")
        return

    for brand in BRANDS:
        try:
            logging.info(f"Recherche pour la marque : {brand}")
            items = scraper.search({"search_text": brand, "order": "newest_first"})
            
            if not items:
                logging.warning(f"Aucun article trouvé pour '{brand}'.")
                continue

            count = 0
            for item in items[:5]:
                title = get_field(item, 'title', '')
                price = extract_price(item)
                link = get_field(item, 'url', '')
                description = get_field(item, 'description', '')
                photo_url = extract_photo_url(item)

                auth_title, auth_desc, color = analyze_authenticity(description, title)

                if "RISQUE ÉLEVÉ" not in auth_title:
                    send_discord(title, price, brand, link, photo_url, auth_title, auth_desc, color, description)
                    count += 1
                    if count >= 2:
                        break

            time.sleep(2)

        except Exception as e:
            logging.error(f"Erreur pour la marque {brand} : {e}")

if __name__ == "__main__":
    main()

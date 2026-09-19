import os
import json
import time
import re
import requests
import logging

# Configuration des logs
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# 📌 WEBHOOK DISCORD UNIQUE
WEBHOOK_URL = (
    os.environ.get("DISCORD_WEBHOOK_URL") 
    or os.environ.get("WEBHOOK_URL") 
    or os.environ.get("DISCORD_BOT_TOKEN")
)

# 🌐 API SITE PROFIT (Base44)
BASE44_API_URL = "https://tangible-vinted-profit-pulse.base44.app/api/analyze"

# 💾 FICHIER DES ARTICLES DÉJÀ ENVOYÉS (ANTI-DOUBLONS)
SEEN_FILE = "seen_items.json"

# 🎯 MARQUES À SURVEILLER
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

def load_seen_items():
    """Charge la liste des ID déjà notifiés."""
    if os.path.exists(SEEN_FILE):
        try:
            with open(SEEN_FILE, "r", encoding="utf-8") as f:
                return set(json.load(f))
        except Exception as e:
            logging.warning(f"Impossible de lire {SEEN_FILE} : {e}")
    return set()

def save_seen_items(seen_set):
    """Sauvegarde la liste des ID déjà notifiés (garde les 1000 derniers)."""
    try:
        items_list = list(seen_set)[-1000:]
        with open(SEEN_FILE, "w", encoding="utf-8") as f:
            json.dump(items_list, f)
    except Exception as e:
        logging.error(f"Erreur lors de la sauvegarde de {SEEN_FILE} : {e}")

def get_field(item, field_name, default=None):
    if isinstance(item, dict):
        return item.get(field_name, default)
    return getattr(item, field_name, default)

def extract_item_url(item):
    """Garantit un lien direct et valide vers l'objet Vinted."""
    url = get_field(item, 'url') or get_field(item, 'path')
    if not url:
        return "https://www.vinted.fr"
    
    url_str = str(url).strip()
    if url_str.startswith("http://") or url_str.startswith("https://"):
        return url_str
    if url_str.startswith("/"):
        return f"https://www.vinted.fr{url_str}"
    
    return f"https://www.vinted.fr/{url_str}"

def extract_price(item):
    price_raw = get_field(item, 'price')
    if isinstance(price_raw, dict):
        return price_raw.get('amount') or price_raw.get('numeric') or "N/C"
    if price_raw is not None and str(price_raw).strip() != "":
        return str(price_raw)
    return "N/C"

def parse_float_price(price_str):
    """Convertit une chaîne de prix en float de manière sécurisée."""
    if not price_str or price_str == "N/C":
        return 0.0
    try:
        cleaned = re.sub(r"[^\d.,]", "", str(price_str)).replace(",", ".")
        return float(cleaned) if cleaned else 0.0
    except ValueError:
        return 0.0

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
            return "❌ RISQUE ÉLEVÉ", f"Mot-clé suspect : '{fake_word}'", 15158332

    has_proof = any(auth_word in full_text for auth_word in AUTH_KEYWORDS)
    if has_proof:
        return "✅ PREUVE D'AUTHENTICITÉ", "Facture / Certificat / Preuve d'achat mentionné.", 3066993

    return "⚠️ À VÉRIFIER", "Aucun document d'authenticité mentionné.", 16776960

def get_profit_from_base44(title, brand, price_raw, item_url):
    """Envoie les données au site base44 pour récupérer l'estimation de profit."""
    try:
        numeric_price = parse_float_price(price_raw)
        payload = {
            "title": title,
            "brand": brand,
            "price": numeric_price,
            "url": item_url
        }
        r = requests.post(BASE44_API_URL, json=payload, timeout=8)
        if r.status_code == 200 and isinstance(r.json(), dict):
            return r.json()
    except Exception as e:
        logging.warning(f"⚠️ Erreur lors de l'appel au site base44 : {e}")
    
    return None

def send_combined_discord_alert(title, price, brand, item_url, photo_url, auth_title, auth_desc, color, description, profit_data):
    """Envoie une notification unique combinée sur Discord."""
    if not WEBHOOK_URL:
        logging.error("❌ WEBHOOK_URL introuvable.")
        return

    # Données issues de l'analyse du site base44
    resale_price = profit_data.get("estimated_resale", "N/C") if isinstance(profit_data, dict) else "N/C"
    net_profit = profit_data.get("profit", "N/C") if isinstance(profit_data, dict) else "N/C"
    score = profit_data.get("score", "N/A") if isinstance(profit_data, dict) else "N/A"

    payload = {
        "embeds": [{
            "title": f"🛍️ [{brand.upper()}] {title or 'Article Vinted'}",
            "url": item_url,
            "description": (description[:200] + "...") if description and len(description) > 200 else (description or "Pas de description disponible"),
            "color": color,
            "fields": [
                {
                    "name": "🛡️ Authenticité",
                    "value": f"**{auth_title}**\n{auth_desc}",
                    "inline": False
                },
                {
                    "name": "💰 Prix Achat",
                    "value": f"{price} €" if price != "N/C" else "N/C",
                    "inline": True
                },
                {
                    "name": "📈 Revente Est.",
                    "value": f"{resale_price} €" if str(resale_price) != "N/C" else "N/C",
                    "inline": True
                },
                {
                    "name": "💵 Profit Net",
                    "value": f"**+{net_profit} €**" if str(net_profit) != "N/C" else "N/C",
                    "inline": True
                },
                {
                    "name": "🏷️ Marque",
                    "value": brand.capitalize(),
                    "inline": True
                },
                {
                    "name": "⭐ Score Marge",
                    "value": str(score),
                    "inline": True
                },
                {
                    "name": "🔗 Lien Direct",
                    "value": f"[👉 Voir/Acheter l'article sur Vinted]({item_url})",
                    "inline": False
                }
            ],
            "footer": {"text": "Bot Vinted • Alerte & Profit Pulse Base44"}
        }]
    }

    if photo_url and isinstance(photo_url, str) and photo_url.startswith("http"):
        payload["embeds"][0]["thumbnail"] = {"url": photo_url}

    try:
        r = requests.post(WEBHOOK_URL, json=payload, timeout=10)
        if r.status_code in [200, 204]:
            logging.info(f"✅ Alerte unique envoyée pour : {title}")
        else:
            logging.error(f"❌ Erreur envoi Discord (HTTP {r.status_code}) : {r.text}")
    except Exception as e:
        logging.error(f"❌ Erreur réseau Webhook : {e}")

def main():
    if not WEBHOOK_URL:
        logging.critical("❌ ARRÊT : Secret DISCORD_WEBHOOK_URL manquant.")
        return

    try:
        from vinted_scraper import VintedScraper
    except ImportError:
        logging.critical("❌ 'vinted-scraper' non installé.")
        return

    seen_items = load_seen_items()

    logging.info("Connexion à Vinted...")
    try:
        scraper = VintedScraper("https://www.vinted.fr")
    except Exception as e:
        logging.error(f"❌ Erreur d'initialisation VintedScraper : {e}")
        return

    for brand in BRANDS:
        try:
            logging.info(f"Recherche : {brand}")
            items = scraper.search({"search_text": brand, "order": "newest_first"})
            
            if not items:
                continue

            count = 0
            for item in items[:5]:
                item_id = str(get_field(item, 'id') or extract_item_url(item))

                # Sauter si l'article a déjà été notifié
                if item_id in seen_items:
                    continue

                title = get_field(item, 'title', '')
                price = extract_price(item)
                item_url = extract_item_url(item)
                description = get_field(item, 'description', '')
                photo_url = extract_photo_url(item)

                auth_title, auth_desc, color = analyze_authenticity(description, title)

                if "RISQUE ÉLEVÉ" not in auth_title:
                    # 1. Calcul du profit via le site Base44
                    profit_data = get_profit_from_base44(title, brand, price, item_url)

                    # 2. Envoi du message unique combiné
                    send_combined_discord_alert(
                        title, price, brand, item_url, photo_url, 
                        auth_title, auth_desc, color, description, profit_data
                    )

                    # Marquer l'article comme vu
                    seen_items.add(item_id)
                    count += 1
                    if count >= 2:
                        break

            time.sleep(2)

        except Exception as e:
            logging.error(f"Erreur pour {brand} : {e}")

    # Sauvegarder la mémoire anti-doublons à la fin de l'exécution
    save_seen_items(seen_items)

if __name__ == "__main__":
    main()

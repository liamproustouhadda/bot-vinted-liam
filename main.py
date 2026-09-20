import json
import logging
import os
import re
import time
import requests

# ---------------------------------------------------------------------------
# CONFIGURATION
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)

# 📌 WEBHOOK 1 : Salon Général (Tous les articles)
WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL") or os.environ.get("WEBHOOK_URL")

# 🔥 WEBHOOK 2 : Salon Pépites / Meilleures affaires (Score >= 7.0)
BEST_WEBHOOK_URL = os.environ.get("DISCORD_BEST_WEBHOOK_URL") or os.environ.get("BEST_WEBHOOK_URL")

# Seuil de note pour le salon pépites
HIGH_SCORE_THRESHOLD = 7.0

# API d'estimation de rentabilité
BASE44_API_URL = "https://tangible-vinted-profit-pulse.base44.app/api/analyze"

# Mémoire anti-doublons
SEEN_FILE = "seen_items.json"

# Cote estimée par marque (Multiplicateur de revente)
BRAND_MULTIPLIERS = {
    "stone island": 1.65,
    "stussy": 1.55,
    "the north face": 1.50,
    "lacoste": 1.40,
    "tommy hilfiger": 1.35,
    "levis": 1.30,
    "jack and jones": 1.25,
    "zara": 1.20,
    "bershka": 1.15,
    "h&m": 1.15,
}

FAKE_KEYWORDS = ["copie", "réplique", "replica", "ua", "1:1", "imitation", "fausse", "faux", "master quality"]
AUTH_KEYWORDS = ["facture", "ticket", "certificat", "authentique", "boite d'origine", "receipt", "boîte", "preuve d'achat"]


# ---------------------------------------------------------------------------
# FONCTIONS DE GESTION DES DONNÉES ET PARSING
# ---------------------------------------------------------------------------
def load_seen_items():
    if os.path.exists(SEEN_FILE):
        try:
            with open(SEEN_FILE, "r", encoding="utf-8") as f:
                return set(json.load(f))
        except Exception:
            pass
    return set()


def save_seen_items(seen_set):
    try:
        items_list = list(seen_set)[-1000:]
        with open(SEEN_FILE, "w", encoding="utf-8") as f:
            json.dump(items_list, f)
    except Exception as e:
        logging.error(f"Erreur sauvegarde {SEEN_FILE} : {e}")


def get_field(item, field_name, default=None):
    if isinstance(item, dict):
        return item.get(field_name, default)
    return getattr(item, field_name, default)


def extract_item_url(item):
    url = get_field(item, "url") or get_field(item, "path")
    if not url:
        return "https://www.vinted.fr"
    url_str = str(url).strip()
    if url_str.startswith("http://") or url_str.startswith("https://"):
        return url_str
    if url_str.startswith("/"):
        return f"https://www.vinted.fr{url_str}"
    return f"https://www.vinted.fr/{url_str}"


def extract_price(item):
    price_raw = get_field(item, "price")
    if isinstance(price_raw, dict):
        return price_raw.get("amount") or price_raw.get("numeric") or "N/C"
    if price_raw is not None and str(price_raw).strip() != "":
        return str(price_raw)
    return "N/C"


def parse_float_price(price_str):
    if not price_str or price_str == "N/C":
        return 0.0
    try:
        cleaned = re.sub(r"[^\d.,]", "", str(price_str)).replace(",", ".")
        return float(cleaned) if cleaned else 0.0
    except ValueError:
        return 0.0


def extract_photo_url(item):
    photo = get_field(item, "photo") or get_field(item, "photos")
    if not photo:
        return None
    if isinstance(photo, str) and photo.startswith("http"):
        return photo
    if isinstance(photo, dict):
        return photo.get("url") or photo.get("full_size_url")
    if isinstance(photo, list) and len(photo) > 0:
        first = photo[0]
        if isinstance(first, str) and first.startswith("http"):
            return first
        if isinstance(first, dict):
            return first.get("url") or first.get("full_size_url")
        if hasattr(first, "url"):
            return getattr(first, "url")
    if hasattr(photo, "url"):
        return getattr(photo, "url")
    return None


# ---------------------------------------------------------------------------
# ANALYSE & CALCULS
# ---------------------------------------------------------------------------
def analyze_authenticity(description, title):
    full_text = f"{title or ''} {description or ''}".lower()
    for fake_word in FAKE_KEYWORDS:
        if fake_word in full_text:
            return ("❌ RISQUE ÉLEVÉ", f"Mot-clé suspect détecté : '{fake_word}'", 15158332)

    has_proof = any(auth_word in full_text for auth_word in AUTH_KEYWORDS)
    if has_proof:
        return ("✅ PREUVE D'AUTHENTICITÉ", "Facture / Certificat / Preuve d'achat mentionné.", 3066993)

    return ("⚠️ À VÉRIFIER", "Aucun document d'authenticité mentionné.", 16776960)


def calculate_local_profit(brand, buy_price):
    if buy_price <= 0:
        return {"estimated_resale": "N/C", "profit": "N/C", "score": "N/A"}

    multiplier = BRAND_MULTIPLIERS.get(brand.lower(), 1.30)
    estimated_resale = round(buy_price * multiplier, 2)
    estimated_fees = round(estimated_resale * 0.08, 2)
    net_profit = round(estimated_resale - buy_price - estimated_fees, 2)

    if net_profit >= 25:
        score = "🔥 9.5/10 (Excellente)"
    elif net_profit >= 15:
        score = "⚡ 8.0/10 (Très Bonne)"
    elif net_profit >= 8:
        score = "✅ 6.5/10 (Correcte)"
    elif net_profit > 0:
        score = "⚠️ 4.0/10 (Faible)"
    else:
        score = "❌ 2.0/10 (Non Rentable)"

    return {
        "estimated_resale": f"{estimated_resale:.2f}",
        "profit": f"{net_profit:.2f}",
        "score": score,
    }


def get_profit_data(title, brand, price_raw, item_url):
    numeric_price = parse_float_price(price_raw)
    try:
        payload = {"title": title, "brand": brand, "price": numeric_price, "url": item_url}
        r = requests.post(BASE44_API_URL, json=payload, timeout=5)
        if r.status_code == 200 and isinstance(r.json(), dict):
            data = r.json()
            if "estimated_resale" in data or "profit" in data:
                return data
    except Exception as e:
        logging.warning(f"⚠️ API externe indisponible ({e}). Utilisation du calcul local.")

    return calculate_local_profit(brand, numeric_price)


def extract_numeric_score(profit_data):
    if not profit_data or not isinstance(profit_data, dict):
        return -999.0

    score_val = profit_data.get("score")
    if isinstance(score_val, (int, float)):
        return float(score_val)

    score_str = str(score_val or "")
    match = re.search(r"(\d+(?:\.\d+)?)", score_str)
    if match:
        try:
            return float(match.group(1))
        except ValueError:
            pass

    return parse_float_price(profit_data.get("profit", 0))


# ---------------------------------------------------------------------------
# ENVOI DISCORD
# ---------------------------------------------------------------------------
def send_combined_discord_alert(title, price, brand, item_url, photo_url, auth_title, auth_desc, color, description, profit_data, target_webhook):
    if not target_webhook:
        return

    resale_price = profit_data.get("estimated_resale", "N/C")
    net_profit = profit_data.get("profit", "N/C")
    score = profit_data.get("score", "N/A")

    payload = {
        "embeds": [
            {
                "title": f"🛍️ [{brand.upper()}] {title or 'Article Vinted'}",
                "url": item_url,
                "description": (description[:200] + "...") if description and len(description) > 200 else (description or "Pas de description disponible"),
                "color": color,
                "fields": [
                    {"name": "🛡️ Authenticité", "value": f"**{auth_title}**\n{auth_desc}", "inline": False},
                    {"name": "💰 Prix Achat", "value": f"{price} €" if price != "N/C" else "N/C", "inline": True},
                    {"name": "📈 Revente Est.", "value": f"{resale_price} €" if str(resale_price) != "N/C" else "N/C", "inline": True},
                    {"name": "💵 Profit Net", "value": f"**+{net_profit} €**" if str(net_profit) != "N/C" else "N/C", "inline": True},
                    {"name": "🏷️ Marque", "value": brand.capitalize(), "inline": True},
                    {"name": "⭐ Score Marge", "value": str(score), "inline": True},
                    {"name": "🔗 Lien Direct", "value": f"[👉 Voir/Acheter l'article sur Vinted]({item_url})", "inline": False},
                ],
                "footer": {"text": "Bot Vinted • Profit Pulse Auto"},
            }
        ]
    }

    if photo_url and isinstance(photo_url, str) and photo_url.startswith("http"):
        payload["embeds"][0]["thumbnail"] = {"url": photo_url}

    try:
        r = requests.post(target_webhook, json=payload, timeout=10)
        if r.status_code in [200, 204]:
            logging.info(f"✅ Alerte Discord envoyée : {title} | Note: {score}")
        else:
            logging.error(f"❌ Refus Discord (Code HTTP {r.status_code}) : {r.text}")
    except Exception as e:
        logging.error(f"❌ Erreur réseau Webhook : {e}")


# ---------------------------------------------------------------------------
# SCRIPT PRINCIPAL
# ---------------------------------------------------------------------------
def main():
    logging.info("--- CONTRÔLE DES WEBHOOKS ---")
    if not WEBHOOK_URL:
        logging.critical("❌ ARRÊT : Secret 'DISCORD_WEBHOOK_URL' manquant dans les variables d'environnement.")
        return
    else:
        logging.info("✅ Webhook Général configuré.")

    if not BEST_WEBHOOK_URL:
        logging.warning("⚠️ Webhook 'DISCORD_BEST_WEBHOOK_URL' non configuré. Les pépites seront uniquement sur le salon général.")
    else:
        logging.info("✅ Webhook Pépites configuré.")

    try:
        from vinted_scraper import VintedScraper
    except ImportError:
        logging.critical("❌ 'vinted-scraper' n'est pas installé. Exécutez : pip install vinted-scraper")
        return

    seen_items = load_seen_items()
    logging.info(f"💾 {len(seen_items)} articles déjà vus en mémoire.")

    try:
        scraper = VintedScraper("https://www.vinted.fr")
    except Exception as e:
        logging.error(f"❌ Impossible d'initialiser VintedScraper : {e}")
        return

    brands = list(BRAND_MULTIPLIERS.keys())
    all_analyzed_items = []

    # 1. RECUEIL ET ANALYSE
    for brand in brands:
        try:
            logging.info(f"🔎 Recherche : {brand}")
            items = scraper.search({"search_text": brand, "order": "newest_first"})

            if not items:
                logging.warning(f"⚠️ Aucun résultat renvoyé pour {brand}.")
                continue

            for item in items[:5]:
                item_id = str(get_field(item, "id") or extract_item_url(item))

                if item_id in seen_items:
                    continue

                title = get_field(item, "title", "")
                price = extract_price(item)
                item_url = extract_item_url(item)
                description = get_field(item, "description", "")
                photo_url = extract_photo_url(item)

                auth_title, auth_desc, color = analyze_authenticity(description, title)

                # Si risque élevé de contrefaçon -> Note minimale
                if "RISQUE ÉLEVÉ" in auth_title:
                    profit_data = {"estimated_resale": "N/C", "profit": "N/C", "score": "❌ Risque Contrefaçon"}
                    numeric_score = -1.0
                else:
                    profit_data = get_profit_data(title, brand, price, item_url)
                    numeric_score = extract_numeric_score(profit_data)

                all_analyzed_items.append({
                    "item_id": item_id,
                    "title": title,
                    "price": price,
                    "brand": brand,
                    "item_url": item_url,
                    "photo_url": photo_url,
                    "auth_title": auth_title,
                    "auth_desc": auth_desc,
                    "color": color,
                    "description": description,
                    "profit_data": profit_data,
                    "numeric_score": numeric_score,
                })

            time.sleep(1)

        except Exception as e:
            logging.error(f"❌ Erreur sur la recherche de {brand} : {e}")

    # 2. 🎯 TRI DÉCROISSANT (Les notes les plus hautes / pépites en PREMIER)
    all_analyzed_items.sort(key=lambda x: x["numeric_score"], reverse=True)

    logging.info(f"📊 TOTAL : {len(all_analyzed_items)} nouveaux articles triés du meilleur au moins bon.")

    # 3. DISTRIBUTION DANS LES SALONS DISCORD
    for item in all_analyzed_items:
        # A. Envoi dans le Salon Général (Chaque article trouvé)
        send_combined_discord_alert(
            item["title"], item["price"], item["brand"], item["item_url"],
            item["photo_url"], item["auth_title"], item["auth_desc"], item["color"],
            item["description"], item["profit_data"], target_webhook=WEBHOOK_URL
        )

        # B. Envoi dans le Salon Pépites (Si note >= 7.0/10 ET deuxième webhook présent)
        if BEST_WEBHOOK_URL and item["numeric_score"] >= HIGH_SCORE_THRESHOLD:
            logging.info(f"🔥 [PÉPITE REÇUE] Score {item['numeric_score']}/10 -> Redirection vers le salon Pépites.")
            send_combined_discord_alert(
                item["title"], item["price"], item["brand"], item["item_url"],
                item["photo_url"], item["auth_title"], item["auth_desc"], item["color"],
                item["description"], item["profit_data"], target_webhook=BEST_WEBHOOK_URL
            )

        seen_items.add(item["item_id"])
        time.sleep(1.2)  # Temporalisation anti-spam API Discord

    save_seen_items(seen_items)
    logging.info("🏁 Exécution terminée.")


if __name__ == "__main__":
    main()

import os
import requests
from vinted_scraper import VintedScraper

# Webhook Discord récupéré depuis GitHub Secrets
WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL")

# 🎯 MARQUES À SURVEILLER
BRANDS = [
    "ralph lauren", "nike", "adidas", 
    "gucci", "louis vuitton", "prada", 
    "balenciaga", "dior", "moncler", "burberry"
]

# ⚠️ INDICATEURS DE CONTREFAÇON
FAKE_KEYWORDS = ["copie", "réplique", "replica", "ua", "1:1", "imitation", "fausse", "faux", "master quality"]

# ✅ INDICATEURS D'AUTHENTICITÉ
AUTH_KEYWORDS = ["facture", "ticket", "certificat", "authentique", "boite d'origine", "receipt", "boîte", "preuve d'achat"]

def analyze_authenticity(description, title):
    full_text = f"{title} {description}".lower()
    
    # 1. Risque élevé de contrefaçon
    for fake_word in FAKE_KEYWORDS:
        if fake_word in full_text:
            return "❌ RISQUE ÉLEVÉ", f"Mot-clé suspect trouvé : '{fake_word}'", 15158332  # Rouge

    # 2. Preuve d'authenticité détectée
    has_proof = any(auth_word in full_text for auth_word in AUTH_KEYWORDS)
    if has_proof:
        return "✅ PREUVE D'AUTHENTICITÉ", "Facture / Certificat / Preuve d'achat mentionné.", 3066993  # Vert

    # 3. À vérifier soi-même
    return "⚠️ À VÉRIFIER", "Aucun document d'authenticité mentionné dans le texte.", 16776960  # Jaune

def send_discord(title, price, brand, link, photo_url, auth_status_title, auth_status_desc, color, description):
    if not WEBHOOK_URL:
        print("Erreur : Secret DISCORD_WEBHOOK_URL non trouvé dans GitHub Secrets.")
        return

    payload = {
        "embeds": [{
            "title": f"🛍️ [{brand.upper()}] {title}",
            "url": link,
            "description": description[:250] + "..." if len(description) > 250 else description,
            "color": color,
            "fields": [
                {
                    "name": "🛡️ Analyse d'Authenticité",
                    "value": f"**{auth_status_title}**\n{auth_status_desc}",
                    "inline": False
                },
                {
                    "name": "💰 Prix",
                    "value": f"{price} €",
                    "inline": True
                },
                {
                    "name": "🏷️ Marque",
                    "value": brand.capitalize(),
                    "inline": True
                }
            ],
            "footer": {"text": "Bot Vinted • Alerte Pépites & Luxe"}
        }]
    }

    if photo_url:
        payload["embeds"][0]["thumbnail"] = {"url": photo_url}

    r = requests.post(WEBHOOK_URL, json=payload)
    print(f"Statut envoi Discord : {r.status_code}")

def main():
    print("Recherche des derniers articles sur Vinted...")
    scraper = VintedScraper("https://www.vinted.fr")

    for brand in BRANDS:
        try:
            print(f"Analyse de la marque : {brand}")
            items = scraper.search({"search_text": brand, "order": "newest_first"})
            
            count = 0
            for item in items[:5]:
                title = getattr(item, 'title', '')
                price = getattr(item, 'price', '')
                link = getattr(item, 'url', '')
                description = getattr(item, 'description', '')
                photo_url = getattr(item, 'photo', None)

                auth_title, auth_desc, color = analyze_authenticity(description, title)

                # Envoi sur Discord si pas de risque évident
                if "RISQUE ÉLEVÉ" not in auth_title:
                    send_discord(title, price, brand, link, photo_url, auth_title, auth_desc, color, description)
                    count += 1
                    if count >= 2:
                        break

        except Exception as e:
            print(f"Erreur pour la marque {brand} : {e}")

if __name__ == "__main__":
    main()

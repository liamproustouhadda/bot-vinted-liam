import zipfile

fichiers = {
    "requirements.txt": "requests\nvinted-scraper\n",
    ".github/workflows/vinted.yml": """name: Bot Vinted Discord

on:
  schedule:
    - cron: '*/15 * * * *'
  workflow_dispatch:

jobs:
  scrape:
    runs-on: ubuntu-latest
    steps:
      - name: Récupérer le code
        uses: actions/checkout@v4

      - name: Configurer Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'

      - name: Installer les dépendances
        run: |
          python -m pip install --upgrade pip
          pip install -r requirements.txt

      - name: Exécuter le script Vinted
        env:
          DISCORD_WEBHOOK_URL: ${{ secrets.DISCORD_WEBHOOK_URL }}
        run: python main.py
""",
    "main.py": """import os
import requests
from vinted_scraper import VintedScraper

WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL")

BRANDS = [
    "ralph lauren", "nike", "adidas", 
    "gucci", "louis vuitton", "prada", 
    "balenciaga", "dior", "moncler", "burberry"
]

FAKE_KEYWORDS = ["copie", "réplique", "replica", "ua", "1:1", "imitation", "fausse", "faux", "master quality"]
AUTH_KEYWORDS = ["facture", "ticket", "certificat", "authentique", "boite d'origine", "receipt", "boîte", "preuve d'achat"]

def analyze_authenticity(description, title):
    full_text = f"{title} {description}".lower()
    
    for fake_word in FAKE_KEYWORDS:
        if fake_word in full_text:
            return "❌ RISQUE ÉLEVÉ", f"Mot-clé suspect trouvé : '{fake_word}'", 15158332

    has_proof = any(auth_word in full_text for auth_word in AUTH_KEYWORDS)
    if has_proof:
        return "✅ PREUVE D'AUTHENTICITÉ", "Facture / Certificat / Preuve d'achat mentionné.", 3066993

    return "⚠️ À VÉRIFIER", "Aucun document d'authenticité mentionné dans le texte.", 16776960

def send_discord(title, price, brand, link, photo_url, auth_status_title, auth_status_desc, color, description):
    if not WEBHOOK_URL:
        print("Erreur : Secret DISCORD_WEBHOOK_URL non trouvé.")
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
                    "value": f"**{auth_status_title}**\\n{auth_status_desc}",
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

                if "RISQUE ÉLEVÉ" not in auth_title:
                    send_discord(title, price, brand, link, photo_url, auth_title, auth_desc, color, description)
                    count += 1
                    if count >= 2:
                        break

        except Exception as e:
            print(f"Erreur pour la marque {brand} : {e}")

if __name__ == "__main__":
    main()
"""
}

with zipfile.ZipFile("bot_vinted.zip", "w") as zip_file:
    for chemin, contenu in fichiers.items():
        zip_file.writestr(chemin, contenu)

print("✅ Fichier bot_vinted.zip prêt !")
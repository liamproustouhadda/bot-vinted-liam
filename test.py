import requests

# Remplace les guillemets ci-dessous par le lien copié à l'étape 1
URL_SALON_2 = "https://discord.com/api/webhooks/..." 

r = requests.post(URL_SALON_2, json={"content": "👋 Test : Est-ce que tu me reçois ?"})

if r.status_code in [200, 204]:
    print("✅ Le webhook marche ! Le message est arrivé sur Discord.")
else:
    print(f"❌ Problème avec le lien (Erreur {r.status_code}). Réenvoie un nouveau webhook.")

# Demo Pre-Flight Checklist

> **CAB-1061** | Run this checklist **30 minutes before** the presentation.
> Target: 24 February 2026 | "ESB is Dead"

---

## T-24h : Preparation

- [ ] Dry-run complet fait (< 5 min)
- [ ] Video backup enregistree et accessible offline
- [ ] Slide deck export en PDF (backup si PowerPoint plante)
- [ ] QR code genere et teste (pointe vers https://docs.gostoa.dev)

## T-30min : Infrastructure

### Connectivity

- [ ] Wifi stable (tester avec speed test)
- [ ] Hotspot mobile pret en backup
- [ ] VPN deconnecte (eviter latence)

### Services UP

Verifier que chaque service repond :

```bash
# Health checks — tout doit retourner 200
curl -s -o /dev/null -w "%{http_code}" https://portal.gostoa.dev     # Portal
curl -s -o /dev/null -w "%{http_code}" https://console.gostoa.dev    # Console
curl -s -o /dev/null -w "%{http_code}" https://api.gostoa.dev/health/ready  # API
curl -s -o /dev/null -w "%{http_code}" https://auth.gostoa.dev       # Keycloak
```

- [ ] Portal : 200
- [ ] Console : 200
- [ ] API : 200
- [ ] Keycloak : 200

### Seed Data

```bash
# Obtenir un token (necessaire pour les endpoints portal)
TOKEN=$(curl -s -X POST "https://auth.gostoa.dev/realms/stoa/protocol/openid-connect/token" \
  -d "grant_type=password&client_id=control-plane-ui&username=anorak&password=demo" \
  | python3 -c "import sys,json; print(json.load(sys.stdin).get('access_token',''))")

# Verifier que les APIs demo sont dans le catalogue
curl -s -H "Authorization: Bearer $TOKEN" \
  "https://api.gostoa.dev/v1/portal/apis?search=petstore" | python3 -m json.tool | head -5
```

- [ ] Petstore API visible dans le catalogue
- [ ] Account Management API visible
- [ ] Payments API visible

Si les APIs manquent, re-executer le seed :

```bash
ANORAK_PASSWORD=<password> python scripts/seed-demo-data.py
```

---

## T-15min : Navigateur

### Setup onglets

Ouvrir dans cet ordre (Chrome recommande) :

| Onglet | URL | Pre-condition |
|--------|-----|---------------|
| 1 | https://portal.gostoa.dev/apis | Logged in as **art3mis** |
| 2 | https://console.gostoa.dev | Logged in as **parzival** |
| 3 | Slide deck | Sur la slide titre |

### Pre-auth sessions

1. **Portal** — Se connecter en tant que art3mis
   - Aller sur https://portal.gostoa.dev
   - Login SSO avec credentials art3mis
   - Verifier que le catalogue s'affiche
   - **Ne pas fermer l'onglet** (la session Keycloak reste active)

2. **Console** — Se connecter en tant que parzival
   - Aller sur https://console.gostoa.dev
   - Login Keycloak avec credentials parzival
   - Verifier que le Dashboard s'affiche
   - **Ne pas fermer l'onglet**

### Etat du navigateur

- [ ] Notifications navigateur desactivees
- [ ] Mode "Ne pas deranger" active (macOS)
- [ ] Historique/favoris barre masquee
- [ ] Zoom navigateur a 125% (lisibilite salle)
- [ ] Dark mode desactive (meilleure projection)
- [ ] Onglets personnels fermes

---

## T-5min : Verification scenario

### Portal (onglet 1)

- [ ] API Catalog charge avec les 3 APIs
- [ ] Recherche "petstore" retourne un resultat
- [ ] Page detail Petstore API s'ouvre
- [ ] Onglets Endpoints et OpenAPI Spec fonctionnent
- [ ] Bouton Subscribe visible

### Console (onglet 2)

- [ ] Dashboard affiche les stats
- [ ] Page Applications montre "Gunter Analytics Dashboard" en Pending
- [ ] API Monitoring accessible

### Subscription test (optionnel)

Si aucune souscription active n'existe pour la demo :

1. Portal > Petstore API > Subscribe
2. Selectionner "OASIS Mobile App" + "Standard Plan"
3. Verifier que l'API Key est generee
4. Tester dans le Sandbox : `GET /pets` → 200 OK

> **Note** : Si la souscription existe deja (409), c'est normal et idempotent.
> Aller dans My Subscriptions pour montrer la souscription existante.

---

## Plan B : Si ca plante

| Scenario | Action immediate |
|----------|-----------------|
| Wifi down | Basculer sur hotspot mobile |
| Portal down | Passer aux screenshots dans le slide deck |
| Keycloak down | Mentionner "environnement en maintenance" et montrer la video backup |
| Subscribe erreur | Montrer My Subscriptions (souscription existante) |
| Test Sandbox 500 | Ouvrir terminal, faire un `curl` direct |
| Tout down | Lancer la video backup (offline) |

### Commande curl de secours

```bash
# Test direct via httpbin (toujours disponible, retourne 200)
curl -s https://httpbin.org/anything/pets?status=available | python3 -m json.tool | head -20
```

---

## Post-demo

- [ ] Collecter contacts (cartes de visite / QR code LinkedIn)
- [ ] Noter les questions posees
- [ ] Screenshot du slide final avec QR code (partager sur LinkedIn)

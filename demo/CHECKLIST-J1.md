# Checklist J-1 — Verifications avant demo

> **CAB-1074** | A executer **la veille** de la presentation.
> Demo cible : 24 February 2026 | "Excel + mails -> Portal + 2 clics"

---

## J-1 : Preparation complete

### Infrastructure

- [ ] **Portal UP** — `curl -s -o /dev/null -w "%{http_code}" https://portal.gostoa.dev` -> 200
- [ ] **Console UP** — `curl -s -o /dev/null -w "%{http_code}" https://console.gostoa.dev` -> 200
- [ ] **API UP** — `curl -s -o /dev/null -w "%{http_code}" https://api.gostoa.dev/health/ready` -> 200
- [ ] **Keycloak UP** — `curl -s -o /dev/null -w "%{http_code}" https://auth.gostoa.dev` -> 200

Script rapide :

```bash
for url in \
  https://portal.gostoa.dev \
  https://console.gostoa.dev \
  https://api.gostoa.dev/health/ready \
  https://auth.gostoa.dev; do
  code=$(curl -s -o /dev/null -w "%{http_code}" "$url")
  echo "$code $url"
done
```

### Donnees de demo

- [ ] **Seed execute** — Les 3 APIs sont dans le catalogue

```bash
# Obtenir un token (necessaire pour les endpoints portal)
TOKEN=$(curl -s -X POST "https://auth.gostoa.dev/realms/stoa/protocol/openid-connect/token" \
  -d "grant_type=password&client_id=control-plane-ui&username=anorak&password=demo" \
  | python3 -c "import sys,json; print(json.load(sys.stdin).get('access_token',''))")

# Verifier les APIs demo
curl -s -H "Authorization: Bearer $TOKEN" \
  "https://api.gostoa.dev/v1/portal/apis" | python3 -m json.tool | grep -c '"name"'
# Attendu : >= 3 (Petstore, Account Management, Payments)
```

- [ ] **Petstore API** visible dans le catalogue
- [ ] **Account Management API** visible
- [ ] **Payments API** visible
- [ ] **OASIS Mobile App** existe (application active)
- [ ] **Gunter Analytics Dashboard** en statut **Pending** (pour l'Acte 3 — Approval)

Si les donnees manquent :

```bash
ANORAK_PASSWORD=<password> python scripts/seed-demo-data.py
```

### Comptes Keycloak

- [ ] **art3mis** peut se connecter sur le Portal

```bash
# Test auth art3mis
curl -s -X POST https://auth.gostoa.dev/realms/stoa/protocol/openid-connect/token \
  -d "grant_type=password&client_id=portal-ui&username=art3mis&password=<password>" \
  | python3 -c "import sys,json; t=json.load(sys.stdin); print('OK' if 'access_token' in t else 'FAIL')"
```

- [ ] **parzival** peut se connecter sur la Console

```bash
# Test auth parzival
curl -s -X POST https://auth.gostoa.dev/realms/stoa/protocol/openid-connect/token \
  -d "grant_type=password&client_id=console-ui&username=parzival&password=<password>" \
  | python3 -c "import sys,json; t=json.load(sys.stdin); print('OK' if 'access_token' in t else 'FAIL')"
```

---

## J-1 : Dry Run

### Dry Run 1 — Technique (filmer en `dry-run-1.mp4`)

Derouler le script complet (SCRIPT.md) en filmant l'ecran :

- [ ] **Acte 1 — Intro** : Texte fluide, < 30s
- [ ] **Acte 2 — Discovery** : Catalogue -> Recherche -> Spec -> Subscribe -> Try It
  - [ ] Recherche "petstore" fonctionne
  - [ ] Page detail affiche Endpoints + OpenAPI Spec
  - [ ] Subscribe genere une API Key
  - [ ] Try It retourne 200 OK
- [ ] **Acte 3 — Approval** : Console -> Applications -> Approve
  - [ ] Gunter Analytics Dashboard visible en Pending
  - [ ] Approve fonctionne (ou 409 si deja fait -> noter pour le reset)
  - [ ] Monitoring affiche des donnees
- [ ] **Acte 4 — API Call** : Terminal -> curl -> Dashboard
  - [ ] curl avec API Key retourne 200 + donnees JSON
  - [ ] Metriques visibles dans le dashboard
- [ ] **Acte 5 — Outro** : Texte fluide, < 30s
- [ ] **Timing total** : < 5 min

### Reset entre dry runs

Apres un dry run, il faut reinitialiser :

```bash
# Re-seed pour reinitialiser les statuts (idempotent)
ANORAK_PASSWORD=<password> python scripts/seed-demo-data.py
```

Verifier que **Gunter Analytics Dashboard** est bien en **Pending** a nouveau.

### Dry Run 2 — Fluide (filmer en `dry-run-2.mp4`)

- [ ] Memes verifications que Dry Run 1
- [ ] Transitions fluides (pas d'hesitation entre les onglets)
- [ ] Texte dit sans regarder le script
- [ ] Timing < 5 min
- [ ] Pas de bug rencontre

### Backup Video (filmer en `backup-final.mp4`)

- [ ] **Meilleur dry run** selectionne ou nouvel enregistrement HD
- [ ] Resolution >= 1080p
- [ ] Audio clair (micro teste)
- [ ] Fichier accessible **offline** (pas sur le cloud uniquement)
- [ ] Teste en lecture complete sans coupure

---

## J-1 : Materiel

### Laptop

- [ ] Batterie > 80% ou branche secteur
- [ ] Adaptateur HDMI/USB-C pour le projecteur
- [ ] Luminosite ecran au max
- [ ] Mode "Ne pas deranger" active
- [ ] Notifications desactivees (Slack, Mail, Calendar)
- [ ] Onglets personnels fermes

### Navigateur (Chrome recommande)

- [ ] Zoom a **125%** (lisibilite salle)
- [ ] Dark mode **desactive** (meilleure projection)
- [ ] Barre de favoris **masquee**
- [ ] Historique barre d'adresse nettoyee (pas d'URL embarrassante en autocomplete)
- [ ] Extensions non essentielles desactivees

### Reseau

- [ ] Wifi du lieu teste (ou confirmation de l'orga)
- [ ] Hotspot mobile pret en backup (verifier forfait data)
- [ ] VPN **deconnecte**

### Slides

- [ ] Slide deck export en **PDF** (backup si PowerPoint plante)
- [ ] QR code genere et teste -> https://docs.gostoa.dev
- [ ] Screenshots de secours integres dans le deck (Plan B)

---

## J-1 : Recap final

| Element | Statut |
|---------|--------|
| Infrastructure UP (4 services) | [ ] |
| Donnees seedees (3 APIs, 2 apps) | [ ] |
| Comptes OK (art3mis, parzival) | [ ] |
| Dry Run 1 filme | [ ] |
| Dry Run 2 filme | [ ] |
| Backup video HD offline | [ ] |
| Materiel pret | [ ] |
| Slides + QR code | [ ] |

> **Regle** : Si un element est KO, le fixer **maintenant**. Pas le jour J.

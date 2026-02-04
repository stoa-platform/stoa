# Demo Script — "Excel + mails -> Portal + 2 clics" (5 min)

> **CAB-1074** | Presentation: 24 February 2026
> Presenter: Christophe Aboulicam | Platform: STOA

---

## Vue d'ensemble

| Acte | Timing | Duree | Action cle |
|------|--------|-------|------------|
| Intro | 0:00 - 0:30 | 30s | "Excel + mails -> Portal + 2 clics" |
| Discovery | 0:30 - 2:00 | 1m30 | Portal -> Search -> Spec -> Try It |
| Approval | 2:00 - 3:00 | 1m | Owner approve en 1 clic |
| API Call | 3:00 - 4:30 | 1m30 | Credentials -> curl -> Dashboard |
| Outro | 4:30 - 5:00 | 30s | "5-10 jours -> 2 minutes" |

### Personas

| Persona | URL | Role | Actes |
|---------|-----|------|-------|
| art3mis | portal.gostoa.dev | devops (consumer) | Discovery, API Call |
| parzival | console.gostoa.dev | tenant-admin (provider) | Approval |

### Setup navigateur

| Onglet | URL | Pre-logged |
|--------|-----|------------|
| 1 | https://portal.gostoa.dev/apis | art3mis |
| 2 | https://console.gostoa.dev | parzival |
| 3 | Terminal avec curl pret | — |

---

## Acte 1 — INTRO (0:00 - 0:30)

**[Ecran : Portal ouvert sur le catalogue]**

> "Aujourd'hui dans la plupart des grandes entreprises, pour consommer une API, il faut un fichier Excel pour trouver la bonne API, 3 mails pour demander l'acces, et 5 a 10 jours d'attente."

*Pause 2 secondes.*

> "Avec STOA, c'est un portail et 2 clics. Je vais vous le montrer en live."

**Checkpoint 0:30** — Si > 0:35, couper la pause et enchainer.

---

## Acte 2 — DISCOVERY (0:30 - 2:00)

**[Onglet 1 : Portal — https://portal.gostoa.dev/apis]**

> "Je suis Art3mis, developpeur dans l'equipe mobile. J'ai besoin d'integrer l'API Petstore."

### 2.1 — Catalogue (0:30 - 0:50)

1. Le catalogue est deja affiche (page `/apis`)
2. Pointer les cartes API visibles

> "Premier changement : toutes les APIs de l'entreprise sont ici, dans un catalogue en self-service. Plus besoin de chercher dans un Excel."

### 2.2 — Recherche + Spec (0:50 - 1:15)

1. Taper `petstore` dans la barre de recherche
2. Cliquer sur la carte **Petstore API**
3. La page detail s'ouvre
4. Cliquer sur l'onglet **Endpoints**
5. Cliquer sur l'onglet **OpenAPI Spec**

> "La spec OpenAPI complete, directement dans le portail. Plus besoin de demander au tech lead ou de fouiller Confluence."

### 2.3 — Souscription (1:15 - 1:45)

1. Cliquer sur **Subscribe**
2. Selectionner **OASIS Mobile App**
3. Selectionner **Standard Plan**
4. Confirmer

> "Un clic. Pas de mail, pas de reunion, pas de ticket ServiceNow."

5. La modale affiche **l'API Key generee**
6. Montrer le message "Copy and save this API key now"

> "Credentials generees instantanement."

7. **Copier la cle** (on en aura besoin a l'Acte 4)

### 2.4 — Try It (1:45 - 2:00)

1. Cliquer sur **Try this API**
2. Selectionner `GET /pets`
3. Cliquer **Send**
4. Resultat : **200 OK**

> "Test en live, directement depuis le portail. C'est notre premier clic."

*Laisser le 200 OK visible a l'ecran.*

**Checkpoint 2:00** — Si > 2:15, sauter le Try It (montrer juste le bouton).

---

## Acte 3 — APPROVAL (2:00 - 3:00)

**[Onglet 2 : Console — https://console.gostoa.dev]**

> "Maintenant, passons de l'autre cote. Je suis Parzival, API owner. C'est moi qui gere les acces."

### 3.1 — Dashboard (2:00 - 2:15)

1. Page Dashboard — montrer les indicateurs

> "Vue d'ensemble en temps reel."

### 3.2 — Approbation en 1 clic (2:15 - 2:50)

1. Cliquer sur **Applications** dans la sidebar
2. Pointer **Gunter Analytics Dashboard** — statut **Pending**

> "Ici, une souscription en attente pour la Payments API. Dans un ESB classique, c'est 3 mails et une reunion. Ici..."

3. Cliquer **Approve**

> "Un clic. C'est notre deuxieme clic."

### 3.3 — Monitoring (2:50 - 3:00)

1. Cliquer sur **API Monitoring**
2. Montrer le dashboard rapidement

> "Chaque appel est trace et mesure. Plus de boite noire."

**Checkpoint 3:00** — Si > 3:15, sauter le monitoring et passer a l'Acte 4.

---

## Acte 4 — API CALL (3:00 - 4:30)

**[Onglet 3 : Terminal]**

> "Maintenant, on va consommer l'API pour de vrai."

### 4.1 — curl avec credentials (3:00 - 3:30)

1. Dans le terminal, afficher la commande curl preparee :

```bash
curl -s -H "X-API-Key: <PASTE_KEY>" \
  https://httpbin.org/anything/pets?status=available \
  | python3 -m json.tool | head -20
```

2. Coller la cle API copiee a l'Acte 2
3. Executer — reponse **200 OK** avec les donnees

> "On a decouvert l'API, souscrit, teste, et maintenant on l'appelle en production. Le tout en moins de 5 minutes."

### 4.2 — Dashboard metriques (3:30 - 4:15)

**[Retour onglet 2 : Console]**

1. Cliquer sur **API Monitoring**
2. Montrer l'appel qui vient d'apparaitre dans les metriques

> "L'appel qu'on vient de faire est deja visible ici. Le provider voit tout en temps reel."

### 4.3 — Recapitulatif visuel (4:15 - 4:30)

> "Recapitulons le parcours :"

Pointer du doigt (ou montrer une slide) :

> "1. Decouvrir l'API dans le catalogue — sans Excel.
> 2. Souscrire en 1 clic — sans mail.
> 3. Tester en live — sans attendre.
> 4. Appeler en production — sans reunion.
> 5. L'owner approuve ou monitore — sans bureaucratie."

**Checkpoint 4:30** — Si > 4:40, passer directement a l'Outro.

---

## Acte 5 — OUTRO (4:30 - 5:00)

**[Slide : "5-10 jours -> 2 minutes"]**

> "Avec un ESB classique, obtenir un acces API prend 5 a 10 jours ouvrables. Avec STOA, ca prend 2 minutes."

> "Un portail, 2 clics, zero mail."

**[Slide : QR code + contact]**

> "Scannez le QR code pour acceder a la documentation. Si vous voulez voir ca sur vos APIs, venez me voir apres."

| | |
|---|---|
| Documentation | https://docs.gostoa.dev |
| Contact | christophe@gostoa.dev |
| Demo Portal | https://portal.gostoa.dev |

> "Merci."

---

## Plan B — Si ca plante

| Probleme | Action |
|----------|--------|
| Portal ne charge pas | Montrer screenshots dans le slide deck |
| Login Keycloak echoue | Session pre-authentifiee (cookies en place) |
| Subscribe echoue (409) | "Deja souscrit — c'est idempotent" -> My Subscriptions |
| Test Sandbox erreur | Montrer le curl dans le terminal |
| Console lente | Sauter le monitoring, aller au curl |
| Reseau down | Basculer sur hotspot mobile, puis video backup |
| Tout down | Lancer `backup-final.mp4` (offline) |

### Commande curl de secours

```bash
# Fonctionne sans la plateforme STOA (httpbin toujours disponible)
curl -s https://httpbin.org/anything/pets?status=available \
  | python3 -m json.tool | head -20
```

---

## Timing checkpoints

| Temps | Checkpoint | Si en retard |
|-------|-----------|-------------|
| 0:30 | Intro finie | Couper la pause |
| 2:00 | Discovery finie | Sauter Try It |
| 3:00 | Approval fini | Sauter monitoring |
| 4:30 | API Call fini | Sauter le recap visuel |
| 5:00 | Fin | — |

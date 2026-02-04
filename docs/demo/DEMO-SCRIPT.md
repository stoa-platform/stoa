# Demo Script — "ESB is Dead" (5 min)

> **CAB-1061** | Presentation: 24 February 2026
> Presenter: Christophe Aboulicam | Platform: STOA

---

## Overview

| Segment | Time | What |
|---------|------|------|
| Hook | 0:00 - 0:30 | Question + pain point |
| Problem | 0:30 - 1:30 | ESB world today |
| Solution LIVE | 1:30 - 3:30 | Portal demo (developer flow) |
| Console | 3:30 - 4:30 | Admin view (provider flow) |
| Close | 4:30 - 5:00 | Punchline + CTA |

---

## 0:00 - 0:30 | HOOK

**[Slide: titre "ESB is Dead"]**

> "Levez la main si vous avez deja attendu **5 jours** pour obtenir un acces API dans votre entreprise."

*Pause 3 secondes. Laisser les mains se lever.*

> "5 jours. Pour un GET sur une API REST. Avec 3 mails, 2 reunions, et un ticket ServiceNow."

> "Aujourd'hui je vais vous montrer comment on fait la meme chose en **5 minutes**."

---

## 0:30 - 1:30 | PROBLEM

**[Slide: "The ESB World" — ou Portal ouvert sur un catalogue vide]**

> "Voici ce que la plupart des equipes vivent aujourd'hui."

Pointer les 3 douleurs :

1. **Catalogue = fichier Excel**
   > "Les APIs existent, mais personne ne sait ou elles sont. Un fichier Excel partage par mail, jamais a jour."

2. **Acces = processus bureaucratique**
   > "Pour consommer une API, il faut un mail a l'equipe API, une reunion de cadrage, un ticket, une validation manager. Minimum 5 jours ouvrables."

3. **Gateway = boite noire**
   > "webMethods, TIBCO, DataPower — des boites noires a 500K euros/an de licence. Personne ne sait ce qui transite. Pas de self-service, pas de visibilite."

> "On a construit STOA pour eliminer ces 3 problemes. Je vais vous montrer — en live."

---

## 1:30 - 3:30 | SOLUTION LIVE — Developer Portal

**[Switch: navigateur — https://portal.gostoa.dev]**

> "Je suis Art3mis, developpeur dans l'equipe mobile. J'ai besoin d'integrer une API."

### Etape 1 — Catalogue (1:30 - 1:50)

1. Cliquer sur **API Catalog** dans la sidebar
2. La page `/apis` affiche les APIs disponibles

> "Premier changement : un **catalogue en self-service**. Toutes les APIs de l'entreprise, cherchables, filtrees, avec leur documentation."

### Etape 2 — Recherche + Specification (1:50 - 2:15)

1. Taper `petstore` dans la barre de recherche
2. Cliquer sur la carte **Petstore API**
3. La page detail s'ouvre (`/apis/{id}`)
4. Cliquer sur l'onglet **Endpoints** — les operations apparaissent
5. Cliquer sur l'onglet **OpenAPI Spec** — le spec complet est visible

> "La spec OpenAPI complete, directement dans le portail. Plus besoin de chercher dans Confluence ou de demander au tech lead."

### Etape 3 — Souscription en 1 clic (2:15 - 2:45)

1. Cliquer sur le bouton **Subscribe**
2. La modale `SubscribeModal` s'ouvre
3. Selectionner l'application (ex: "OASIS Mobile App")
4. Selectionner le plan (ex: "Standard Plan")
5. Confirmer

> "Un clic. Pas de mail, pas de reunion, pas de ticket."

6. La modale de succes affiche **l'API Key generee**
7. **IMPORTANT** : Montrer le message "Copy and save this API key now"

> "Credentials generees **instantanement**. Pas dans 5 jours. Maintenant."

### Etape 4 — Test live (2:45 - 3:30)

1. Copier la cle API
2. Cliquer sur **Try this API** (ou naviguer vers `/apis/{id}/test`)
3. Dans le Testing Sandbox :
   - Selectionner `GET /pets`
   - Cliquer **Send**
   - Le resultat affiche **200 OK** avec la liste de pets

> "Test en live, directement depuis le portail. On vient de passer de 5 jours a... 2 minutes."

*Laisser le `200 OK` visible a l'ecran pendant la transition.*

---

## 3:30 - 4:30 | CONSOLE — Admin View

**[Switch: nouvel onglet — https://console.gostoa.dev]**

> "Maintenant, passons de l'autre cote. Je suis Parzival, tenant-admin. C'est moi qui gere les APIs et les acces."

### Etape 5 — Dashboard (3:30 - 3:50)

1. Page `/` — Dashboard
2. Montrer les cartes de statut rapide

> "Vue d'ensemble en temps reel. APIs, applications, deployments — tout est visible."

### Etape 6 — Approbation (3:50 - 4:10)

1. Cliquer sur **Applications** dans la sidebar
2. Montrer la liste des applications
3. Pointer **Gunter Analytics Dashboard** — statut **Pending** (jaune)

> "Ici une souscription en attente d'approbation pour la Payments API. Un clic pour approuver ou rejeter."

4. *(Optionnel)* Approuver la demande en live

> "Les equipes API gardent le controle — mais sans bureaucratie."

### Etape 7 — Monitoring (4:10 - 4:30)

1. Cliquer sur **API Monitoring** dans la sidebar
2. Montrer le dashboard monitoring

> "Monitoring en temps reel. Chaque appel API est trace, mesure, visible. Plus de boite noire."

---

## 4:30 - 5:00 | CLOSE

**[Slide: "5 jours -> 5 minutes"]**

> "Recapitulons."

> "Avec un ESB classique :
> - 5 jours pour un acces API
> - Un fichier Excel comme catalogue
> - Zero visibilite sur le trafic"

> "Avec STOA :
> - **5 minutes** pour decouvrir, souscrire et tester une API
> - Un catalogue self-service avec spec OpenAPI
> - Un monitoring temps reel"

**[Slide: QR code + contact]**

> "Scannez le QR code pour acceder a la documentation. Et si vous voulez voir comment ca marche sur **vos** APIs, venez me voir apres."

| | |
|---|---|
| Documentation | https://docs.gostoa.dev |
| Contact | christophe@gostoa.dev |
| Demo Portal | https://portal.gostoa.dev |

> "Merci."

---

## Notes pour le presentateur

### Persona & credentials

| Persona | URL | Role | Usage dans la demo |
|---------|-----|------|--------------------|
| art3mis | portal.gostoa.dev | devops | Portal: search, subscribe, test |
| parzival | console.gostoa.dev | tenant-admin | Console: approve, monitor |

### Raccourcis navigateur

- **Onglet 1** : Portal (pre-logged as art3mis)
- **Onglet 2** : Console (pre-logged as parzival)
- **Onglet 3** : Slide deck (backup)

### Si ca plante

| Probleme | Action |
|----------|--------|
| Portal ne charge pas | Montrer screenshots dans le slide deck |
| Login Keycloak echoue | Utiliser session pre-authentifiee (cookies en place) |
| Subscribe echoue (409) | "L'API est deja souscrite — c'est idempotent" |
| Test Sandbox erreur | Montrer le curl equivalent dans le terminal |
| Reseau down | Basculer sur la video backup |

### Timing checkpoints

| Temps | Checkpoint | Si en retard |
|-------|-----------|-------------|
| 0:30 | Hook fini | Couper la pause |
| 1:30 | Problem fini | Sauter la slide webMethods |
| 2:30 | Subscribe fait | Sauter le test sandbox |
| 3:30 | Portal fini | Raccourcir console a 30s |
| 4:30 | Console fini | Aller droit au close |

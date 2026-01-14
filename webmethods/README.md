# 📁 GitOps webMethods — Structure de Réconciliation

> **Source de vérité Git pour webMethods Gateway**
> 
> Ce répertoire contient les définitions déclaratives des APIs, policies et aliases
> qui seront réconciliés automatiquement vers webMethods Gateway via AWX.

---

## 🏗️ Structure

```
gitops/webmethods/
├── README.md                    # Ce fichier
├── schema/
│   └── api-schema.json          # JSON Schema pour validation CI
├── apis/
│   ├── crm-api.yaml             # Définition API CRM
│   ├── billing-api.yaml         # Définition API Billing
│   └── ...
├── policies/
│   ├── rate-limit-standard.yaml # Policy rate limiting standard
│   ├── rate-limit-premium.yaml  # Policy rate limiting premium
│   └── jwt-validation.yaml      # Policy validation JWT
└── aliases/
    ├── dev.yaml                 # Endpoints backend DEV
    ├── int.yaml                 # Endpoints backend INT
    └── prod.yaml                # Endpoints backend PROD
```

---

## 📋 Format API (apis/*.yaml)

Chaque fichier YAML dans `apis/` définit une API complète :

```yaml
apiVersion: stoa.io/v1
kind: WebMethodsAPI
metadata:
  name: crm-api
  version: "1.0.0"
  description: "API CRM pour gestion des contacts"
  tags:
    - crm
    - contacts
spec:
  type: REST
  basePath: /api/crm/v1
  
  # Backend routing (résolu via aliases/)
  backend:
    alias: crm-backend    # Référence vers aliases/{env}.yaml
    
  # Policies appliquées (ordre d'exécution)
  policies:
    - rate-limit-standard
    - jwt-validation
    
  # Configuration authentification
  auth:
    type: oauth2
    scopes:
      - crm:read
      - crm:write
      
  # Applications autorisées (optionnel, vide = toutes)
  applications: []
  
  # Ressources/Endpoints exposés
  resources:
    - path: /contacts
      methods: [GET, POST]
    - path: /contacts/{id}
      methods: [GET, PUT, DELETE]
```

---

## 🔒 Format Policy (policies/*.yaml)

```yaml
apiVersion: stoa.io/v1
kind: WebMethodsPolicy
metadata:
  name: rate-limit-standard
  description: "Rate limiting standard - 100 req/min"
spec:
  type: rate-limit
  config:
    limit: 100
    interval: 60s
    key: client_id
    action: reject    # reject | queue
```

---

## 🔗 Format Alias (aliases/{env}.yaml)

Les aliases définissent les endpoints backend par environnement :

```yaml
apiVersion: stoa.io/v1
kind: WebMethodsAliases
metadata:
  environment: dev
aliases:
  crm-backend:
    url: http://crm-service.dev.svc:8080
    timeout: 30s
    retries: 3
    
  billing-backend:
    url: http://billing-service.dev.svc:8080
    timeout: 60s
    retries: 2
```

---

## 🔄 Processus de Réconciliation

```
┌─────────────┐     ┌─────────────┐     ┌─────────────────┐
│   Git Push  │────→│   ArgoCD    │────→│  AWX Job        │
│  (PR merge) │     │  PostSync   │     │  reconcile.yml  │
└─────────────┘     └─────────────┘     └────────┬────────┘
                                                  │
                                                  ▼
                                        ┌─────────────────┐
                                        │   webMethods    │
                                        │    Gateway      │
                                        └─────────────────┘
```

### Étapes AWX :
1. **Fetch** : Clone/pull du repo Git
2. **Parse** : Lecture des YAML (apis/, policies/, aliases/)
3. **Diff** : Comparaison avec état actuel Gateway (API REST)
4. **Apply** : Create/Update/Delete pour aligner
5. **Report** : Log du résultat dans AWX + notification

---

## ✅ Validation CI

Avant merge, le pipeline GitLab valide :

```yaml
validate-webmethods:
  stage: validate
  script:
    - pip install jsonschema pyyaml
    - python scripts/validate-webmethods.py
  rules:
    - changes:
        - gitops/webmethods/**/*
```

Le script valide :
- Syntaxe YAML correcte
- Conformité au JSON Schema
- Références d'aliases existantes
- Références de policies existantes

---

## 🚀 Utilisation

### Ajouter une nouvelle API

1. Créer `apis/my-new-api.yaml` selon le format
2. Ajouter les policies nécessaires dans `policies/`
3. Ajouter les aliases backend dans `aliases/{env}.yaml`
4. Commit + PR
5. Après merge → réconciliation automatique

### Modifier une API existante

1. Éditer le fichier YAML correspondant
2. Commit + PR
3. Après merge → réconciliation automatique

### Supprimer une API

1. Supprimer le fichier YAML
2. Commit + PR
3. Après merge → API supprimée de la Gateway

---

## 📚 Références

- [CAB-367 - GitOps Réconciliation](https://linear.app/hlfh-workspace/issue/CAB-367)
- [CAB-393 - Adapter STOA → webMethods](https://linear.app/hlfh-workspace/issue/CAB-393)
- [Guide CI/CD Migration](https://www.notion.so/2e5faea66cb881e48925e95a365db6af)

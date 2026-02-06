# STOA Demo - Notes Techniques et Limitations

> Document interne pour la préparation de la démo enterprise (30-45 min)

## Status de Validation (2026-02-06)

| Composant | Status | Notes |
|-----------|--------|-------|
| UAC Files (3) | ✅ Valid YAML | high-five, ioi, oasis |
| K8s CRDs (33 tools) | ✅ Valid YAML | 9+9+15 tools |
| Traffic Generator | ✅ Testé | Python async avec httpx |
| Grafana Dashboard | ✅ Créé | demo-overview.json |
| E2E Tests | ✅ 6 scénarios | demo-showcase.feature |

---

## APIs Publiques - Rate Limits

| API | Rate Limit | Delay Recommandé | Status |
|-----|------------|------------------|--------|
| **CoinGecko** | 10-30 req/min (free) | 2.5s entre requêtes | ✅ OK |
| **Open-Meteo** | Illimité | 1s | ✅ OK |
| **JSONPlaceholder** | Illimité | 0.5s | ✅ OK |
| **DummyJSON** | ~100 req/min | 0.5s | ✅ OK |
| **httpbin.org** | Illimité | 0.5s | ✅ OK |
| ~~reqres.in~~ | ❌ 403 Cloudflare | N/A | ❌ REMPLACÉ |

### CoinGecko - Points d'Attention

**Problème potentiel**: Le free tier de CoinGecko est très limité (10-30 req/min).

**Workarounds**:
1. **Semantic Cache**: Les requêtes identiques/similaires sont cachées (TTL 60s)
2. **Delay intégré**: Le traffic generator utilise 2.5s entre chaque requête CoinGecko
3. **Fallback**: Si rate limited, montrer le cache HIT sur requête répétée

**Script de test avant démo**:
```bash
# Vérifier que CoinGecko répond
curl -s "https://api.coingecko.com/api/v3/simple/price?ids=bitcoin&vs_currencies=usd"

# Si 429 Too Many Requests, attendre 1 minute
```

### reqres.in → DummyJSON

**Problème**: reqres.in retourne 403 (Cloudflare protection)

**Solution**: Remplacé par DummyJSON qui offre:
- Plus de champs PII (email, phone, password, birthDate)
- Meilleur pour la démo de PII masking
- API similaire (`/users`, `/users/{id}`)

---

## Scénarios de Démo - Risques et Mitigations

### Scénario 1: Legacy-to-MCP Bridge
**Risque**: Shadow mode nécessite un backend MCP Gateway fonctionnel
**Mitigation**: Avoir un recording vidéo de backup

### Scénario 2: Fintech Agent
**Risque**: CoinGecko rate limit pendant la démo
**Mitigation**:
1. Pré-chauffer le cache avant la démo
2. Montrer le cache HIT sur 2e requête (pas besoin d'appel API)

### Scénario 3: Multi-Tenant Isolation
**Risque**: Rate limit IOI trop bas pourrait sembler "bug"
**Mitigation**: Expliquer clairement que c'est voulu (IOI = enterprise legacy = limites strictes)

### Scénario 4: DevOps Workflow
**Risque**: GitHub API nécessite un token pour >60 req/h
**Mitigation**: Utiliser httpbin.org mock pour les actions write (create_issue, create_pr)

### Scénario 5: AI Pipeline Bridge
**Risque**: HuggingFace nécessite une API key pour l'inference réelle
**Mitigation**: Mock via httpbin.org, montrer le schema de réponse

### Scénario 6: Compliance & Audit
**Risque**: Pas de vraies données sensibles
**Mitigation**: DummyJSON fournit des emails/phones réalistes pour la démo PII masking

---

## Checklist Pré-Démo

### 1 heure avant

- [ ] Vérifier CoinGecko: `curl -s https://api.coingecko.com/api/v3/ping`
- [ ] Vérifier DummyJSON: `curl -s https://dummyjson.com/users/1`
- [ ] Lancer le traffic generator pour "chauffer" les dashboards
- [ ] Vérifier Grafana dashboards

### 15 minutes avant

- [ ] Stopper le traffic generator
- [ ] Reset des metrics si nécessaire
- [ ] Ouvrir les onglets: Portal, Console, Grafana
- [ ] Préparer le terminal pour les commandes MCP

### Pendant la démo

- [ ] Commencer par le scénario le plus stable (Scénario 2 ou 3)
- [ ] Si CoinGecko rate limited, montrer le cache HIT
- [ ] Si API échoue, passer au mock httpbin.org

---

## Contacts & Fallbacks

- **Recording vidéo backup**: À créer avant la démo
- **Hotline technique**: [TBD]
- **Reset rapide**: `kubectl delete -k deploy/demo-rpo/ && kubectl apply -k deploy/demo-rpo/`

---

## Historique des Changements

| Date | Changement |
|------|------------|
| 2026-02-06 | Création initiale WS1 |
| 2026-02-06 | Remplacement reqres.in → DummyJSON |
| 2026-02-06 | Validation APIs publiques |

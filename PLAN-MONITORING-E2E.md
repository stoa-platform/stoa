# Plan: Monitoring E2E - Alimenter les données

## Problème actuel

La page **Monitoring** de la Console UI affiche "No pipeline traces yet" car:

1. **Store en mémoire** - Les traces sont stockées dans `TraceStore` (mémoire Python)
2. **Perdues au redémarrage** - Chaque restart du pod `control-plane-api` efface toutes les traces
3. **Source unique** - Seul le webhook GitLab crée des traces (push, MR, tag)
4. **Pas de GitLab configuré** - Aucun webhook GitLab n'envoie vers `/webhooks/gitlab`

## Architecture actuelle

```
GitLab Push/MR → POST /webhooks/gitlab → PipelineTrace → trace_store (mémoire)
                                              │
                                              ├─ Step: webhook_received
                                              ├─ Step: token_verification
                                              ├─ Step: event_processing
                                              ├─ Step: analyze_changes
                                              ├─ Step: kafka_publish
                                              └─ Step: awx_trigger (pending)

Console UI → GET /v1/traces → trace_store.list_recent() → Affichage
```

## Solutions proposées

### Option A: Endpoint de test/démo (Rapide - 30 min)

Ajouter un endpoint pour créer des traces de démonstration.

```python
# POST /v1/traces/demo
# Crée une trace simulée avec tous les steps
```

**Avantages**: Rapide, permet de voir la UI fonctionner
**Inconvénients**: Pas de vraies données

---

### Option B: Configurer un webhook GitLab (Moyen - 1h)

1. Créer un projet test sur GitLab
2. Configurer le webhook vers `https://api.stoa.cab-i.com/webhooks/gitlab`
3. Faire des push pour générer des traces

**Avantages**: Vrais événements, test E2E réel
**Inconvénients**: Nécessite GitLab, traces perdues au restart

---

### Option C: Persister les traces en PostgreSQL (Recommandé - 2-3h)

Migrer `TraceStore` de mémoire vers PostgreSQL.

#### Fichiers à créer/modifier:

| Fichier | Action |
|---------|--------|
| `alembic/versions/007_create_pipeline_traces.py` | Migration Alembic |
| `src/models/traces_db.py` | Modèle SQLAlchemy |
| `src/services/trace_service.py` | Service async pour DB |
| `src/routers/traces.py` | Adapter pour utiliser le service |
| `src/routers/webhooks.py` | Adapter pour utiliser le service |

#### Schema PostgreSQL:

```sql
CREATE TABLE pipeline_traces (
    id UUID PRIMARY KEY,
    trigger_type VARCHAR(50) NOT NULL,
    trigger_source VARCHAR(50) NOT NULL,

    -- Git info
    git_commit_sha VARCHAR(40),
    git_commit_message TEXT,
    git_branch VARCHAR(255),
    git_author VARCHAR(255),
    git_author_email VARCHAR(255),
    git_project VARCHAR(255),
    git_files_changed JSONB,

    -- Target info
    tenant_id VARCHAR(100),
    api_id VARCHAR(100),
    api_name VARCHAR(255),
    environment VARCHAR(50),

    -- Timing
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    completed_at TIMESTAMP WITH TIME ZONE,
    total_duration_ms INTEGER,

    -- Status
    status VARCHAR(20) NOT NULL DEFAULT 'pending',
    error_summary TEXT,

    -- Steps (JSONB array)
    steps JSONB DEFAULT '[]'
);

CREATE INDEX idx_traces_tenant ON pipeline_traces(tenant_id);
CREATE INDEX idx_traces_status ON pipeline_traces(status);
CREATE INDEX idx_traces_created ON pipeline_traces(created_at DESC);
```

**Avantages**: Données persistantes, requêtes SQL, historique complet
**Inconvénients**: Plus de travail, migration nécessaire

---

### Option D: Traces depuis MCP Gateway errors (Bonus)

Connecter les Error Snapshots du MCP Gateway au monitoring.

Chaque erreur 5xx capturée crée une trace dans le monitoring.

---

## Recommandation

**Phase 1**: Option A (endpoint démo) pour voir la UI fonctionner immédiatement
**Phase 2**: Option C (PostgreSQL) pour la persistance long terme

## Implémentation Phase 1 - Endpoint Démo

```python
# control-plane-api/src/routers/traces.py

@router.post("/demo")
async def create_demo_trace():
    """Create a demo trace for testing the monitoring UI."""
    import random
    from datetime import datetime, timedelta

    # Random statuses for variety
    statuses = [TraceStatus.SUCCESS, TraceStatus.SUCCESS, TraceStatus.SUCCESS, TraceStatus.FAILED]
    final_status = random.choice(statuses)

    trace = PipelineTrace(
        trigger_type="gitlab-push",
        trigger_source="gitlab",
        git_commit_sha=f"{random.randint(1000000, 9999999):07x}abc",
        git_commit_message=random.choice([
            "feat: add new API endpoint",
            "fix: resolve authentication issue",
            "chore: update dependencies",
            "refactor: improve performance",
            "docs: update README",
        ]),
        git_branch="main",
        git_author=random.choice(["alice", "bob", "charlie", "diana"]),
        git_author_email="dev@stoa.cab-i.com",
        git_project="stoa/api-definitions",
        git_files_changed=["tenants/acme/apis/customer-api/openapi.yaml"],
        tenant_id="tenant-acme",
        api_name=random.choice(["customer-api", "order-api", "inventory-api", "payment-api"]),
        environment="dev",
    )
    trace.start()

    # Add realistic steps with timing
    steps_config = [
        ("webhook_received", 15, 50),
        ("token_verification", 5, 20),
        ("event_processing", 20, 100),
        ("analyze_changes", 50, 200),
        ("kafka_publish", 30, 150),
        ("awx_trigger", 100, 500),
    ]

    for step_name, min_ms, max_ms in steps_config:
        step = trace.add_step(step_name)
        step.start()
        step.duration_ms = random.randint(min_ms, max_ms)

        # Fail the last step if trace should fail
        if final_status == TraceStatus.FAILED and step_name == "awx_trigger":
            step.fail("AWX job failed: Ansible playbook error", {
                "job_id": random.randint(1000, 9999),
                "error_code": "ANSIBLE_ERROR",
            })
        else:
            step.complete({
                "processed": True,
                "duration_ms": step.duration_ms,
            })

    # Complete trace
    if final_status == TraceStatus.FAILED:
        trace.fail("Pipeline failed at awx_trigger step")
    else:
        trace.complete()

    trace_store.save(trace)

    return {
        "created": True,
        "trace_id": trace.id,
        "status": trace.status.value,
        "duration_ms": trace.total_duration_ms,
    }


@router.post("/demo/batch")
async def create_demo_traces_batch(count: int = Query(10, ge=1, le=50)):
    """Create multiple demo traces for a realistic monitoring view."""
    traces = []
    for _ in range(count):
        result = await create_demo_trace()
        traces.append(result)

    return {
        "created": count,
        "traces": traces,
    }
```

## Test après implémentation

```bash
# Créer 10 traces de démo
curl -X POST https://api.stoa.cab-i.com/v1/traces/demo/batch?count=10

# Vérifier les traces
curl https://api.stoa.cab-i.com/v1/traces

# Vérifier les stats
curl https://api.stoa.cab-i.com/v1/traces/stats
```

Puis rafraîchir la page Monitoring sur la Console UI.

---

## Prochaine étape

Dis-moi si tu veux que j'implémente:
- **Option A** (endpoint démo) - rapide pour voir la UI
- **Option C** (PostgreSQL) - persistance long terme
- **Les deux** - démo immédiate + persistance ensuite

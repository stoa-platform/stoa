CAB-1105 Phase 9: Gateway Mode Dashboard — UI pour les 4 modes gateway.

Branch: `feat/cab-1105-mode-dashboard` (creer depuis main, APRES merge de feat/cab-1105-kill-python)

## Contexte
Le control-plane-api et le control-plane-ui doivent supporter les 4 modes gateway (EdgeMcp, Sidecar, Proxy, Shadow).
Le GatewayType enum dans l'API doit etre etendu. La Console UI doit afficher des badges de mode et une page dashboard.

Stack: React 18, TypeScript, vitest, Keycloak-js. Lire CLAUDE.md pour les conventions.

## Taches

### 1. Explorer l'existant
- Lire `control-plane-api/src/models/gateway.py` — modele GatewayInstance, GatewayType enum
- Lire `control-plane-api/src/schemas/gateway.py` — schemas Pydantic
- Lire `control-plane-api/src/routers/gateways.py` — endpoints CRUD
- Lire `control-plane-ui/src/pages/Gateways/GatewayList.tsx` — liste actuelle
- Lire `control-plane-ui/src/pages/Gateways/GatewayModesDashboard.tsx` si existe
- Lire `control-plane-ui/src/types/index.ts` — types TypeScript

### 2. API: Etendre GatewayType enum
Fichier: `control-plane-api/src/models/gateway.py`

Ajouter au GatewayType enum:
```python
class GatewayType(str, Enum):
    STOA_NATIVE = "STOA_NATIVE"
    STOA_SIDECAR = "STOA_SIDECAR"
    STOA_PROXY = "STOA_PROXY"       # NEW
    STOA_SHADOW = "STOA_SHADOW"     # NEW
    KONG = "KONG"
    ENVOY = "ENVOY"
    NGINX = "NGINX"
    CUSTOM = "CUSTOM"
```

### 3. API: Ajouter champ `mode` au schema
Fichier: `control-plane-api/src/schemas/gateway.py`

```python
mode: Optional[str] = Field(None, description="Gateway operational mode: edge_mcp, sidecar, proxy, shadow")
```

### 4. UI: Types TypeScript
Fichier: `control-plane-ui/src/types/index.ts`

Mettre a jour le type GatewayType:
```typescript
export type GatewayType =
  | 'STOA_NATIVE'
  | 'STOA_SIDECAR'
  | 'STOA_PROXY'
  | 'STOA_SHADOW'
  | 'KONG' | 'ENVOY' | 'NGINX' | 'CUSTOM';

export type GatewayMode = 'edge_mcp' | 'sidecar' | 'proxy' | 'shadow';
```

### 5. UI: Mode badges dans GatewayList
Fichier: `control-plane-ui/src/pages/Gateways/GatewayList.tsx`

Badge couleurs:
- EdgeMcp = blue (`bg-blue-100 text-blue-800`)
- Sidecar = green (`bg-green-100 text-green-800`)
- Proxy = yellow (`bg-yellow-100 text-yellow-800`)
- Shadow = purple (`bg-purple-100 text-purple-800`)

Ajouter une colonne "Mode" dans la table + un filtre par mode.

### 6. UI: ModesDashboard page
Creer: `control-plane-ui/src/pages/Gateways/GatewayModesDashboard.tsx`

Contenu:
- Pie chart: distribution des modes (combien de gateways par mode)
- Stats cards: total par mode, online/offline par mode
- Liste filtrable par mode
- Lien depuis le sidebar ou la page GatewayList

Si GatewayModesDashboard.tsx existe deja, l'enrichir avec les nouveaux modes.

### 7. UI: Route + Sidebar
- Ajouter la route `/gateways/modes` dans `App.tsx` (lazy-loaded)
- Ajouter l'entree dans le sidebar si pas deja present
- Raccourci clavier optionnel

### 8. Tests
- Unit test pour le composant ModeBadge
- Unit test pour GatewayModesDashboard (mock data avec les 4 modes)
- Mettre a jour les tests existants de GatewayList si les colonnes changent
- Framework: vitest + React Testing Library (JAMAIS Jest)

### 9. Verifier
- `npm run lint` dans control-plane-ui/
- `npm run format:check` dans control-plane-ui/
- `npm run test` dans control-plane-ui/ — tous les tests passent
- `npm run test:coverage` — pas de regression de coverage

## DoD
- [ ] GatewayType enum etendu avec STOA_PROXY et STOA_SHADOW
- [ ] Mode badges (blue/green/yellow/purple) dans GatewayList
- [ ] Filtre par mode dans GatewayList
- [ ] Page GatewayModesDashboard avec pie chart + stats
- [ ] Route `/gateways/modes` fonctionnelle
- [ ] Tests unitaires pour les nouveaux composants
- [ ] `npm run lint && npm run test` vert
- [ ] Commit: `feat(ui): gateway mode dashboard with 4-mode badges (CAB-1105)`

## Contraintes
- Suivre les patterns UI existants (Tailwind, composants existants)
- vitest (JAMAIS Jest), React Testing Library
- Prettier: single quotes, semicolons, 100 chars
- Ne PAS modifier le code Rust (stoa-gateway/)
- Ne PAS push

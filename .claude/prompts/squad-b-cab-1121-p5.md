CAB-1121 Phase 5 — Portal Consumer UI (portal/ React TypeScript).

Branch: `feat/cab-1121-portal-consumer-ui`

## Contexte

- Phase 1 (data model + 14 REST endpoints) = DONE (PR #204)
- Phase 2 (Keycloak OAuth2 integration) = DONE (PR #208)
- Phase 3 (Gateway Propagation) = EN COURS
- Les endpoints API existent dans control-plane-api:
  - `GET/POST /v1/tenants/{slug}/consumers` (list + create)
  - `GET/PATCH/DELETE /v1/tenants/{slug}/consumers/{id}` (detail + update + delete)
  - `GET/POST /v1/tenants/{slug}/plans` (list + create)
  - `GET/PATCH/DELETE /v1/tenants/{slug}/plans/{id}` (detail + update + delete)
- AUCUN code consumer n'existe dans portal/ actuellement

## Conventions portal (SUIVRE EXACTEMENT)

### API Service pattern (`src/services/`)
```typescript
// services/applications.ts = reference
import { apiClient } from './api';

export const consumersService = {
  listConsumers: async (tenantSlug: string, params?: ListParams): Promise<PaginatedResponse<Consumer>> => {
    const response = await apiClient.get<PaginatedResponse<Consumer>>(
      `/v1/tenants/${tenantSlug}/consumers`, { params }
    );
    return response.data;
  },
  // ... CRUD
};
export default consumersService;
```
- `apiClient` importe depuis `services/api.ts` (Axios, auth interceptor)
- Export named const + default export
- Return `response.data` (unwrap Axios)
- Generics explicites sur les appels

### React Query Hooks (`src/hooks/`)
```typescript
// hooks/useApplications.ts = reference
export function useConsumers(tenantSlug: string, params?: ListParams) {
  return useQuery({
    queryKey: ['consumers', tenantSlug, params],
    queryFn: () => consumersService.listConsumers(tenantSlug, params),
    staleTime: 30_000,
  });
}
export function useCreateConsumer() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: ConsumerCreateRequest) => consumersService.createConsumer(data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['consumers'] }),
  });
}
```
- Named exports
- Query keys: `['resource', ...params]`
- Mutations invalidate queries on success

### Page pattern
- Stats cards en haut
- Search + filtres
- Grid de cards
- Loading/error/empty states
- Modals pour create/edit

### Routing (`App.tsx`)
```typescript
const ConsumersPage = lazy(() => import('./pages/consumers').then(m => ({ default: m.ConsumersPage })));
// ...
<Route path="/consumers" element={
  <ProtectedRoute scope="stoa:tenant:admin">
    <Suspense fallback={<PageLoader />}><ConsumersPage /></Suspense>
  </ProtectedRoute>
} />
<Route path="/consumers/:id" element={
  <ProtectedRoute scope="stoa:tenant:admin">
    <Suspense fallback={<PageLoader />}><ConsumerDetailPage /></Suspense>
  </ProtectedRoute>
} />
```

### WorkspacePage tabs (`src/pages/workspace/WorkspacePage.tsx`)
- Tabs via `useSearchParams()` (`?tab=consumers`)
- Ajouter un tab "Consumers" avec icone UserGroupIcon ou UsersIcon

### Modal pattern
```typescript
interface CreateConsumerModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSubmit: (data: ConsumerCreateRequest) => Promise<void>;
  isLoading?: boolean;
  error?: string | null;
}
```
- Conditional render `if (!isOpen) return null`
- Overlay bg-black/50 + centered card

## Taches

### 1. Types (`src/types/index.ts` — ajouter)
```typescript
export interface Consumer {
  id: string;
  name: string;
  external_id: string;
  contact_email?: string;
  description?: string;
  status: 'active' | 'suspended' | 'blocked';
  tenant_id: string;
  oauth_client_id?: string;
  created_at: string;
  updated_at: string;
}

export interface Plan {
  id: string;
  name: string;
  slug: string;
  description?: string;
  rate_limit_per_second?: number;
  rate_limit_per_minute?: number;
  request_limit_daily?: number;
  request_limit_monthly?: number;
  requires_approval: boolean;
  is_active: boolean;
  tenant_id: string;
  created_at: string;
  updated_at: string;
}

export interface ConsumerCreateRequest {
  name: string;
  external_id: string;
  contact_email?: string;
  description?: string;
}
```

### 2. API Services
- `src/services/consumers.ts` — CRUD consumers (suivre pattern applications.ts)
- `src/services/plans.ts` — list + detail plans

### 3. React Query Hooks
- `src/hooks/useConsumers.ts` — useConsumers, useConsumer, useCreateConsumer, useUpdateConsumer
- `src/hooks/usePlans.ts` — usePlans, usePlan

### 4. Pages
- `src/pages/consumers/index.ts` — barrel export
- `src/pages/consumers/ConsumersPage.tsx` — liste avec stats cards (total, active, suspended), search, grid de ConsumerCards
- `src/pages/consumers/ConsumerDetailPage.tsx` — detail consumer + ses subscriptions + actions (suspend, activate)
- `src/pages/consumers/ConsumerRegistrationPage.tsx` — formulaire creation avec PlanSelector

### 5. Composants
- `src/components/consumers/ConsumerCard.tsx` — card dans la grille (name, external_id, status badge, email, created_at)
- `src/components/consumers/CreateConsumerModal.tsx` — modal creation (name, external_id, email, description)
- `src/components/consumers/PlanSelector.tsx` — grille de plans disponibles, selection, affichage quotas
- `src/components/consumers/CredentialsDisplay.tsx` — affichage one-time client_id/client_secret apres creation (copy to clipboard)

### 6. Integration navigation
- Ajouter tab "Consumers" dans WorkspacePage.tsx
- Ajouter route `/consumers` et `/consumers/:id` dans App.tsx
- Ajouter lien sidebar si la sidebar a une section Workspace

### 7. Tests vitest
- Test render ConsumersPage (mock useConsumers)
- Test ConsumerCard (props rendering)
- Test CreateConsumerModal (form validation: name required, email format)
- Test PlanSelector (selection callback)
- Test CredentialsDisplay (copy button, one-time warning)

## Regles

- Lis portal/src/services/applications.ts, hooks/useApplications.ts, pages/apps/ AVANT de coder
- Lis portal/src/pages/workspace/WorkspacePage.tsx pour comprendre le pattern tabs
- Lis portal/src/App.tsx pour comprendre le routing
- `npm run lint` — max 20 warnings ESLint
- `npm run format:check` — prettier clean
- `npx tsc -p tsconfig.app.json --noEmit` — zero erreur TS
- `npm run test -- --run` — tous tests passent
- Tailwind CSS pour le styling (pas de CSS modules)
- Single quotes, semicolons, trailing commas es5 (prettier config)
- Commit: `feat(portal): consumer registration + subscription workflow UI (CAB-1121 P5)`

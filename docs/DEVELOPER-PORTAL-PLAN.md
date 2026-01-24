# Developer Portal Custom - Development Plan

> **Status**: ✅ **COMPLETED** (CAB-246)
> **Completion Date**: January 2025
> **Production URL**: https://portal.gostoa.dev

## 📋 Overview

**Objective**: Replace the IBM Developer Portal with a custom React portal integrated into the APIM GitOps architecture.

**Estimated Duration**: 3 weeks → **Actual: Completed in 6 sprints**

**Tech Stack**:
- Frontend: React 18 + TypeScript + Vite + TailwindCSS
- Auth: Keycloak OIDC (client: `stoa-portal`)
- Backend: Control Plane API (FastAPI) via Gateway
- Documentation: OpenAPI Viewer component

---

## 📁 Project Structure (Implemented)

```
portal/                          # Actual implementation location
├── src/
│   ├── pages/
│   │   ├── Home.tsx             # ✅ Implemented
│   │   ├── apis/
│   │   │   ├── APICatalog.tsx   # ✅ Implemented
│   │   │   ├── APIDetail.tsx    # ✅ Implemented
│   │   │   └── APITestingSandbox.tsx  # ✅ Implemented
│   │   ├── apps/
│   │   │   ├── MyApplications.tsx     # ✅ Implemented
│   │   │   └── ApplicationDetail.tsx  # ✅ Implemented
│   │   ├── subscriptions/
│   │   │   └── MySubscriptions.tsx    # ✅ Implemented
│   │   ├── tools/               # MCP Tools (bonus feature)
│   │   │   ├── ToolsCatalog.tsx
│   │   │   └── ToolDetail.tsx
│   │   └── Profile.tsx          # ✅ Implemented
│   │
│   ├── components/
│   │   ├── layout/
│   │   │   ├── Header.tsx       # ✅ Implemented
│   │   │   ├── Sidebar.tsx      # ✅ Implemented
│   │   │   └── Layout.tsx       # ✅ Implemented
│   │   ├── apis/
│   │   │   ├── APICard.tsx      # ✅ Implemented
│   │   │   ├── APIFilters.tsx   # ✅ Implemented
│   │   │   ├── EndpointList.tsx # ✅ Implemented
│   │   │   └── OpenAPIViewer.tsx # ✅ Implemented
│   │   ├── apps/
│   │   │   ├── ApplicationCard.tsx   # ✅ Implemented
│   │   │   ├── CreateAppModal.tsx    # ✅ Implemented
│   │   │   └── CredentialsViewer.tsx # ✅ Implemented
│   │   ├── testing/
│   │   │   ├── EnvironmentSelector.tsx  # ✅ Implemented
│   │   │   ├── RequestBuilder.tsx       # ✅ Implemented
│   │   │   ├── ResponseViewer.tsx       # ✅ Implemented
│   │   │   └── SandboxConfirmationModal.tsx # ✅ Implemented
│   │   └── subscriptions/
│   │       └── SubscriptionCard.tsx  # ✅ Implemented
│   │
│   ├── services/
│   │   ├── api.ts               # ✅ Axios client with auth
│   │   ├── apiCatalog.ts        # ✅ API catalog service
│   │   ├── applications.ts      # ✅ Applications service
│   │   └── subscriptions.ts     # ✅ Subscriptions service
│   │
│   ├── hooks/
│   │   ├── useAPIs.ts           # ✅ React Query hooks
│   │   ├── useApplications.ts   # ✅ React Query hooks
│   │   └── useSubscriptions.ts  # ✅ React Query hooks
│   │
│   ├── contexts/
│   │   └── AuthContext.tsx      # ✅ Keycloak auth context
│   │
│   ├── types/
│   │   ├── api.ts               # ✅ API types
│   │   ├── application.ts       # ✅ Application types
│   │   └── subscription.ts      # ✅ Subscription types
│   │
│   ├── config.ts                # ✅ Portal configuration
│   ├── App.tsx                  # ✅ Routes
│   └── main.tsx                 # ✅ Entry point
│
├── public/
│   └── favicon.ico
│
├── package.json
├── vite.config.ts
├── tailwind.config.js
├── tsconfig.json
├── vitest.config.ts             # Unit tests config
└── Dockerfile                   # Production build
```

---

## 📅 Week-by-Week Planning

### Week 1: Foundations + Catalog

| Day | Tasks | Files |
|------|--------|----------|
| **D1** | Setup Vite + React + TS + Tailwind project | `package.json`, `vite.config.ts`, `tailwind.config.js` |
| **D1** | Configure Keycloak OIDC | `src/services/auth.service.ts`, `src/hooks/useAuth.ts` |
| **D2** | Main layout | `src/components/layout/*` |
| **D2** | React Router routing | `src/App.tsx` |
| **D3** | ApiCatalog page | `src/pages/ApiCatalog.tsx` |
| **D3** | ApiCard component | `src/components/api/ApiCard.tsx` |
| **D4** | ApiDetail page (structure) | `src/pages/ApiDetail.tsx` |
| **D4** | Tabs (Doc, Try-It, Code) | `src/pages/ApiDetail.tsx` |
| **D5** | Swagger-UI integration | `src/components/api/SwaggerViewer.tsx` |

**W1 Checklist**:
- [x] Project initialized with Vite
- [x] TailwindCSS configured
- [x] Keycloak auth functional
- [x] Responsive layout
- [x] API Catalog with search
- [x] Detail page with OpenAPI doc

---

### Week 2: Applications + Subscriptions

| Day | Tasks | Files |
|------|--------|----------|
| **D1** | MyApplications page | `src/pages/MyApplications.tsx` |
| **D1** | AppCard component | `src/components/application/AppCard.tsx` |
| **D2** | CreateApplication page | `src/pages/CreateApplication.tsx` |
| **D2** | Application creation form | `src/pages/CreateApplication.tsx` |
| **D3** | Secure ApiKeyDisplay | `src/components/application/ApiKeyDisplay.tsx` |
| **D3** | CredentialsModal | `src/components/application/CredentialsModal.tsx` |
| **D4** | Subscriptions page | `src/pages/Subscriptions.tsx` |
| **D4** | SubscribeButton | `src/components/api/SubscribeButton.tsx` |
| **D5** | Full end-to-end flow | Manual testing |

**W2 Checklist**:
- [x] List my applications
- [x] Create an application
- [x] Display credentials (API Key visible once)
- [x] Rotate API Key
- [x] List my subscriptions
- [x] Subscribe to an API
- [x] Unsubscribe

---

### Week 3: Try-It + Polish

| Day | Tasks | Files |
|------|--------|----------|
| **D1** | RequestBuilder | `src/components/tryit/RequestBuilder.tsx` |
| **D1** | Method, URL, params selection | `src/components/tryit/RequestBuilder.tsx` |
| **D2** | HeadersEditor | `src/components/tryit/HeadersEditor.tsx` |
| **D2** | Body editor (JSON) | `src/components/tryit/RequestBuilder.tsx` |
| **D3** | ResponseViewer | `src/components/tryit/ResponseViewer.tsx` |
| **D3** | Display status, headers, body, timing | `src/components/tryit/ResponseViewer.tsx` |
| **D4** | CodeSamples | `src/components/api/CodeSamples.tsx` |
| **D4** | Generate curl, Python, JavaScript | `src/components/api/CodeSamples.tsx` |
| **D5** | Polish UI | Global |
| **D5** | Loading states, error handling, responsive | Global |

**W3 Checklist**:
- [x] Functional Try-It console (API Testing Sandbox)
- [x] Request sent via Gateway proxy
- [x] Response displayed (status, headers, body)
- [x] Timing displayed
- [x] Code samples generated
- [x] Responsive UI
- [x] Error handling

---

## 🔌 Backend Endpoints to Add

Add these endpoints in the Control Plane API (FastAPI).

### API Catalog

```
GET    /portal/apis
       Query params: ?category=&search=&tenant=
       Response: List of published APIs

GET    /portal/apis/{api_id}
       Response: API detail (name, version, description, tenant, etc.)

GET    /portal/apis/{api_id}/spec
       Response: OpenAPI spec (JSON or YAML)
```

### Applications

```
GET    /portal/my/applications
       Auth: Bearer token
       Response: List of applications for the connected developer

POST   /portal/applications
       Body: { name, description, callback_urls }
       Response: { id, name, client_id, client_secret, api_key }
       Note: client_secret and api_key visible only once

GET    /portal/applications/{app_id}
       Response: Application detail (without secrets)

DELETE /portal/applications/{app_id}
       Response: 204 No Content

POST   /portal/applications/{app_id}/rotate-key
       Response: { new_api_key }
       Note: New key visible only once
```

### Subscriptions

```
GET    /portal/my/subscriptions
       Response: List of subscriptions (app -> API)

POST   /portal/subscriptions
       Body: { application_id, api_id }
       Response: { subscription_id, status }

DELETE /portal/subscriptions/{subscription_id}
       Response: 204 No Content
```

### Try-It (Proxy)

```
POST   /portal/try-it
       Body: {
         api_id,
         application_id,
         method,
         path,
         headers,
         body
       }
       Response: {
         status_code,
         headers,
         body,
         timing_ms
       }
       Note: The backend adds the API Key and forwards to the Gateway
```

---

## 📦 NPM Dependencies

### package.json

```json
{
  "name": "developer-portal",
  "version": "1.0.0",
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "tsc && vite build",
    "preview": "vite preview",
    "lint": "eslint src --ext ts,tsx"
  },
  "dependencies": {
    "react": "^18.2.0",
    "react-dom": "^18.2.0",
    "react-router-dom": "^6.22.0",
    "axios": "^1.6.7",
    "keycloak-js": "^24.0.1",
    "@react-keycloak/web": "^3.4.0",
    "swagger-ui-react": "^5.11.0",
    "@monaco-editor/react": "^4.6.0",
    "react-hot-toast": "^2.4.1",
    "lucide-react": "^0.344.0",
    "clsx": "^2.1.0",
    "date-fns": "^3.3.1"
  },
  "devDependencies": {
    "@types/react": "^18.2.55",
    "@types/react-dom": "^18.2.19",
    "@vitejs/plugin-react": "^4.2.1",
    "autoprefixer": "^10.4.17",
    "eslint": "^8.56.0",
    "eslint-plugin-react-hooks": "^4.6.0",
    "postcss": "^8.4.35",
    "tailwindcss": "^3.4.1",
    "typescript": "^5.3.3",
    "vite": "^5.1.0"
  }
}
```

---

## ⚙️ Configuration Files

### vite.config.ts

```typescript
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 3001,
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, '')
      }
    }
  }
})
```

### tailwind.config.js

```javascript
/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        primary: {
          50: '#eff6ff',
          500: '#3b82f6',
          600: '#2563eb',
          700: '#1d4ed8',
        }
      }
    },
  },
  plugins: [],
}
```

### tsconfig.json

```json
{
  "compilerOptions": {
    "target": "ES2020",
    "useDefineForClassFields": true,
    "lib": ["ES2020", "DOM", "DOM.Iterable"],
    "module": "ESNext",
    "skipLibCheck": true,
    "moduleResolution": "bundler",
    "allowImportingTsExtensions": true,
    "resolveJsonModule": true,
    "isolatedModules": true,
    "noEmit": true,
    "jsx": "react-jsx",
    "strict": true,
    "noUnusedLocals": true,
    "noUnusedParameters": true,
    "noFallthroughCasesInSwitch": true,
    "baseUrl": ".",
    "paths": {
      "@/*": ["src/*"]
    }
  },
  "include": ["src"],
  "references": [{ "path": "./tsconfig.node.json" }]
}
```

---

## 🔐 Configuration Keycloak

### Realm / Client (Implemented)

```yaml
Realm: stoa (existing)

Client:
  client_id: stoa-portal              # Actual client ID used
  client_type: public
  valid_redirect_uris:
    - http://localhost:5173/*         # Vite dev server
    - https://portal.gostoa.dev/*
  web_origins:
    - http://localhost:5173
    - https://portal.gostoa.dev

Roles used:
  - stoa:read   (API Consumer access)
  - stoa:write  (create apps, subscribe)
```

### src/contexts/AuthContext.tsx (Implemented)

```typescript
// Uses @react-keycloak/web with custom AuthContext
import { ReactKeycloakProvider } from '@react-keycloak/web';
import Keycloak from 'keycloak-js';

const keycloak = new Keycloak({
  url: config.keycloak.url,       // https://auth.gostoa.dev
  realm: config.keycloak.realm,   // stoa
  clientId: 'stoa-portal'
});

// AuthContext provides: user, isAuthenticated, login, logout, getAccessToken
```

### Environment Variables (Production)

```env
VITE_BASE_DOMAIN=gostoa.dev
VITE_KEYCLOAK_URL=https://auth.gostoa.dev
VITE_KEYCLOAK_REALM=stoa
VITE_API_URL=https://apis.gostoa.dev/gateway/Control-Plane-API/2.0
VITE_PORTAL_MODE=production
VITE_ENABLE_MCP_TOOLS=true
VITE_ENABLE_API_CATALOG=true
VITE_ENABLE_API_TESTING=true
VITE_ENABLE_SUBSCRIPTIONS=true
VITE_ENABLE_APPLICATIONS=true
```

---

## 🎨 Key Components

### SwaggerViewer.tsx

```typescript
import SwaggerUI from 'swagger-ui-react';
import 'swagger-ui-react/swagger-ui.css';

interface Props {
  specUrl: string;
}

export const SwaggerViewer = ({ specUrl }: Props) => {
  return (
    <SwaggerUI 
      url={specUrl}
      docExpansion="list"
      defaultModelsExpandDepth={-1}
      tryItOutEnabled={false}
    />
  );
};
```

### ApiKeyDisplay.tsx

```typescript
import { useState } from 'react';
import { Eye, EyeOff, Copy, Check } from 'lucide-react';

interface Props {
  apiKey: string;
  onRotate: () => void;
}

export const ApiKeyDisplay = ({ apiKey, onRotate }: Props) => {
  const [visible, setVisible] = useState(false);
  const [copied, setCopied] = useState(false);

  const copyToClipboard = () => {
    navigator.clipboard.writeText(apiKey);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className="flex items-center gap-2 p-3 bg-gray-100 rounded">
      <code className="flex-1 font-mono">
        {visible ? apiKey : '••••••••••••••••'}
      </code>
      <button onClick={() => setVisible(!visible)}>
        {visible ? <EyeOff size={18} /> : <Eye size={18} />}
      </button>
      <button onClick={copyToClipboard}>
        {copied ? <Check size={18} /> : <Copy size={18} />}
      </button>
    </div>
  );
};
```

### CodeSamples.tsx

```typescript
interface Props {
  api: { baseUrl: string; };
  endpoint: { method: string; path: string; };
  apiKey: string;
}

export const CodeSamples = ({ api, endpoint, apiKey }: Props) => {
  const samples = {
    curl: `curl -X ${endpoint.method} \\
  "${api.baseUrl}${endpoint.path}" \\
  -H "X-API-Key: ${apiKey}"`,
    
    python: `import requests

response = requests.${endpoint.method.toLowerCase()}(
    "${api.baseUrl}${endpoint.path}",
    headers={"X-API-Key": "${apiKey}"}
)
print(response.json())`,
    
    javascript: `fetch("${api.baseUrl}${endpoint.path}", {
  method: "${endpoint.method}",
  headers: {
    "X-API-Key": "${apiKey}"
  }
})
.then(res => res.json())
.then(data => console.log(data));`
  };

  return (
    <div className="space-y-4">
      {Object.entries(samples).map(([lang, code]) => (
        <div key={lang}>
          <h4 className="font-semibold capitalize">{lang}</h4>
          <pre className="p-4 bg-gray-900 text-gray-100 rounded overflow-x-auto">
            <code>{code}</code>
          </pre>
        </div>
      ))}
    </div>
  );
};
```

---

## ✅ Final Checklist

### Features

- [x] **Auth**: Keycloak login
- [x] **Auth**: Logout
- [x] **Auth**: Route protection

- [x] **Catalog**: List APIs
- [x] **Catalog**: Search by name
- [x] **Catalog**: Filter by category
- [x] **Catalog**: Filter by tenant

- [x] **API Detail**: General information
- [x] **API Detail**: OpenAPI documentation (custom viewer)
- [x] **API Detail**: Subscribe button

- [x] **Applications**: List my apps
- [x] **Applications**: Create an app
- [x] **Applications**: View credentials
- [x] **Applications**: Rotate API Key
- [x] **Applications**: Delete app

- [x] **Subscriptions**: List my subscriptions
- [x] **Subscriptions**: Subscribe
- [x] **Subscriptions**: Unsubscribe

- [x] **Try-It (API Testing Sandbox)**: Method/path selection
- [x] **Try-It**: Custom headers
- [x] **Try-It**: JSON body
- [x] **Try-It**: Send request
- [x] **Try-It**: Display response
- [x] **Try-It**: Environment selector
- [x] **Try-It**: Production sandbox confirmation

- [x] **Code Samples**: curl
- [x] **Code Samples**: Python
- [x] **Code Samples**: JavaScript

### Technical

- [x] Responsive design
- [x] Loading states
- [x] Error handling
- [x] Toast notifications
- [ ] Dark mode (not implemented - future enhancement)

---

## 🚀 Getting Started

```bash
# Create the project
npm create vite@latest developer-portal -- --template react-ts
cd developer-portal

# Install dependencies
npm install react-router-dom axios keycloak-js @react-keycloak/web
npm install swagger-ui-react @monaco-editor/react
npm install react-hot-toast lucide-react clsx date-fns
npm install -D tailwindcss postcss autoprefixer
npx tailwindcss init -p

# Start the dev server
npm run dev
```

---

## 📝 Notes

- The backend (Control Plane API) must expose the `/portal/*` endpoints
- Credentials (client_secret, api_key) are only visible once at creation
- Try-It goes through a backend proxy to automatically add the API Key
- Keycloak: use the existing `stoa` realm with the `stoa-portal` client

---

## 🎉 Implementation Notes (CAB-246)

### What Was Built

The Developer Portal was implemented as a separate React application (`portal/`) distinct from the Console UI (`control-plane-ui/`):

| Application | Purpose | URL | Keycloak Client |
|------------|---------|-----|-----------------|
| Console UI | API Provider (DevOps, Admin) | https://console.gostoa.dev | control-plane-ui |
| Developer Portal | API Consumer (Browse, Subscribe, Test) | https://portal.gostoa.dev | stoa-portal |

### Key Implementation Details

1. **Project Structure**: Located in `portal/` directory (not `developer-portal/`)
2. **Vite Dev Server**: Port 5173 (not 3001 as originally planned)
3. **Keycloak Client**: `stoa-portal` (not `developer-portal`)
4. **API Access**: Via Gateway at `apis.gostoa.dev/gateway/Control-Plane-API/2.0`
5. **OpenAPI Viewer**: Custom component (not swagger-ui-react)
6. **State Management**: React Query (TanStack Query) for server state

### Bonus Features Implemented

- **MCP Tools Catalog**: Browse and test AI-powered tools
- **Portal Modes**: Production vs Non-Production with different sandbox behaviors
- **Environment Selector**: Support for multiple environments (dev, staging, prod)
- **Sandbox Confirmation**: Modal confirmation for production API testing
- **Test History**: Track recent API test requests

### CI/CD

- **Workflow**: `.github/workflows/stoa-portal-ci.yml`
- **Docker Image**: Built on push to main
- **Deployment**: Kubernetes via Helm chart

### Future Enhancements

- [ ] Dark mode theme
- [ ] Non-production portal deployment (`portal.dev.gostoa.dev`)
- [ ] API usage analytics dashboard
- [ ] Webhook management
- [ ] Team collaboration features

---

Happy coding! 🎯

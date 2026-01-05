# Developer Portal Custom - Development Plan

## 📋 Overview

**Objective**: Replace the IBM Developer Portal with a custom React portal integrated into the APIM GitOps architecture.

**Estimated Duration**: 3 weeks

**Tech Stack**:
- Frontend: React + TypeScript + Vite + TailwindCSS
- Auth: Keycloak OIDC
- Backend: Control Plane API (FastAPI) - endpoints to add
- Documentation: Swagger-UI or Redoc

---

## 📁 Project Structure

```
developer-portal/
├── src/
│   ├── pages/
│   │   ├── Home.tsx
│   │   ├── ApiCatalog.tsx
│   │   ├── ApiDetail.tsx
│   │   ├── TryIt.tsx
│   │   ├── MyApplications.tsx
│   │   ├── CreateApplication.tsx
│   │   ├── Subscriptions.tsx
│   │   ├── Profile.tsx
│   │   └── Login.tsx
│   │
│   ├── components/
│   │   ├── layout/
│   │   │   ├── Header.tsx
│   │   │   ├── Footer.tsx
│   │   │   └── Sidebar.tsx
│   │   ├── api/
│   │   │   ├── ApiCard.tsx
│   │   │   ├── SwaggerViewer.tsx
│   │   │   ├── CodeSamples.tsx
│   │   │   └── SubscribeButton.tsx
│   │   ├── application/
│   │   │   ├── AppCard.tsx
│   │   │   ├── ApiKeyDisplay.tsx
│   │   │   └── CredentialsModal.tsx
│   │   └── tryit/
│   │       ├── RequestBuilder.tsx
│   │       ├── ResponseViewer.tsx
│   │       └── HeadersEditor.tsx
│   │
│   ├── services/
│   │   ├── api.service.ts
│   │   ├── auth.service.ts
│   │   └── portal.service.ts
│   │
│   ├── hooks/
│   │   ├── useAuth.ts
│   │   ├── useApis.ts
│   │   ├── useApplications.ts
│   │   └── useSubscriptions.ts
│   │
│   ├── types/
│   │   └── index.ts
│   │
│   ├── App.tsx
│   └── main.tsx
│
├── public/
│   └── favicon.ico
│
├── package.json
├── vite.config.ts
├── tailwind.config.js
├── tsconfig.json
└── README.md
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
- [ ] Project initialized with Vite
- [ ] TailwindCSS configured
- [ ] Keycloak auth functional
- [ ] Responsive layout
- [ ] API Catalog with search
- [ ] Detail page with OpenAPI doc

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
- [ ] List my applications
- [ ] Create an application
- [ ] Display credentials (API Key visible once)
- [ ] Rotate API Key
- [ ] List my subscriptions
- [ ] Subscribe to an API
- [ ] Unsubscribe

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
- [ ] Functional Try-It console
- [ ] Request sent via backend proxy
- [ ] Response displayed (status, headers, body)
- [ ] Timing displayed
- [ ] Code samples generated
- [ ] Responsive UI
- [ ] Error handling

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

### Realm / Client

```yaml
Realm: stoa-platform (existing)

Client:
  client_id: developer-portal
  client_type: public
  valid_redirect_uris:
    - http://localhost:3001/*
    - https://portal.stoa.cab-i.com/*
  web_origins:
    - http://localhost:3001
    - https://portal.stoa.cab-i.com

Role to create:
  - developer (portal access)
```

### src/services/auth.service.ts

```typescript
import Keycloak from 'keycloak-js';

const keycloak = new Keycloak({
  url: import.meta.env.VITE_KEYCLOAK_URL,
  realm: import.meta.env.VITE_KEYCLOAK_REALM,
  clientId: 'developer-portal'
});

export { keycloak };
```

### .env

```env
VITE_KEYCLOAK_URL=https://keycloak.stoa.cab-i.com
VITE_KEYCLOAK_REALM=stoa-platform
VITE_API_URL=https://api.stoa.cab-i.com
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

- [ ] **Auth**: Keycloak login
- [ ] **Auth**: Logout
- [ ] **Auth**: Route protection

- [ ] **Catalog**: List APIs
- [ ] **Catalog**: Search by name
- [ ] **Catalog**: Filter by category
- [ ] **Catalog**: Filter by tenant

- [ ] **API Detail**: General information
- [ ] **API Detail**: Swagger documentation
- [ ] **API Detail**: Subscribe button

- [ ] **Applications**: List my apps
- [ ] **Applications**: Create an app
- [ ] **Applications**: View credentials
- [ ] **Applications**: Rotate API Key
- [ ] **Applications**: Delete app

- [ ] **Subscriptions**: List my subscriptions
- [ ] **Subscriptions**: Subscribe
- [ ] **Subscriptions**: Unsubscribe

- [ ] **Try-It**: Method/path selection
- [ ] **Try-It**: Custom headers
- [ ] **Try-It**: JSON body
- [ ] **Try-It**: Send request
- [ ] **Try-It**: Display response

- [ ] **Code Samples**: curl
- [ ] **Code Samples**: Python
- [ ] **Code Samples**: JavaScript

### Technical

- [ ] Responsive design
- [ ] Loading states
- [ ] Error handling
- [ ] Toast notifications
- [ ] Dark mode (optional)

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
- Keycloak: use the existing `stoa-platform` realm with a new `developer-portal` client

---

Happy coding! 🎯

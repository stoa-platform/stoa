# Developer Portal Custom - Plan de Développement

## 📋 Vue d'ensemble

**Objectif** : Remplacer le Developer Portal IBM par un portal custom React intégré à l'architecture APIM GitOps.

**Durée estimée** : 3 semaines

**Stack technique** :
- Frontend : React + TypeScript + Vite + TailwindCSS
- Auth : Keycloak OIDC
- Backend : Control Plane API (FastAPI) - endpoints à ajouter
- Documentation : Swagger-UI ou Redoc

---

## 📁 Structure du Projet

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

## 📅 Planning Semaine par Semaine

### Semaine 1 : Fondations + Catalogue

| Jour | Tâches | Fichiers |
|------|--------|----------|
| **J1** | Setup projet Vite + React + TS + Tailwind | `package.json`, `vite.config.ts`, `tailwind.config.js` |
| **J1** | Config Keycloak OIDC | `src/services/auth.service.ts`, `src/hooks/useAuth.ts` |
| **J2** | Layout principal | `src/components/layout/*` |
| **J2** | Routing React Router | `src/App.tsx` |
| **J3** | Page ApiCatalog | `src/pages/ApiCatalog.tsx` |
| **J3** | Composant ApiCard | `src/components/api/ApiCard.tsx` |
| **J4** | Page ApiDetail (structure) | `src/pages/ApiDetail.tsx` |
| **J4** | Tabs (Doc, Try-It, Code) | `src/pages/ApiDetail.tsx` |
| **J5** | Intégration Swagger-UI | `src/components/api/SwaggerViewer.tsx` |

**Checklist S1** :
- [ ] Projet initialisé avec Vite
- [ ] TailwindCSS configuré
- [ ] Keycloak auth fonctionnelle
- [ ] Layout responsive
- [ ] Catalogue APIs avec recherche
- [ ] Page détail avec doc OpenAPI

---

### Semaine 2 : Applications + Souscriptions

| Jour | Tâches | Fichiers |
|------|--------|----------|
| **J1** | Page MyApplications | `src/pages/MyApplications.tsx` |
| **J1** | Composant AppCard | `src/components/application/AppCard.tsx` |
| **J2** | Page CreateApplication | `src/pages/CreateApplication.tsx` |
| **J2** | Formulaire création app | `src/pages/CreateApplication.tsx` |
| **J3** | ApiKeyDisplay sécurisé | `src/components/application/ApiKeyDisplay.tsx` |
| **J3** | CredentialsModal | `src/components/application/CredentialsModal.tsx` |
| **J4** | Page Subscriptions | `src/pages/Subscriptions.tsx` |
| **J4** | SubscribeButton | `src/components/api/SubscribeButton.tsx` |
| **J5** | Flow complet end-to-end | Tests manuels |

**Checklist S2** :
- [ ] Liste mes applications
- [ ] Créer une application
- [ ] Afficher credentials (API Key visible une fois)
- [ ] Rotation API Key
- [ ] Liste mes souscriptions
- [ ] Souscrire à une API
- [ ] Désouscrire

---

### Semaine 3 : Try-It + Polish

| Jour | Tâches | Fichiers |
|------|--------|----------|
| **J1** | RequestBuilder | `src/components/tryit/RequestBuilder.tsx` |
| **J1** | Sélection méthode, URL, params | `src/components/tryit/RequestBuilder.tsx` |
| **J2** | HeadersEditor | `src/components/tryit/HeadersEditor.tsx` |
| **J2** | Body editor (JSON) | `src/components/tryit/RequestBuilder.tsx` |
| **J3** | ResponseViewer | `src/components/tryit/ResponseViewer.tsx` |
| **J3** | Affichage status, headers, body, timing | `src/components/tryit/ResponseViewer.tsx` |
| **J4** | CodeSamples | `src/components/api/CodeSamples.tsx` |
| **J4** | Génération curl, Python, JavaScript | `src/components/api/CodeSamples.tsx` |
| **J5** | Polish UI | Global |
| **J5** | Loading states, error handling, responsive | Global |

**Checklist S3** :
- [ ] Console Try-It fonctionnelle
- [ ] Requête envoyée via proxy backend
- [ ] Réponse affichée (status, headers, body)
- [ ] Timing affiché
- [ ] Code samples générés
- [ ] UI responsive
- [ ] Gestion erreurs

---

## 🔌 Endpoints Backend à Ajouter

Ajouter ces endpoints dans le Control Plane API (FastAPI).

### Catalogue APIs

```
GET    /portal/apis
       Query params: ?category=&search=&tenant=
       Response: Liste des APIs publiées

GET    /portal/apis/{api_id}
       Response: Détail API (name, version, description, tenant, etc.)

GET    /portal/apis/{api_id}/spec
       Response: Spec OpenAPI (JSON ou YAML)
```

### Applications

```
GET    /portal/my/applications
       Auth: Bearer token
       Response: Liste des applications du développeur connecté

POST   /portal/applications
       Body: { name, description, callback_urls }
       Response: { id, name, client_id, client_secret, api_key }
       Note: client_secret et api_key visibles une seule fois

GET    /portal/applications/{app_id}
       Response: Détail application (sans secrets)

DELETE /portal/applications/{app_id}
       Response: 204 No Content

POST   /portal/applications/{app_id}/rotate-key
       Response: { new_api_key }
       Note: Nouvelle clé visible une seule fois
```

### Souscriptions

```
GET    /portal/my/subscriptions
       Response: Liste des souscriptions (app -> API)

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
       Note: Le backend ajoute l'API Key et forward vers le Gateway
```

---

## 📦 Dépendances NPM

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

## ⚙️ Fichiers de Configuration

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
Realm: stoa-platform (existant)

Client:
  client_id: developer-portal
  client_type: public
  valid_redirect_uris:
    - http://localhost:3001/*
    - https://portal.stoa.cab-i.com/*
  web_origins:
    - http://localhost:3001
    - https://portal.stoa.cab-i.com
  
Rôle à créer:
  - developer (accès portal)
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
VITE_KEYCLOAK_URL=https://keycloak.dev.stoa.cab-i.com
VITE_KEYCLOAK_REALM=stoa-platform
VITE_API_URL=https://api.dev.stoa.cab-i.com
```

---

## 🎨 Composants Clés

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

## ✅ Checklist Finale

### Fonctionnalités

- [ ] **Auth** : Connexion Keycloak
- [ ] **Auth** : Déconnexion
- [ ] **Auth** : Protection des routes

- [ ] **Catalogue** : Liste des APIs
- [ ] **Catalogue** : Recherche par nom
- [ ] **Catalogue** : Filtre par catégorie
- [ ] **Catalogue** : Filtre par tenant

- [ ] **API Detail** : Informations générales
- [ ] **API Detail** : Documentation Swagger
- [ ] **API Detail** : Bouton souscrire

- [ ] **Applications** : Liste mes apps
- [ ] **Applications** : Créer une app
- [ ] **Applications** : Voir credentials
- [ ] **Applications** : Rotation API Key
- [ ] **Applications** : Supprimer app

- [ ] **Souscriptions** : Liste mes souscriptions
- [ ] **Souscriptions** : Souscrire
- [ ] **Souscriptions** : Désouscrire

- [ ] **Try-It** : Sélection méthode/path
- [ ] **Try-It** : Headers custom
- [ ] **Try-It** : Body JSON
- [ ] **Try-It** : Envoi requête
- [ ] **Try-It** : Affichage réponse

- [ ] **Code Samples** : curl
- [ ] **Code Samples** : Python
- [ ] **Code Samples** : JavaScript

### Technique

- [ ] Responsive design
- [ ] Loading states
- [ ] Error handling
- [ ] Toast notifications
- [ ] Dark mode (optionnel)

---

## 🚀 Commandes de Démarrage

```bash
# Créer le projet
npm create vite@latest developer-portal -- --template react-ts
cd developer-portal

# Installer les dépendances
npm install react-router-dom axios keycloak-js @react-keycloak/web
npm install swagger-ui-react @monaco-editor/react
npm install react-hot-toast lucide-react clsx date-fns
npm install -D tailwindcss postcss autoprefixer
npx tailwindcss init -p

# Lancer le dev server
npm run dev
```

---

## 📝 Notes

- Le backend (Control Plane API) doit exposer les endpoints `/portal/*`
- Les credentials (client_secret, api_key) ne sont visibles qu'une fois à la création
- Le Try-It passe par un proxy backend pour ajouter l'API Key automatiquement
- Keycloak : utiliser le realm existant `stoa-platform` avec un nouveau client `developer-portal`

---

Bon développement ! 🎯

---
description: Content compliance rules for public-facing docs — competitor mentions, client names, pricing, certifications
---

# Content Compliance

## Scope

Toute documentation publique ou contenu marketing:
- **stoa-docs** (Docusaurus): `docs/`, `blog/`
- **stoa-web** (Astro): landing pages, comparaisons
- **stoa** (monorepo): `docs/` (runbooks, guides publics)

## Risk Categories

### P0 — Bloquant (interdit, jamais acceptable)

| Type | Exemples | Risque |
|------|----------|--------|
| Claims tarifaires concurrents | "Kong costs $X per call", "IBM licenses are expensive" | Diffamation commerciale |
| Noms de clients sans autorisation | "Acme Corp uses STOA", "deployed at BNP Paribas" | Breach confidentialite |
| Claims de certification | "STOA is DORA-compliant", "certified ISO 27001" | Fausse declaration |
| Declarations diffamatoires | "Kong is insecure", "MuleSoft is a scam" | Diffamation |
| Captures d'ecran concurrents | Screenshots d'UI, pricing pages, dashboards | Copyright |
| Prix specifiques concurrents | "$50,000/year", "starting at $X" | Information non-verifiable |

### P1 — Important (a corriger avant publication)

| Type | Exemples | Risque |
|------|----------|--------|
| Comparaisons features sans source/date | "Kong doesn't support MCP" (sans "last verified") | Information obsolete |
| Caracterisations negatives de categories | "legacy API gateways", "traditional solutions" | Risque reputationnel |
| Disclaimers manquants | Comparaison sans footer disclaimer | Risque legal |
| Claims "last verified" > 6 mois | Date de verification expiree | Information potentiellement obsolete |
| Claims reglementaires sans nuance | "enables DORA compliance" (au lieu de "supports") | Sur-engagement |

### P2 — Suggestion (non-bloquant)

| Type | Exemples | Risque |
|------|----------|--------|
| Attribution trademark manquante | "Kong" sans (TM), "MuleSoft" sans (R) | Trademark dilution |
| Lien trademarks.md manquant | Page sans reference aux trademarks | Best practice |
| Formulations ameliorables | "better than" vs "alternative to" | Ton agressif |

## Forbidden (toujours P0)

- Prix specifiques de concurrents (meme si publics)
- Noms de clients/partenaires sans accord ecrit
- Claims "certified", "compliant", "approved by" sans certification reelle
- Captures d'ecran ou reproductions d'UI de concurrents
- Code source ou documentation interne de concurrents
- Declarations sur la sante financiere d'un concurrent

## Allowed with Conditions

### Comparaisons de features
- **Obligatoire**: source publique + date "last verified: YYYY-MM"
- **Formulation**: "As of [date], [product] [does/does not] offer [feature] ([source])"
- **Interdiction**: termes subjectifs ("better", "superior", "best")

### Claims reglementaires
- **Autorise**: "supports compliance with", "helps organizations align with"
- **Interdit**: "is compliant with", "certified for", "guarantees compliance"
- **Obligatoire**: disclaimer "STOA does not provide legal advice"

### Mentions de migration
- **Autorise**: "migrate from [product]" comme cas d'usage technique
- **Interdit**: "escape from", "stop paying for", "replace your expensive"

### Positionnement marche
- **Autorise**: "alternative to", "compared to", "open-source option"
- **Interdit**: "replacement for", "better than", "superior to"

## Disclaimer Templates

### Comparaison de features
```
> Feature comparisons are based on publicly available documentation as of
> [YYYY-MM]. Product capabilities change frequently. We encourage readers
> to verify current features directly with each vendor. All trademarks
> belong to their respective owners. See [trademarks](/legal/trademarks).
```

### Reglementation
```
> STOA Platform provides technical capabilities that support regulatory
> compliance efforts. This does not constitute legal advice or a guarantee
> of compliance. Organizations should consult qualified legal counsel for
> compliance requirements.
```

### Migration guide
```
> This guide describes technical migration steps and does not imply any
> deficiency in the source platform. Migration decisions depend on
> specific organizational requirements. All trademarks belong to their
> respective owners.
```

### Landing page
```
> Product names and logos are trademarks of their respective owners. STOA
> Platform is not affiliated with or endorsed by any mentioned vendor.
> See [trademarks](/legal/trademarks) for details.
```

## Politique "Last Verified"

Toute claim comparative doit porter une date "last verified":

| Age | Statut | Action |
|-----|--------|--------|
| < 6 mois | OK | Aucune |
| 6-12 mois | P1 | Re-verifier et mettre a jour la date |
| > 12 mois | P0 | Supprimer ou re-verifier immediatement |

Format: `<!-- last verified: YYYY-MM -->` dans le source, ou inline "(last verified: YYYY-MM)".

## Concurrents connus

Liste non-exhaustive des produits a surveiller:

| Categorie | Produits |
|-----------|----------|
| API Gateway OSS | Kong, Tyk, Gravitee, Apache APISIX, KrakenD |
| API Gateway Enterprise | Apigee (Google), MuleSoft (Salesforce), webMethods (Software AG), IBM API Connect |
| API Gateway Cloud | AWS API Gateway, Azure APIM, GCP Apigee, Cloudflare API Shield |
| Integration/iPaaS | MuleSoft Anypoint, Boomi, Workato, Celigo |
| Legacy / On-Prem | Oracle API Gateway, Oracle OAM, IBM DataPower, Axway |
| MCP / AI Gateway | Anthropic MCP, OpenAI Plugins, LangChain, Portkey |

Toute mention d'un de ces noms dans du contenu public declenche le scan content-reviewer.

## Checklist rapide (pour auteurs)

1. Ai-je mentionne un concurrent par nom? → Verifier source + date + disclaimer
2. Ai-je mentionne un client? → Retirer sauf autorisation ecrite
3. Ai-je mentionne un prix? → Retirer (meme si public)
4. Ai-je dit "compliant" ou "certified"? → Reformuler en "supports compliance"
5. Ai-je utilise "legacy", "outdated", "expensive"? → Reformuler en neutre
6. Mon disclaimer est-il present? → Ajouter le template adapte

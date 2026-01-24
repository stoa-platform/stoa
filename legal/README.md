# STOA Legal Templates

Ce dossier contient les templates juridiques pour STOA Platform.

## Documents disponibles

### NDA Design Partner — Individuel

Pour les contacts indépendants, consultants, développeurs qui testent STOA en tant que design partners.

| Document | Langue | Usage |
|----------|--------|-------|
| [NDA_DESIGN_PARTNER_INDIVIDUAL_FR.md](./NDA_DESIGN_PARTNER_INDIVIDUAL_FR.md) | 🇫🇷 Français | Contacts francophones |
| [NDA_DESIGN_PARTNER_INDIVIDUAL_EN.md](./NDA_DESIGN_PARTNER_INDIVIDUAL_EN.md) | 🇬🇧 English | International contacts |

**Points clés :**
- Durée de confidentialité : 2 ans
- Non-concurrence : 12 mois
- Durée du programme : 6 mois (renouvelable)

### Design Partner Agreement — Entreprise

Pour les entreprises (banques, assurances, grands comptes) qui évaluent STOA Platform.

| Document | Langue | Usage |
|----------|--------|-------|
| [DESIGN_PARTNER_AGREEMENT_ENTERPRISE_FR.md](./DESIGN_PARTNER_AGREEMENT_ENTERPRISE_FR.md) | 🇫🇷 Français | Entreprises françaises |
| [DESIGN_PARTNER_AGREEMENT_ENTERPRISE_EN.md](./DESIGN_PARTNER_AGREEMENT_ENTERPRISE_EN.md) | 🇬🇧 English | International companies |

**Points clés :**
- Durée de confidentialité : 3 ans
- Non-concurrence : 18 mois
- Durée du programme : 6 mois (renouvelable)
- Réduction commerciale : 20% si conversion dans les 6 mois post-GA
- Clauses témoignage et logo incluses

## Usage

### Génération PDF

Pour convertir en PDF avec mise en page professionnelle :

```bash
# Avec pandoc + LaTeX
pandoc NDA_DESIGN_PARTNER_INDIVIDUAL_FR.md -o NDA_DESIGN_PARTNER_INDIVIDUAL_FR.pdf \
  --pdf-engine=xelatex \
  -V geometry:margin=2.5cm \
  -V fontsize=11pt

# Ou avec md-to-pdf (npm)
npx md-to-pdf NDA_DESIGN_PARTNER_INDIVIDUAL_FR.md
```

### Signature électronique

Ces documents peuvent être signés via :
- DocuSign
- Yousign (conforme eIDAS)
- HelloSign
- Signature manuscrite scannée

## Avertissement juridique

⚠️ **Ces templates sont fournis à titre indicatif.** 

Il est recommandé de les faire valider par un conseil juridique avant utilisation, notamment pour :
- Les entreprises du secteur financier (DORA, NIS2)
- Les administrations publiques
- Les engagements avec des partenaires stratégiques

## Mises à jour

| Version | Date | Changements |
|---------|------|-------------|
| 1.0 | 2026-01-23 | Création initiale |

---

## Contact

Pour toute question juridique :
- Email : legal@gostoa.dev
- Contact commercial : christophe@gostoa.dev

---

*Généré pour STOA Platform — HLFH / CAB Ingénierie*

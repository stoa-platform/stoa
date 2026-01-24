# STOA Legal Templates

This directory contains legal templates for STOA Platform.

## Available Documents

### NDA Design Partner - Individual

For independent contacts, consultants, and developers testing STOA as design partners.

| Document | Usage |
|----------|-------|
| [NDA_DESIGN_PARTNER_INDIVIDUAL_EN.md](./NDA_DESIGN_PARTNER_INDIVIDUAL_EN.md) | Individual partners |

**Key Terms:**
- Confidentiality duration: 2 years
- Non-compete: 12 months
- Program duration: 6 months (renewable)

### Design Partner Agreement - Enterprise

For enterprises (banks, insurance companies, large accounts) evaluating STOA Platform.

| Document | Usage |
|----------|-------|
| [DESIGN_PARTNER_AGREEMENT_ENTERPRISE_EN.md](./DESIGN_PARTNER_AGREEMENT_ENTERPRISE_EN.md) | Enterprise partners |

**Key Terms:**
- Confidentiality duration: 3 years
- Non-compete: 18 months
- Program duration: 6 months (renewable)
- Commercial discount: 20% if conversion within 6 months post-GA
- Testimonial and logo clauses included

## Usage

### PDF Generation

To convert to PDF with professional formatting:

```bash
# With pandoc + LaTeX
pandoc NDA_DESIGN_PARTNER_INDIVIDUAL_EN.md -o NDA_DESIGN_PARTNER_INDIVIDUAL_EN.pdf \
  --pdf-engine=xelatex \
  -V geometry:margin=2.5cm \
  -V fontsize=11pt

# Or with md-to-pdf (npm)
npx md-to-pdf NDA_DESIGN_PARTNER_INDIVIDUAL_EN.md
```

### Electronic Signature

These documents can be signed via:
- DocuSign
- Yousign (eIDAS compliant)
- HelloSign
- Scanned handwritten signature

## Legal Disclaimer

**These templates are provided for informational purposes only.**

It is recommended to have them validated by legal counsel before use, particularly for:
- Financial sector companies (DORA, NIS2)
- Public administrations
- Strategic partner engagements

## Updates

| Version | Date | Changes |
|---------|------|---------|
| 1.0 | 2026-01-23 | Initial creation |
| 1.1 | 2026-01-24 | Converted to OSS templates |

---

## Contact

For legal questions:
- Email: legal@gostoa.dev

---

*Generated for STOA Platform*

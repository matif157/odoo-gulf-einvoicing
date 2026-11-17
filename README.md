# Gulf E-Invoicing for Odoo 19

**ZATCA Phase 1 QR codes and UBL 2.1 e-invoice XML for Saudi Arabia — as an installable Odoo 19 module.**

[![Odoo](https://img.shields.io/badge/Odoo-19.0-875A7B)](https://www.odoo.com)
[![License](https://img.shields.io/badge/license-LGPL--3-blue)](LICENSE)
[![Tests](https://github.com/matif157/odoo-gulf-einvoicing/actions/workflows/ci.yml/badge.svg)](https://github.com/matif157/odoo-gulf-einvoicing/actions)

---

## Why this exists

Saudi Arabia's ZATCA (Fatoora) programme makes e-invoicing mandatory. **Phase 2, Wave 24**
pulls every business with VAT-taxable revenue above **SAR 375,000** into integration by
**30 June 2026**, when the penalty waiver ends. Every Odoo partner in the Gulf is being
asked the same two questions right now:

1. Does the invoice print the ZATCA QR code?
2. Can you send me the invoice as UBL 2.1 XML?

Odoo Enterprise has a Saudi localisation. **Odoo Community does not.** Partners running
Community — and most mid-size Saudi businesses do — have no compliant path.

This module is that path, for the generation half of the problem.

---

## What it does

| Feature | Detail |
|---|---|
| **ZATCA Phase 1 QR** | 5-field TLV (seller name, VAT number, timestamp, total with VAT, VAT total), base64-encoded |
| **UBL 2.1 XML** | Full `Invoice` document with ICV, PIH, QR reference, supplier/customer tax schemes, per-line VAT |
| **Invoice type codes** | `0100000` standard (B2B) and `0200000` simplified (B2C) |
| **One button** | *Generate E-Invoice* on the invoice header |
| **Audit trail** | UUID, payload, XML, timestamp and status stored on the move, with a chatter entry |
| **Multi-currency** | Second `cac:TaxTotal` emitted in the tax currency when it differs |
| **37 pure-Python tests** | The compliance logic runs and is tested without a database |
| **14 Odoo tests** | End-to-end through `account.move` |

---

## Install

### Native (recommended on 8 GB machines)

```bash
# 1. Odoo 19 source
git clone --depth 1 --branch 19.0 https://github.com/odoo/odoo.git ~/odoo
cd ~/odoo
python3.12 -m venv ~/.odoo-venv
source ~/.odoo-venv/bin/activate
pip install -r requirements.txt

# 2. This module next to it
git clone https://github.com/matif157/odoo-gulf-einvoicing.git ~/odoo-gulf-einvoicing

# 3. Run
~/odoo/odoo-bin \
  --addons-path=~/odoo/addons,~/odoo-gulf-einvoicing \
  -d gulf -i gulf_einvoicing \
  --db_host=localhost --db_user=$USER
```

### Docker

```bash
git clone https://github.com/matif157/odoo-gulf-einvoicing.git
cd odoo-gulf-einvoicing
docker compose up -d
```

Open <http://localhost:8069>, create the database, then
**Apps → Update Apps List → Gulf E-Invoicing (ZATCA / UBL) → Install**.

---

## Use it

1. **Settings → Companies →** set the company name, VAT number and Commercial
   Registration No., tick *Gulf E-Invoicing*.
2. **Accounting → Customers → Invoices →** create an invoice with a VAT tax on the lines.
3. Press **Generate E-Invoice**.
4. The **Gulf E-Invoice** tab now shows the base64 QR payload, the UUID, and a
   downloadable `INV-2026-0001.xml`.

---

## Test it

```bash
# The compliance library — no Odoo, no database, 37 tests, under a second
python3 -m unittest discover -s tests -t tests -v

# The Odoo module — needs a database
odoo -d testdb -i gulf_einvoicing --test-tags /gulf_einvoicing --stop-after-init
```

---

## How it works

```
account.move ──────────────────────────────┐
      │                                    │
      ├─► gulf_einvoicing/lib/zatca_qr.py ──► base64 TLV  ──► QR on the invoice
      │        (seller name, VAT no., timestamp, total, VAT)
      │
      └─► gulf_einvoicing/lib/ubl.py ───────► UBL 2.1 XML  ──► ZATCA / buyer system
               (ICV, PIH, parties, tax totals, lines)
```

Both helpers are **pure Python**. They do not import Odoo, which is why they can be
unit-tested in under a second and reused by any Python system.

### Design decisions

1. **The TLV encoder is a library, not a method on the model.** Compliance logic that
   lives inside an ORM method cannot be tested without a database, cannot be reused, and
   cannot be audited by a customer's IT team. Ours is 120 lines of pure Python with 20
   tests pointing at it.
2. **The XML is generated, never templated.** String templates break the moment a
   customer name contains `&`. The UBL builder uses `ElementTree` with real namespaces,
   so escaping, ordering and well-formedness are guaranteed by the parser, not by hope.
3. **Generation is a recorded event, not a computed field.** A ZATCA invoice must be
   auditable: which UUID, which payload, generated when, by whom. Storing it and logging
   it in the chatter is the difference between a demo and something an auditor accepts.
4. **Phase 2 is deliberately absent.** Cryptographic stamping and CSID onboarding are not
   a weekend feature. Shipping a half-signed invoice would be worse than shipping none —
   a business could believe it is compliant when it is not.
5. **The error message lists every problem at once.** "VAT number missing" then "customer
   name missing" then "no lines" is three round-trips for the user. One message, all
   problems.

---

## Roadmap

- [x] v1.0 — Phase 1 QR, UBL 2.1 XML, both invoice type codes, audit fields, tests
- [ ] v1.1 — QR image embedded in the invoice PDF (QWeb report patch)
- [ ] v1.2 — UAE PINT AE profile (same builder, different ruleset)
- [ ] v1.3 — Credit note (`cac:CreditNote`) support
- [ ] v1.4 — CSV/JSON export batch for accountants
- [ ] v2.0 — **Phase 2**: CSID onboarding, XAdES signing, clearance/reporting API, PIH chain

---

## Compatibility

- Odoo 19.0 Community (Enterprise works too)
- PostgreSQL 13+
- Python 3.10+
- No external service, no API key, no paid dependency

---

## Author

**Muhammad Atif** — Odoo implementation and business automation, Faisalabad, Pakistan.

- GitHub: [github.com/matif157](https://github.com/matif157)
- Portfolio: [matif157.github.io](https://matif157.github.io)
- Email: matifzahoor1577@gmail.com

Available for Odoo implementation work and junior/mid Odoo developer roles.

---

## License

LGPL-3.0. See [LICENSE](LICENSE).

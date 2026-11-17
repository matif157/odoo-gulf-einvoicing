{
    "name": "Gulf E-Invoicing (ZATCA / UBL)",
    "version": "19.0.1.0.0",
    "category": "Accounting/Localizations",
    "summary": "ZATCA Phase 1 QR codes and UBL 2.1 e-invoice XML for Saudi Arabia and the Gulf",
    "description": """
Gulf E-Invoicing
================

Saudi Arabia's ZATCA (Fatoora) programme requires every VAT-registered business
to print a compliant QR code on every tax invoice, and to be able to produce the
invoice as a UBL 2.1 document.

Odoo Community ships neither of those for Saudi Arabia.

This module adds them:

* ZATCA Phase 1 QR payload (5-field TLV, base64) generated from the real invoice
* UBL 2.1 Invoice XML with ICV, PIH, seller/buyer VAT schemes and per-line VAT
* Standard and simplified invoice type codes (0100000 / 0200000)
* One button on the invoice, everything stored on the record for audit
* Pure-Python compliance library with 37 unit tests that run without a database

Phase 2 (cryptographic stamping, CSID onboarding, clearance/reporting API) is on
the roadmap, not in this release.
""",
    "author": "Muhammad Atif",
    "website": "https://github.com/matif157/odoo-gulf-einvoicing",
    "license": "LGPL-3",
    "depends": [
        "base",
        "account",
    ],
    "data": [
        "views/res_company_views.xml",
        "views/account_move_views.xml",
    ],
    "installable": True,
    "application": True,
    "auto_install": False,
}

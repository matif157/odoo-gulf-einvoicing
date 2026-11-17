# Part of Gulf E-Invoicing. See LICENSE file for full copyright and licensing details.
"""
UBL 2.1 invoice builder for ZATCA (Saudi Arabia).

Pure Python, no Odoo dependency.

Output follows the element order ZATCA's XSD enforces: InvoiceTypeCode,
DocumentCurrencyCode, TaxCurrencyCode, AdditionalDocumentReference, parties,
TaxTotal, LegalMonetaryTotal, InvoiceLine.

What this covers
----------------
* Phase 1 generation: a valid UBL 2.1 document with the QR payload embedded,
  ICV and PIH references, seller/buyer tax schemes, per-line VAT.
* Phase 2 submission (cryptographic stamping, CSID onboarding, clearance API)
  is deliberately NOT included - see the README roadmap.
"""

import xml.etree.ElementTree as ET
from datetime import date
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

UBL_NS = "urn:oasis:names:specification:ubl:schema:xsd:Invoice-2"
CAC_NS = "urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2"
CBC_NS = "urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2"

ET.register_namespace("", UBL_NS)
ET.register_namespace("cac", CAC_NS)
ET.register_namespace("cbc", CBC_NS)

# ZATCA invoice type code (name attribute): 7 digits
#   digit 1-2: 01 standard tax invoice, 02 simplified tax invoice
#   digit 3:   0 = not a third-party invoice
#   digit 4:   0 = nominal (not summary)
#   digit 5-7: 0000 reserved to ZATCA
INVOICE_TYPE_CODES = {
    "standard": "0100000",
    "simplified": "0200000",
}

# ZATCA's published placeholder for the first invoice in a chain.
DEFAULT_PIH = (
    "NWZlY2ViNjZmZmM4NmYzOGQ5NTI3ODZjNmQ2OTZjNzljMmRiYzIzOWRkNGU5MWI0Njcy"
    "OWQ3M2EyN2ZiNTdlOQ=="
)


class UblError(ValueError):
    """Raised when the invoice cannot be expressed as a UBL document."""


def _q(name: str) -> str:
    """Expand 'cbc:ID' / 'cac:Party' into Clark notation."""
    prefix, local = name.split(":", 1)
    ns = {"cbc": CBC_NS, "cac": CAC_NS}[prefix]
    return "{%s}%s" % (ns, local)


def _sub(parent, tag, text=None, **attrs):
    element = ET.SubElement(parent, _q(tag))
    for key, value in attrs.items():
        element.set(key, str(value))
    if text is not None:
        element.text = str(text)
    return element


def _dec(value) -> Decimal:
    """Coerce anything numeric (including Odoo's float monetary fields) to Decimal.

    ``float + Decimal`` raises TypeError, so every incoming value goes through
    ``str()`` first. This is the bug that only appears once real Odoo records
    are passed in, not hand-written test dicts.
    """
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError) as exc:
        raise UblError("Invalid monetary value: %r" % (value,)) from exc


def money(value) -> str:
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, TypeError) as exc:
        raise UblError("Invalid monetary value: %r" % (value,)) from exc
    return str(amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def _require(mapping, key, where):
    value = mapping.get(key)
    if value in (None, ""):
        raise UblError("Missing %s.%s" % (where, key))
    return value


def _party(parent, tag, party, role):
    wrapper = _sub(parent, tag)
    node = _sub(wrapper, "cac:Party")

    if party.get("crn"):
        ident = _sub(node, "cac:PartyIdentification")
        _sub(ident, "cbc:ID", party["crn"], schemeID="CRN")

    address = _sub(node, "cac:PostalAddress")
    _sub(address, "cbc:StreetName", party.get("street") or party.get("name"))
    if party.get("building"):
        _sub(address, "cbc:BuildingNumber", party["building"])
    if party.get("additional"):
        _sub(address, "cbc:PlotIdentification", party["additional"])
    _sub(address, "cbc:CityName", party.get("city") or "-")
    if party.get("postal"):
        _sub(address, "cbc:PostalZone", party["postal"])
    country = _sub(address, "cac:Country")
    _sub(country, "cbc:IdentificationCode", party.get("country") or "SA")

    tax_scheme = _sub(node, "cac:PartyTaxScheme")
    _sub(tax_scheme, "cbc:CompanyID", party.get("vat") or "")
    scheme = _sub(tax_scheme, "cac:TaxScheme")
    _sub(scheme, "cbc:ID", "VAT")

    legal = _sub(node, "cac:PartyLegalEntity")
    _sub(legal, "cbc:RegistrationName", _require(party, "name", role))
    return node


def build_invoice(data: dict) -> str:
    """Return a UBL 2.1 Invoice XML string for the given invoice data."""
    invoice_type = data.get("invoice_type") or "standard"
    if invoice_type not in INVOICE_TYPE_CODES:
        raise UblError("Unknown invoice_type: %r" % (invoice_type,))

    lines = data.get("lines") or []
    if not lines:
        raise UblError("An invoice needs at least one line.")

    currency = data.get("currency") or "SAR"
    tax_currency = data.get("tax_currency") or currency
    issue_date = data.get("issue_date")
    if isinstance(issue_date, date):
        issue_date = issue_date.isoformat()
    if not issue_date:
        raise UblError("Missing issue_date.")

    root = ET.Element("{%s}Invoice" % UBL_NS)

    _sub(root, "cbc:ProfileID", "reporting:1.0")
    _sub(root, "cbc:ID", _require(data, "invoice_id", "invoice"))
    _sub(root, "cbc:UUID", _require(data, "uuid", "invoice"))
    _sub(root, "cbc:IssueDate", issue_date)
    _sub(root, "cbc:IssueTime", data.get("issue_time") or "00:00:00")
    _sub(
        root,
        "cbc:InvoiceTypeCode",
        "388",
        name=INVOICE_TYPE_CODES[invoice_type],
    )
    _sub(root, "cbc:DocumentCurrencyCode", currency)
    _sub(root, "cbc:TaxCurrencyCode", tax_currency)

    icv = _sub(root, "cac:AdditionalDocumentReference")
    _sub(icv, "cbc:ID", "ICV")
    _sub(icv, "cbc:UUID", data.get("icv", "1"))

    pih = _sub(root, "cac:AdditionalDocumentReference")
    _sub(pih, "cbc:ID", "PIH")
    attachment = _sub(pih, "cac:Attachment")
    _sub(
        attachment,
        "cbc:EmbeddedDocumentBinaryObject",
        data.get("pih") or DEFAULT_PIH,
        mimeCode="text/plain",
    )

    if data.get("qr"):
        qr_ref = _sub(root, "cac:AdditionalDocumentReference")
        _sub(qr_ref, "cbc:ID", "QR")
        qr_attachment = _sub(qr_ref, "cac:Attachment")
        _sub(
            qr_attachment,
            "cbc:EmbeddedDocumentBinaryObject",
            data["qr"],
            mimeCode="text/plain",
        )

    _party(root, "cac:AccountingSupplierParty", data.get("seller") or {}, "seller")
    _party(root, "cac:AccountingCustomerParty", data.get("buyer") or {}, "buyer")

    line_extension_total = Decimal("0")
    vat_total = Decimal("0")
    for line in lines:
        line_extension_total += _dec(line["line_extension"])
        vat_total += _dec(line["vat_amount"])

    tax_amount = money(data.get("tax_amount", vat_total))

    tax_total = _sub(root, "cac:TaxTotal")
    _sub(tax_total, "cbc:TaxAmount", tax_amount, currencyID=currency)
    for rate in sorted({money(line.get("vat_rate", 0)) for line in lines}):
        subtotal = _sub(tax_total, "cac:TaxSubtotal")
        _sub(
            subtotal,
            "cbc:TaxableAmount",
            money(data.get("taxable_amount", line_extension_total)),
            currencyID=currency,
        )
        _sub(subtotal, "cbc:TaxAmount", tax_amount, currencyID=currency)
        category = _sub(subtotal, "cac:TaxCategory")
        _sub(category, "cbc:ID", "S")
        _sub(category, "cbc:Percent", rate)
        scheme = _sub(category, "cac:TaxScheme")
        _sub(scheme, "cbc:ID", "VAT")

    if tax_currency != currency:
        tax_total_alt = _sub(root, "cac:TaxTotal")
        _sub(
            tax_total_alt,
            "cbc:TaxAmount",
            money(data.get("tax_amount_tax_currency", tax_amount)),
            currencyID=tax_currency,
        )

    totals = _sub(root, "cac:LegalMonetaryTotal")
    _sub(
        totals,
        "cbc:LineExtensionAmount",
        money(data.get("line_extension_total", line_extension_total)),
        currencyID=currency,
    )
    _sub(
        totals,
        "cbc:TaxExclusiveAmount",
        money(data.get("tax_exclusive_amount", line_extension_total)),
        currencyID=currency,
    )
    _sub(
        totals,
        "cbc:TaxInclusiveAmount",
        money(data.get("tax_inclusive_amount", line_extension_total + vat_total)),
        currencyID=currency,
    )
    _sub(
        totals,
        "cbc:PayableAmount",
        money(
            data.get(
                "payable_amount", data.get("tax_inclusive_amount", line_extension_total + vat_total)
            )
        ),
        currencyID=currency,
    )

    for index, line in enumerate(lines, start=1):
        node = _sub(root, "cac:InvoiceLine")
        _sub(node, "cbc:ID", line.get("id") or str(index))
        _sub(node, "cbc:InvoicedQuantity", line.get("quantity", 1), unitCode=line.get("uom", "PCE"))
        _sub(node, "cbc:LineExtensionAmount", money(line["line_extension"]), currencyID=currency)

        line_tax = _sub(node, "cac:TaxTotal")
        _sub(line_tax, "cbc:TaxAmount", money(line["vat_amount"]), currencyID=currency)
        rounding = line.get("rounding_amount")
        if rounding is None:
            rounding = _dec(line["line_extension"]) + _dec(line["vat_amount"])
        _sub(line_tax, "cbc:RoundingAmount", money(rounding), currencyID=currency)

        item = _sub(node, "cac:Item")
        _sub(item, "cbc:Name", _require(line, "name", "line"))
        item_tax = _sub(item, "cac:ClassifiedTaxCategory")
        _sub(item_tax, "cbc:ID", "S")
        _sub(item_tax, "cbc:Percent", money(line.get("vat_rate", 0)))
        item_scheme = _sub(item_tax, "cac:TaxScheme")
        _sub(item_scheme, "cbc:ID", "VAT")

        price = _sub(node, "cac:Price")
        _sub(price, "cbc:PriceAmount", money(line.get("unit_price", line["line_extension"])), currencyID=currency)

    ET.indent(root, space="  ")
    return ET.tostring(root, encoding="unicode", xml_declaration=True)

# Part of Gulf E-Invoicing. See LICENSE file for full copyright and licensing details.
"""
ZATCA (Saudi Arabia) Phase 1 QR code generator.

Pure Python, no Odoo dependency, so it can be unit-tested without a database.

Specification
-------------
ZATCA's "QR code specification for e-invoices" (Fatoora, Phase 1) defines a
TLV (tag-length-value) byte string, base64-encoded, embedded in the invoice:

    tag 1 -> seller name            (UTF-8)
    tag 2 -> VAT registration no.   (UTF-8, 15 digits for Saudi Arabia)
    tag 3 -> invoice timestamp      (ISO 8601, e.g. 2026-11-17T13:45:00Z)
    tag 4 -> invoice total with VAT (decimal string, e.g. "1150.00")
    tag 5 -> VAT total              (decimal string, e.g. "150.00")

Each field is: one byte tag, one byte length, then the value bytes.
"""

import base64
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

TAG_SELLER_NAME = 1
TAG_VAT_NUMBER = 2
TAG_TIMESTAMP = 3
TAG_TOTAL_WITH_VAT = 4
TAG_VAT_TOTAL = 5

FIELD_NAMES = {
    TAG_SELLER_NAME: "seller_name",
    TAG_VAT_NUMBER: "vat_number",
    TAG_TIMESTAMP: "timestamp",
    TAG_TOTAL_WITH_VAT: "total_with_vat",
    TAG_VAT_TOTAL: "vat_total",
}


class ZatcaQrError(ValueError):
    """Raised when the QR payload cannot be built or read."""


def format_amount(value) -> str:
    """Return a monetary value as a plain 2-decimal string, e.g. '1150.00'."""
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, TypeError) as exc:
        raise ZatcaQrError("Invalid amount: %r" % (value,)) from exc
    return str(amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def format_timestamp(value) -> str:
    """Return 'YYYY-MM-DDTHH:MM:SSZ' in UTC.

    Accepts a ``datetime`` (naive values are treated as UTC), a ``date``
    (midnight UTC) or an ISO 8601 string.
    """
    if isinstance(value, datetime):
        moment = value
    elif isinstance(value, date):
        moment = datetime(value.year, value.month, value.day)
    elif isinstance(value, str):
        text = value.strip().replace("Z", "+00:00")
        try:
            moment = datetime.fromisoformat(text)
        except ValueError as exc:
            raise ZatcaQrError("Invalid timestamp: %r" % (value,)) from exc
    else:
        raise ZatcaQrError("Invalid timestamp: %r" % (value,))

    if moment.tzinfo is not None:
        moment = moment.astimezone(timezone.utc).replace(tzinfo=None)
    return moment.strftime("%Y-%m-%dT%H:%M:%SZ")


def _tag_length_value(tag: int, text: str) -> bytes:
    raw = text.encode("utf-8")
    if len(raw) > 255:
        raise ZatcaQrError(
            "Field %s is %d bytes; the TLV format allows 255."
            % (FIELD_NAMES.get(tag, tag), len(raw))
        )
    return bytes([tag, len(raw)]) + raw


def build_payload(
    seller_name: str,
    vat_number: str,
    timestamp,
    total_with_vat,
    vat_total,
) -> str:
    """Build the base64 TLV string that goes into the invoice QR code."""
    seller = (seller_name or "").strip()
    vat = (vat_number or "").strip()
    if not seller:
        raise ZatcaQrError("Seller name is required.")
    if not vat:
        raise ZatcaQrError("Seller VAT number is required.")

    payload = b"".join(
        [
            _tag_length_value(TAG_SELLER_NAME, seller),
            _tag_length_value(TAG_VAT_NUMBER, vat),
            _tag_length_value(TAG_TIMESTAMP, format_timestamp(timestamp)),
            _tag_length_value(TAG_TOTAL_WITH_VAT, format_amount(total_with_vat)),
            _tag_length_value(TAG_VAT_TOTAL, format_amount(vat_total)),
        ]
    )
    return base64.b64encode(payload).decode("ascii")


def parse_payload(payload: str) -> dict:
    """Decode a base64 TLV payload back into a dict. Used by tests and auditors."""
    if not payload:
        raise ZatcaQrError("Empty payload.")
    try:
        raw = base64.b64decode(payload, validate=True)
    except Exception as exc:  # binascii.Error, ValueError
        raise ZatcaQrError("Payload is not valid base64.") from exc

    result = {}
    index = 0
    while index < len(raw):
        if index + 2 > len(raw):
            raise ZatcaQrError("Truncated TLV header at byte %d." % index)
        tag = raw[index]
        length = raw[index + 1]
        index += 2
        if index + length > len(raw):
            raise ZatcaQrError("Truncated TLV value for tag %d." % tag)
        value = raw[index : index + length]
        index += length
        name = FIELD_NAMES.get(tag)
        if name is None:
            raise ZatcaQrError("Unknown TLV tag %d." % tag)
        result[name] = value.decode("utf-8")

    missing = [name for name in FIELD_NAMES.values() if name not in result]
    if missing:
        raise ZatcaQrError("Missing TLV fields: %s" % ", ".join(sorted(missing)))
    return result


def validate_payload(payload: str) -> list:
    """Return a list of human-readable problems. Empty list means valid."""
    problems = []
    try:
        fields = parse_payload(payload)
    except ZatcaQrError as exc:
        return [str(exc)]

    vat = fields["vat_number"]
    if not (vat.isdigit() and len(vat) == 15):
        problems.append(
            "Saudi VAT numbers are 15 digits; got %r (%d characters)."
            % (vat, len(vat))
        )
    for name in ("total_with_vat", "vat_total"):
        try:
            Decimal(fields[name])
        except InvalidOperation:
            problems.append("Field %s is not a decimal: %r" % (name, fields[name]))
    stamp = fields["timestamp"]
    if not (len(stamp) == 20 and stamp.endswith("Z") and stamp[10] == "T"):
        problems.append("Timestamp must look like 2026-11-17T13:45:00Z; got %r" % stamp)
    return problems


def qr_png_base64(payload: str) -> str:
    """Render the payload as a base64 PNG, for embedding in reports and PDFs."""
    import base64 as _b64

    import qrcode

    image = qrcode.make(payload)
    buffer = _b64.BytesIO()
    image.save(buffer, format="PNG")
    return _b64.b64encode(buffer.getvalue()).decode("ascii")

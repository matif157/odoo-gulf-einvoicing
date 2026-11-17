"""Pure-Python tests for the ZATCA QR payload. No Odoo, no database."""

import base64
import unittest
from datetime import date, datetime, timezone
from decimal import Decimal

import _bootstrap  # noqa: F401  (adds the module folder to sys.path)
from lib.zatca_qr import (
    ZatcaQrError,
    build_payload,
    format_amount,
    format_timestamp,
    parse_payload,
    validate_payload,
)

SELLER = "Al Noor Trading Est."
VAT = "300000000000003"
STAMP = "2026-11-17T13:45:00Z"


class TestAmountFormatting(unittest.TestCase):
    def test_two_decimals(self):
        self.assertEqual(format_amount(1150), "1150.00")

    def test_rounds_half_up(self):
        self.assertEqual(format_amount("1150.005"), "1150.01")

    def test_decimal_input(self):
        self.assertEqual(format_amount(Decimal("0.1") + Decimal("0.2")), "0.30")

    def test_garbage_raises(self):
        with self.assertRaises(ZatcaQrError):
            format_amount("not a number")


class TestTimestamp(unittest.TestCase):
    def test_date_becomes_midnight(self):
        self.assertEqual(format_timestamp(date(2026, 11, 17)), "2026-11-17T00:00:00Z")

    def test_naive_datetime_is_treated_as_utc(self):
        self.assertEqual(
            format_timestamp(datetime(2026, 11, 17, 13, 45, 0)),
            "2026-11-17T13:45:00Z",
        )

    def test_timezone_is_converted_to_utc(self):
        from datetime import timedelta

        riyadh = timezone(timedelta(hours=3))
        self.assertEqual(
            format_timestamp(datetime(2026, 11, 17, 16, 45, 0, tzinfo=riyadh)),
            "2026-11-17T13:45:00Z",
        )

    def test_iso_string_accepted(self):
        self.assertEqual(format_timestamp("2026-11-17T13:45:00Z"), STAMP)


class TestPayload(unittest.TestCase):
    def setUp(self):
        self.payload = build_payload(SELLER, VAT, STAMP, 1150, 150)

    def test_is_valid_base64(self):
        base64.b64decode(self.payload, validate=True)

    def test_round_trip(self):
        fields = parse_payload(self.payload)
        self.assertEqual(fields["seller_name"], SELLER)
        self.assertEqual(fields["vat_number"], VAT)
        self.assertEqual(fields["timestamp"], STAMP)
        self.assertEqual(fields["total_with_vat"], "1150.00")
        self.assertEqual(fields["vat_total"], "150.00")

    def test_tlv_structure_is_ascending(self):
        raw = base64.b64decode(self.payload)
        tags = []
        index = 0
        while index < len(raw):
            tags.append(raw[index])
            index += 2 + raw[index + 1]
        self.assertEqual(tags, [1, 2, 3, 4, 5])

    def test_validator_accepts_good_payload(self):
        self.assertEqual(validate_payload(self.payload), [])

    def test_missing_seller_raises(self):
        with self.assertRaises(ZatcaQrError):
            build_payload("", VAT, STAMP, 1150, 150)

    def test_missing_vat_raises(self):
        with self.assertRaises(ZatcaQrError):
            build_payload(SELLER, "", STAMP, 1150, 150)

    def test_overlong_field_rejected(self):
        with self.assertRaises(ZatcaQrError):
            build_payload("x" * 300, VAT, STAMP, 1150, 150)

    def test_truncated_payload_detected(self):
        raw = base64.b64decode(self.payload)
        broken = base64.b64encode(raw[:-3]).decode()
        with self.assertRaises(ZatcaQrError):
            parse_payload(broken)

    def test_arabic_seller_name_supported(self):
        payload = build_payload("شركة النور", VAT, STAMP, 1150, 150)
        self.assertEqual(parse_payload(payload)["seller_name"], "شركة النور")

    def test_validator_flags_short_vat(self):
        payload = build_payload(SELLER, "300", STAMP, 1150, 150)
        problems = validate_payload(payload)
        self.assertTrue(any("15 digits" in problem for problem in problems))


if __name__ == "__main__":
    unittest.main()

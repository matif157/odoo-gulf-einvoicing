"""Pure-Python tests for the UBL 2.1 builder. No Odoo, no database."""

import unittest
import xml.etree.ElementTree as ET
from datetime import date
from decimal import Decimal

import _bootstrap  # noqa: F401  (adds the module folder to sys.path)
from lib.ubl import CAC_NS, CBC_NS, UBL_NS, UblError, build_invoice

CBC = "{%s}" % CBC_NS
CAC = "{%s}" % CAC_NS

DATA = {
    "invoice_id": "INV/2026/00042",
    "uuid": "8e6f1f5a-4b7c-4c1f-9a1e-0f3b2c7d1e55",
    "issue_date": date(2026, 11, 17),
    "issue_time": "13:45:00",
    "invoice_type": "standard",
    "currency": "SAR",
    "tax_currency": "SAR",
    "icv": "42",
    "qr": "AQ5BbCBOb29yIFRyYWRpbmc=",
    "seller": {
        "name": "Al Noor Trading Est.",
        "vat": "300000000000003",
        "crn": "1010101010",
        "street": "King Fahd Road",
        "building": "1234",
        "city": "Riyadh",
        "postal": "12211",
        "country": "SA",
    },
    "buyer": {
        "name": "Gulf Contracting Co.",
        "vat": "310000000000003",
        "street": "Prince Sultan Street",
        "building": "55",
        "city": "Jeddah",
        "postal": "21432",
        "country": "SA",
    },
    "lines": [
        {
            "id": "1",
            "name": "Steel pipe 2 inch",
            "quantity": 10,
            "unit_price": 100,
            "line_extension": 1000,
            "vat_rate": 15,
            "vat_amount": 150,
        }
    ],
    "tax_amount": 150,
    "tax_inclusive_amount": 1150,
    "payable_amount": 1150,
}


def parse(data=None):
    return ET.fromstring(build_invoice(data or DATA))


class TestStructure(unittest.TestCase):
    def test_root_namespace(self):
        self.assertEqual(parse().tag, "{%s}Invoice" % UBL_NS)

    def test_required_headers(self):
        root = parse()
        self.assertEqual(root.findtext(CBC + "ProfileID"), "reporting:1.0")
        self.assertEqual(root.findtext(CBC + "ID"), "INV/2026/00042")
        self.assertEqual(root.findtext(CBC + "UUID"), DATA["uuid"])
        self.assertEqual(root.findtext(CBC + "IssueDate"), "2026-11-17")
        self.assertEqual(root.findtext(CBC + "IssueTime"), "13:45:00")
        self.assertEqual(root.findtext(CBC + "DocumentCurrencyCode"), "SAR")

    def test_standard_invoice_type_code(self):
        node = parse().find(CBC + "InvoiceTypeCode")
        self.assertEqual(node.text, "388")
        self.assertEqual(node.get("name"), "0100000")

    def test_simplified_invoice_type_code(self):
        data = dict(DATA, invoice_type="simplified")
        node = parse(data).find(CBC + "InvoiceTypeCode")
        self.assertEqual(node.get("name"), "0200000")

    def test_bad_invoice_type_rejected(self):
        with self.assertRaises(UblError):
            build_invoice(dict(DATA, invoice_type="credit_note"))

    def test_no_lines_rejected(self):
        with self.assertRaises(UblError):
            build_invoice(dict(DATA, lines=[]))


class TestReferences(unittest.TestCase):
    def test_icv_and_pih_and_qr_present(self):
        root = parse()
        refs = root.findall(CAC + "AdditionalDocumentReference")
        ids = [ref.findtext(CBC + "ID") for ref in refs]
        self.assertIn("ICV", ids)
        self.assertIn("PIH", ids)
        self.assertIn("QR", ids)

    def test_qr_is_embedded(self):
        root = parse()
        for ref in root.findall(CAC + "AdditionalDocumentReference"):
            if ref.findtext(CBC + "ID") == "QR":
                attachment = ref.find(CAC + "Attachment")
                embedded = attachment.find(CBC + "EmbeddedDocumentBinaryObject")
                self.assertEqual(embedded.text, DATA["qr"])
                self.assertEqual(embedded.get("mimeCode"), "text/plain")
                return
        self.fail("QR reference not found")

    def test_pih_defaults_when_absent(self):
        data = {key: value for key, value in DATA.items() if key != "qr"}
        text = build_invoice(data)
        self.assertIn("PIH", text)


class TestParties(unittest.TestCase):
    def test_supplier_vat_and_name(self):
        root = parse()
        supplier = root.find(CAC + "AccountingSupplierParty")
        tax_scheme = supplier.find(CAC + "Party/" + CAC + "PartyTaxScheme")
        self.assertEqual(tax_scheme.findtext(CBC + "CompanyID"), "300000000000003")
        legal = supplier.find(CAC + "Party/" + CAC + "PartyLegalEntity")
        self.assertEqual(legal.findtext(CBC + "RegistrationName"), "Al Noor Trading Est.")

    def test_supplier_crn(self):
        root = parse()
        ident = root.find(
            CAC + "AccountingSupplierParty/" + CAC + "Party/" + CAC + "PartyIdentification"
        )
        self.assertEqual(ident.findtext(CBC + "ID"), "1010101010")
        self.assertEqual(ident.find(CBC + "ID").get("schemeID"), "CRN")

    def test_buyer_name_required(self):
        buyer = {key: value for key, value in DATA["buyer"].items() if key != "name"}
        with self.assertRaises(UblError):
            build_invoice(dict(DATA, buyer=buyer))


class TestTotals(unittest.TestCase):
    def test_tax_total(self):
        root = parse()
        tax_total = root.find(CAC + "TaxTotal")
        self.assertEqual(tax_total.findtext(CBC + "TaxAmount"), "150.00")

    def test_legal_monetary_total(self):
        root = parse()
        totals = root.find(CAC + "LegalMonetaryTotal")
        self.assertEqual(totals.findtext(CBC + "LineExtensionAmount"), "1000.00")
        self.assertEqual(totals.findtext(CBC + "TaxInclusiveAmount"), "1150.00")
        self.assertEqual(totals.findtext(CBC + "PayableAmount"), "1150.00")

    def test_second_tax_total_when_currencies_differ(self):
        data = dict(DATA, currency="USD", tax_currency="SAR", tax_amount_tax_currency=562.5)
        root = parse(data)
        self.assertEqual(len(root.findall(CAC + "TaxTotal")), 2)

    def test_line_vat(self):
        root = parse()
        line = root.find(CAC + "InvoiceLine")
        self.assertEqual(line.findtext(CBC + "InvoicedQuantity"), "10")
        self.assertEqual(
            line.find(CAC + "TaxTotal").findtext(CBC + "TaxAmount"), "150.00"
        )


class TestOutput(unittest.TestCase):
    def test_declaration_present(self):
        self.assertTrue(build_invoice(DATA).startswith("<?xml"))

    def test_is_well_formed_and_reparses(self):
        text = build_invoice(DATA)
        self.assertGreater(len(text), 1000)
        ET.fromstring(text.split("?>", 1)[1])

    def test_float_inputs_are_supported(self):
        """Odoo's monetary fields are floats; float + Decimal raises TypeError."""
        data = dict(DATA)
        data["lines"] = [
            dict(
                DATA["lines"][0],
                unit_price=100.0,
                line_extension=1000.0,
                vat_amount=150.0,
            )
        ]
        root = parse(data)
        line = root.find(CAC + "InvoiceLine")
        self.assertEqual(line.findtext(CBC + "LineExtensionAmount"), "1000.00")
        self.assertEqual(
            line.find(CAC + "TaxTotal").findtext(CBC + "RoundingAmount"), "1150.00"
        )

    def test_decimal_precision_is_two_places(self):
        data = dict(DATA)
        data["lines"] = [
            dict(DATA["lines"][0], line_extension=Decimal("999.999"), vat_amount=Decimal("150.005"))
        ]
        root = parse(data)
        line = root.find(CAC + "InvoiceLine")
        self.assertEqual(line.findtext(CBC + "LineExtensionAmount"), "1000.00")


if __name__ == "__main__":
    unittest.main()

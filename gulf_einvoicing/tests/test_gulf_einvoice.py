# Part of Gulf E-Invoicing. See LICENSE file for full copyright and licensing details.

import base64
import xml.etree.ElementTree as ET
from datetime import date

from odoo.exceptions import UserError
from odoo.tests.common import TransactionCase

from ..lib import ubl, zatca_qr

CBC = "{%s}" % ubl.CBC_NS
CAC = "{%s}" % ubl.CAC_NS


class TestGulfEinvoice(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env = cls.env(context=dict(cls.env.context, tracking_disable=True))

        cls.company = cls.env.company
        cls.company.write(
            {
                "name": "Al Noor Trading Est.",
                "vat": "300000000000003",
                "gulf_cr_number": "1010101010",
                "gulf_einvoicing_enabled": True,
            }
        )

        cls.income_account = cls.env["account.account"].search(
            [("account_type", "=", "income")], limit=1
        )
        if not cls.income_account:
            cls.income_account = cls.env["account.account"].create(
                {
                    "name": "Test Income",
                    "code": "999999",
                    "account_type": "income",
                }
            )

        cls.journal = cls.env["account.journal"].search(
            [("type", "=", "sale")], limit=1
        )
        if not cls.journal:
            cls.journal = cls.env["account.journal"].create(
                {
                    "name": "Test Sales",
                    "code": "TSAL",
                    "type": "sale",
                    "default_account_id": cls.income_account.id,
                }
            )

        cls.tax_group = cls.env["account.tax.group"].create(
            {
                "name": "VAT",
                "country_id": cls.env.ref("base.sa").id,
            }
        )
        cls.tax = cls.env["account.tax"].create(
            {
                "name": "VAT 15%",
                "amount": 15.0,
                "amount_type": "percent",
                "type_tax_use": "sale",
                "tax_group_id": cls.tax_group.id,
                "country_id": cls.env.ref("base.sa").id,
            }
        )

        cls.partner = cls.env["res.partner"].create(
            {
                "name": "Gulf Contracting Co.",
                "vat": "310000000000003",
                "city": "Jeddah",
                "country_id": cls.env.ref("base.sa").id,
            }
        )
        cls.walk_in = cls.env["res.partner"].create(
            {"name": "Walk-in Customer", "city": "Riyadh"}
        )

    def _invoice(self, partner=None, **kwargs):
        vals = {
            "move_type": "out_invoice",
            "partner_id": (partner or self.partner).id,
            "journal_id": self.journal.id,
            "invoice_date": date(2026, 11, 17),
            "invoice_line_ids": [
                (
                    0,
                    0,
                    {
                        "name": "Steel pipe 2 inch",
                        "quantity": 10,
                        "price_unit": 100.0,
                        "tax_ids": [(6, 0, [self.tax.id])],
                        "account_id": self.income_account.id,
                    },
                )
            ],
        }
        vals.update(kwargs)
        return self.env["account.move"].create(vals)

    # ------------------------------------------------------------------
    # Generation
    # ------------------------------------------------------------------
    def test_generate_sets_state(self):
        invoice = self._invoice()
        self.assertEqual(invoice.gulf_einvoice_state, "none")
        invoice.action_generate_gulf_einvoice()
        self.assertEqual(invoice.gulf_einvoice_state, "generated")
        self.assertTrue(invoice.gulf_einvoice_uuid)
        self.assertTrue(invoice.gulf_einvoice_qr)
        self.assertTrue(invoice.gulf_einvoice_xml)
        self.assertTrue(invoice.gulf_einvoice_filename.endswith(".xml"))

    def test_qr_payload_is_valid(self):
        invoice = self._invoice()
        invoice.action_generate_gulf_einvoice()
        fields = zatca_qr.parse_payload(invoice.gulf_einvoice_qr)
        self.assertEqual(fields["seller_name"], "Al Noor Trading Est.")
        self.assertEqual(fields["vat_number"], "300000000000003")
        self.assertEqual(fields["total_with_vat"], "1150.00")
        self.assertEqual(fields["vat_total"], "150.00")
        self.assertEqual(zatca_qr.validate_payload(invoice.gulf_einvoice_qr), [])

    def test_ubl_is_well_formed(self):
        invoice = self._invoice()
        invoice.action_generate_gulf_einvoice()
        xml_bytes = base64.b64decode(invoice.gulf_einvoice_xml)
        root = ET.fromstring(xml_bytes)
        self.assertTrue(root.tag.endswith("Invoice"))
        self.assertEqual(root.findtext(CBC + "ID"), invoice.name)

    def test_ubl_contains_uuid_and_qr(self):
        invoice = self._invoice()
        invoice.action_generate_gulf_einvoice()
        root = ET.fromstring(base64.b64decode(invoice.gulf_einvoice_xml))
        self.assertEqual(root.findtext(CBC + "UUID"), invoice.gulf_einvoice_uuid)
        found_qr = False
        for ref in root.findall(CAC + "AdditionalDocumentReference"):
            if ref.findtext(CBC + "ID") == "QR":
                found_qr = True
                self.assertEqual(
                    ref.find(CAC + "Attachment").findtext(
                        CBC + "EmbeddedDocumentBinaryObject"
                    ),
                    invoice.gulf_einvoice_qr,
                )
        self.assertTrue(found_qr)

    def test_standard_type_code(self):
        invoice = self._invoice()
        invoice.gulf_einvoice_type = "standard"
        invoice.action_generate_gulf_einvoice()
        root = ET.fromstring(base64.b64decode(invoice.gulf_einvoice_xml))
        self.assertEqual(root.find(CBC + "InvoiceTypeCode").get("name"), "0100000")

    def test_simplified_type_code(self):
        invoice = self._invoice(partner=self.walk_in)
        invoice.gulf_einvoice_type = "simplified"
        invoice.action_generate_gulf_einvoice()
        root = ET.fromstring(base64.b64decode(invoice.gulf_einvoice_xml))
        self.assertEqual(root.find(CBC + "InvoiceTypeCode").get("name"), "0200000")

    def test_regeneration_replaces_values(self):
        invoice = self._invoice()
        invoice.action_generate_gulf_einvoice()
        first_uuid = invoice.gulf_einvoice_uuid
        invoice.action_generate_gulf_einvoice()
        self.assertNotEqual(invoice.gulf_einvoice_uuid, first_uuid)

    def test_reset_clears_everything(self):
        invoice = self._invoice()
        invoice.action_generate_gulf_einvoice()
        invoice.action_reset_gulf_einvoice()
        self.assertEqual(invoice.gulf_einvoice_state, "none")
        self.assertFalse(invoice.gulf_einvoice_qr)
        self.assertFalse(invoice.gulf_einvoice_xml)

    # ------------------------------------------------------------------
    # Guard rails
    # ------------------------------------------------------------------
    def test_missing_company_vat_raises(self):
        self.company.vat = False
        invoice = self._invoice()
        with self.assertRaises(UserError):
            invoice.action_generate_gulf_einvoice()

    def test_vendor_bill_raises(self):
        bill = self.env["account.move"].create(
            {
                "move_type": "in_invoice",
                "partner_id": self.partner.id,
                "invoice_date": date(2026, 11, 17),
                "invoice_line_ids": [
                    (
                        0,
                        0,
                        {
                            "name": "Purchase",
                            "quantity": 1,
                            "price_unit": 100.0,
                            "account_id": self.income_account.id,
                        },
                    )
                ],
            }
        )
        with self.assertRaises(UserError):
            bill.action_generate_gulf_einvoice()

    def test_cancelled_invoice_raises(self):
        invoice = self._invoice()
        invoice.button_cancel()
        with self.assertRaises(UserError):
            invoice.action_generate_gulf_einvoice()

    def test_error_message_lists_all_problems(self):
        self.company.vat = False
        invoice = self._invoice()
        with self.assertRaises(UserError) as caught:
            invoice.action_generate_gulf_einvoice()
        self.assertIn("VAT number", str(caught.exception))

    # ------------------------------------------------------------------
    # Onchange
    # ------------------------------------------------------------------
    def test_onchange_sets_simplified_for_walk_in(self):
        invoice = self.env["account.move"].new({"move_type": "out_invoice"})
        invoice.partner_id = self.walk_in
        invoice._onchange_partner_set_einvoice_type()
        self.assertEqual(invoice.gulf_einvoice_type, "simplified")

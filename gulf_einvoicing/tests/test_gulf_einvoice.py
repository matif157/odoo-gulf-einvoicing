# Part of Gulf E-Invoicing. See LICENSE file for full copyright and licensing details.

import base64
import xml.etree.ElementTree as ET

from odoo.addons.account.tests.common import AccountTestInvoicingCommon
from odoo.exceptions import UserError

from ..lib import ubl, zatca_qr

CBC = "{%s}" % ubl.CBC_NS
CAC = "{%s}" % ubl.CAC_NS

SAUDI_VAT = "300000000000003"


class TestGulfEinvoice(AccountTestInvoicingCommon):
    """End-to-end tests through ``account.move``.

    Uses Odoo's own accounting test mixin so a real chart of accounts, journals,
    taxes and payment terms exist. Building those by hand is how test suites
    become unmaintainable.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.company_data["company"]
        # A CI database created with --without-demo has no chart of accounts,
        # which means no journals, no taxes and no receivable account. Load the
        # Saudi chart so the tests run against the same accounting model a real
        # ZATCA customer uses.
        if not cls.company.chart_template:
            cls.env["account.chart.template"].try_loading(
                "sa", cls.company, install_demo=False
            )
            cls.company_data = cls.collect_company_accounting_data(cls.company)
        cls.company.write(
            {
                "vat": SAUDI_VAT,
                "gulf_cr_number": "1010101010",
                "gulf_einvoicing_enabled": True,
            }
        )
        cls.walk_in = cls.env["res.partner"].create(
            {"name": "Walk-in Customer", "city": "Riyadh"}
        )
        cls.business_customer = cls.env["res.partner"].create(
            {
                "name": "Gulf Contracting Co.",
                "vat": "310000000000003",
                "city": "Jeddah",
            }
        )

    # ------------------------------------------------------------------
    # Fixtures
    # ------------------------------------------------------------------
    def _invoice(self, partner=None, **kwargs):
        return self._create_invoice_one_line(
            price_unit=1000.0,
            tax_ids=self.company_data["default_tax_sale"],
            partner_id=partner or self.business_customer,
            invoice_date="2026-11-17",
            **kwargs,
        )

    def _xml_root(self, invoice):
        return ET.fromstring(base64.b64decode(invoice.gulf_einvoice_xml))

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

    def test_qr_payload_matches_invoice(self):
        invoice = self._invoice()
        invoice.action_generate_gulf_einvoice()
        fields = zatca_qr.parse_payload(invoice.gulf_einvoice_qr)
        self.assertEqual(fields["seller_name"], self.company.name)
        self.assertEqual(fields["vat_number"], SAUDI_VAT)
        self.assertEqual(
            fields["total_with_vat"], zatca_qr.format_amount(invoice.amount_total)
        )
        self.assertEqual(fields["vat_total"], zatca_qr.format_amount(invoice.amount_tax))

    def test_qr_passes_own_validator(self):
        invoice = self._invoice()
        invoice.action_generate_gulf_einvoice()
        self.assertEqual(zatca_qr.validate_payload(invoice.gulf_einvoice_qr), [])

    def test_ubl_is_well_formed(self):
        invoice = self._invoice()
        invoice.action_generate_gulf_einvoice()
        root = self._xml_root(invoice)
        self.assertTrue(root.tag.endswith("Invoice"))
        self.assertEqual(root.findtext(CBC + "ID"), invoice.name)

    def test_ubl_uuid_matches_record(self):
        invoice = self._invoice()
        invoice.action_generate_gulf_einvoice()
        root = self._xml_root(invoice)
        self.assertEqual(root.findtext(CBC + "UUID"), invoice.gulf_einvoice_uuid)

    def test_ubl_embeds_the_same_qr(self):
        invoice = self._invoice()
        invoice.action_generate_gulf_einvoice()
        root = self._xml_root(invoice)
        found = False
        for ref in root.findall(CAC + "AdditionalDocumentReference"):
            if ref.findtext(CBC + "ID") == "QR":
                found = True
                value = ref.find(CAC + "Attachment").findtext(
                    CBC + "EmbeddedDocumentBinaryObject"
                )
                self.assertEqual(value, invoice.gulf_einvoice_qr)
        self.assertTrue(found, "QR reference missing from the UBL document")

    def test_standard_type_code(self):
        invoice = self._invoice()
        invoice.gulf_einvoice_type = "standard"
        invoice.action_generate_gulf_einvoice()
        root = self._xml_root(invoice)
        self.assertEqual(root.find(CBC + "InvoiceTypeCode").get("name"), "0100000")

    def test_simplified_type_code(self):
        invoice = self._invoice(partner=self.walk_in)
        invoice.gulf_einvoice_type = "simplified"
        invoice.action_generate_gulf_einvoice()
        root = self._xml_root(invoice)
        self.assertEqual(root.find(CBC + "InvoiceTypeCode").get("name"), "0200000")

    def test_regeneration_changes_uuid(self):
        invoice = self._invoice()
        invoice.action_generate_gulf_einvoice()
        first = invoice.gulf_einvoice_uuid
        invoice.action_generate_gulf_einvoice()
        self.assertNotEqual(invoice.gulf_einvoice_uuid, first)

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
        bill = self._create_invoice_one_line(
            price_unit=100.0,
            partner_id=self.business_customer,
            move_type="in_invoice",
            invoice_date="2026-11-17",
        )
        with self.assertRaises(UserError):
            bill.action_generate_gulf_einvoice()

    def test_cancelled_invoice_raises(self):
        invoice = self._invoice()
        invoice.button_cancel()
        with self.assertRaises(UserError):
            invoice.action_generate_gulf_einvoice()

    def test_error_message_names_the_missing_field(self):
        self.company.vat = False
        invoice = self._invoice()
        with self.assertRaises(UserError) as caught:
            invoice.action_generate_gulf_einvoice()
        self.assertIn("VAT number", str(caught.exception))

    # ------------------------------------------------------------------
    # Onchange
    # ------------------------------------------------------------------
    def test_onchange_uses_standard_for_business_customer(self):
        invoice = self._invoice()
        invoice._onchange_partner_set_einvoice_type()
        self.assertEqual(invoice.gulf_einvoice_type, "standard")

    def test_onchange_uses_simplified_for_walk_in(self):
        invoice = self._invoice(partner=self.walk_in)
        invoice._onchange_partner_set_einvoice_type()
        self.assertEqual(invoice.gulf_einvoice_type, "simplified")

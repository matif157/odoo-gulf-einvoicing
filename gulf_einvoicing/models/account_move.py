# Part of Gulf E-Invoicing. See LICENSE file for full copyright and licensing details.

import base64
import re
import uuid

from odoo import _, api, fields, models
from odoo.exceptions import UserError

from ..lib import ubl, zatca_qr


class AccountMove(models.Model):
    _inherit = "account.move"

    gulf_einvoice_type = fields.Selection(
        selection=[
            ("standard", "Standard Tax Invoice"),
            ("simplified", "Simplified Tax Invoice"),
        ],
        string="E-Invoice Type",
        default="standard",
        required=True,
        copy=False,
        help="Standard invoices are B2B (0100000). Simplified invoices are B2C (0200000).",
    )
    gulf_einvoice_state = fields.Selection(
        selection=[
            ("none", "Not Generated"),
            ("generated", "Generated"),
        ],
        string="E-Invoice Status",
        default="none",
        required=True,
        copy=False,
        readonly=True,
    )
    gulf_einvoice_qr = fields.Text(
        string="ZATCA QR Payload",
        readonly=True,
        copy=False,
    )
    gulf_einvoice_uuid = fields.Char(
        string="Invoice UUID",
        readonly=True,
        copy=False,
    )
    gulf_einvoice_xml = fields.Binary(
        string="UBL 2.1 XML",
        readonly=True,
        copy=False,
        attachment=True,
    )
    gulf_einvoice_filename = fields.Char(
        string="XML Filename",
        readonly=True,
        copy=False,
    )
    gulf_einvoice_generated_on = fields.Datetime(
        string="Generated On",
        readonly=True,
        copy=False,
    )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _gulf_company(self):
        self.ensure_one()
        return self.company_id or self.env.company

    def _gulf_issue_date(self):
        self.ensure_one()
        return self.invoice_date or fields.Date.context_today(self)

    def _gulf_line_vat_rate(self, line):
        """Return the VAT percentage on a line as a Decimal-friendly string."""
        rates = [tax.amount for tax in line.tax_ids if tax.amount_type == "percent"]
        return sum(rates) if rates else 0.0

    def _gulf_check_ready(self):
        """Raise a single, complete error listing everything that is missing."""
        self.ensure_one()
        company = self._gulf_company()
        problems = []

        if self.move_type != "out_invoice":
            problems.append(_("Only customer invoices can be e-invoiced."))
        if self.state == "cancel":
            problems.append(_("A cancelled invoice cannot be e-invoiced."))
        if not self.invoice_line_ids:
            problems.append(_("The invoice has no lines."))
        if not company.name:
            problems.append(_("The company name is required for the QR code."))
        if not company.vat:
            problems.append(_("The company VAT number is required for the QR code."))
        if not self.partner_id.name:
            problems.append(_("The customer name is required for the UBL document."))

        if problems:
            raise UserError(
                _("This invoice cannot be e-invoiced yet:\n- %s", "\n- ".join(problems))
            )
        return True

    # ------------------------------------------------------------------
    # Generation
    # ------------------------------------------------------------------
    def _gulf_qr_payload(self):
        self.ensure_one()
        company = self._gulf_company()
        return zatca_qr.build_payload(
            seller_name=company.name,
            vat_number=company.vat,
            timestamp=fields.Datetime.now(),
            total_with_vat=abs(self.amount_total),
            vat_total=abs(self.amount_tax),
        )

    def _gulf_party_values(self, partner, fallback_name=None):
        country = partner.country_id.code or "SA"
        return {
            "name": partner.name or fallback_name or "",
            "vat": partner.vat or "",
            # Odoo 20 removed res.partner.company_registry; keep this defensive
            # so the same file runs on 19 and 20.
            "crn": getattr(partner, "company_registry", False) or "",
            "street": partner.street or partner.name or "",
            "building": getattr(partner, "street_number", False) or "0000",
            "additional": partner.street2 or "",
            "city": partner.city or "",
            "postal": partner.zip or "",
            "country": country,
        }

    def _gulf_ubl_data(self, payload, invoice_uuid):
        self.ensure_one()
        company = self._gulf_company()
        currency = self.currency_id.name or company.currency_id.name

        lines = []
        for line in self.invoice_line_ids.filtered(
            lambda move_line: move_line.display_type == "product"
        ):
            vat_rate = self._gulf_line_vat_rate(line)
            vat_amount = line.price_total - line.price_subtotal
            lines.append(
                {
                    "id": str(len(lines) + 1),
                    "name": line.name or line.product_id.display_name or "Item",
                    "quantity": line.quantity,
                    "uom": (line.product_uom_id.name or "PCE")[:3].upper(),
                    "unit_price": line.price_unit,
                    "line_extension": line.price_subtotal,
                    "vat_rate": vat_rate,
                    "vat_amount": vat_amount,
                    "rounding_amount": line.price_total,
                }
            )

        seller = self._gulf_party_values(company.partner_id, fallback_name=company.name)
        seller["name"] = company.name
        seller["vat"] = company.vat
        seller["crn"] = company.gulf_cr_number or company.company_registry or ""

        return {
            # A draft invoice has no number yet; ZATCA needs a value in cbc:ID,
            # so fall back to a placeholder that is regenerated once posted.
            "invoice_id": self.name or ("DRAFT/%s" % self.id),
            "uuid": invoice_uuid,
            "issue_date": self._gulf_issue_date(),
            "issue_time": fields.Datetime.now().strftime("%H:%M:%S"),
            "invoice_type": self.gulf_einvoice_type,
            "currency": currency,
            "tax_currency": company.currency_id.name or currency,
            "icv": str(self.id),
            "qr": payload,
            "seller": seller,
            "buyer": self._gulf_party_values(self.partner_id),
            "lines": lines,
            "tax_amount": abs(self.amount_tax),
            "tax_inclusive_amount": abs(self.amount_total),
            "payable_amount": abs(self.amount_total),
        }

    def action_generate_gulf_einvoice(self):
        """Generate the ZATCA QR payload and the UBL 2.1 XML for these invoices."""
        for move in self:
            move._gulf_check_ready()
            invoice_uuid = str(uuid.uuid4())
            payload = move._gulf_qr_payload()
            xml_text = ubl.build_invoice(move._gulf_ubl_data(payload, invoice_uuid))
            safe_name = re.sub(r"[^A-Za-z0-9._-]+", "-", move.name or "invoice")
            move.write(
                {
                    "gulf_einvoice_uuid": invoice_uuid,
                    "gulf_einvoice_qr": payload,
                    "gulf_einvoice_xml": base64.b64encode(xml_text.encode("utf-8")),
                    "gulf_einvoice_filename": "%s.xml" % safe_name,
                    "gulf_einvoice_generated_on": fields.Datetime.now(),
                    "gulf_einvoice_state": "generated",
                }
            )
            move.message_post(
                body=_("Gulf e-invoice generated (ZATCA QR + UBL 2.1).")
            )
        return True

    def action_reset_gulf_einvoice(self):
        for move in self:
            move.write(
                {
                    "gulf_einvoice_uuid": False,
                    "gulf_einvoice_qr": False,
                    "gulf_einvoice_xml": False,
                    "gulf_einvoice_filename": False,
                    "gulf_einvoice_generated_on": False,
                    "gulf_einvoice_state": "none",
                }
            )
        return True

    @api.onchange("partner_id")
    def _onchange_partner_set_einvoice_type(self):
        for move in self:
            if move.partner_id.vat:
                move.gulf_einvoice_type = "standard"
            elif move.partner_id:
                move.gulf_einvoice_type = "simplified"

# Part of Gulf E-Invoicing. See LICENSE file for full copyright and licensing details.

from odoo import fields, models


class ResCompany(models.Model):
    _inherit = "res.company"

    gulf_einvoicing_enabled = fields.Boolean(
        string="Gulf E-Invoicing",
        help="Enable ZATCA / Gulf e-invoice generation for invoices of this company.",
    )
    gulf_einvoicing_country = fields.Selection(
        selection=[
            ("sa", "Saudi Arabia (ZATCA)"),
            ("ae", "United Arab Emirates (PINT AE) - planned"),
        ],
        string="E-Invoicing Country",
        default="sa",
        required=True,
    )
    gulf_cr_number = fields.Char(
        string="Commercial Registration No.",
        help="Seller CRN written into the UBL PartyIdentification element.",
    )


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    gulf_einvoicing_enabled = fields.Boolean(
        related="company_id.gulf_einvoicing_enabled",
        readonly=False,
    )
    gulf_einvoicing_country = fields.Selection(
        related="company_id.gulf_einvoicing_country",
        readonly=False,
    )
    gulf_cr_number = fields.Char(
        related="company_id.gulf_cr_number",
        readonly=False,
    )

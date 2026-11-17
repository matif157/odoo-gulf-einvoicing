"""Pure-Python helpers: ZATCA QR payload and UBL 2.1 document builder.

Kept free of Odoo imports so the compliance logic can be tested with plain
``python -m unittest`` and reused outside Odoo if ever needed.
"""

from . import ubl, zatca_qr

__all__ = ["ubl", "zatca_qr"]

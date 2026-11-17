"""Import bootstrap so the pure-Python library is testable without Odoo.

``gulf_einvoicing/__init__.py`` imports Odoo models, which cannot be imported
outside an Odoo runtime. Adding the package folder itself to ``sys.path`` lets
the tests import the ``lib`` package directly.
"""

import pathlib
import sys

MODULE_ROOT = pathlib.Path(__file__).resolve().parents[1] / "gulf_einvoicing"
if str(MODULE_ROOT) not in sys.path:
    sys.path.insert(0, str(MODULE_ROOT))

# Copyright 2026 Core Odoo contributors
# SPDX-License-Identifier: LGPL-3.0

{
    "name": "Smoke Test",
    "summary": "Disposable E2E module extending res.partner with a nickname",
    "version": "20.0.1.0.0",
    "category": "Uncategorized",
    "license": "LGPL-3",
    "author": "Core Odoo",
    "website": "https://core-odoo.local",
    "depends": ["base"],
    "data": [
        "security/ir.access.csv",
        "views/res_partner_views.xml",
    ],
    "installable": True,
    "application": False,
}

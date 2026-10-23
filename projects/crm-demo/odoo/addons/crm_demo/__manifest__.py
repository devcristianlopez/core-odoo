# Copyright 2026 Core Odoo contributors
# SPDX-License-Identifier: LGPL-3.0
{
    "name": "CRM Demo",
    "summary": "Small CRM demo with leads and a simple pipeline",
    "version": "20.0.1.0.0",
    "category": "Sales",
    "license": "LGPL-3",
    "author": "Core Odoo",
    "website": "https://core-odoo.local",
    "depends": ["base"],
    "data": [
        "security/ir.access.csv",
        "views/crm_lead_views.xml",
    ],
    "installable": True,
    "application": True,
}

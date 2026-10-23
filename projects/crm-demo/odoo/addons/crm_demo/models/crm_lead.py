# Copyright 2026 Core Odoo contributors
# SPDX-License-Identifier: LGPL-3.0
from odoo import fields, models


class CrmLead(models.Model):
    _name = "crm.demo.lead"
    _description = "CRM Demo Lead"
    _order = "create_date desc"

    name = fields.Char(required=True)
    contact_name = fields.Char()
    email = fields.Char()
    phone = fields.Char()
    stage = fields.Selection(
        selection=[
            ("new", "New"),
            ("contacted", "Contacted"),
            ("proposal", "Proposal"),
            ("won", "Won"),
            ("lost", "Lost"),
        ],
        default="new",
        required=True,
    )
    expected_revenue = fields.Float(digits=(12, 2))
    notes = fields.Text()

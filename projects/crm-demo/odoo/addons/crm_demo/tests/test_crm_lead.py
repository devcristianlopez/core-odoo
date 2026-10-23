# Copyright 2026 Core Odoo contributors
# SPDX-License-Identifier: LGPL-3.0
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestCrmLead(TransactionCase):
    def test_create_lead(self):
        lead = self.env["crm.demo.lead"].create(
            {
                "name": "Acme expansion",
                "contact_name": "Ada Lovelace",
                "email": "ada@example.com",
                "stage": "contacted",
                "expected_revenue": 1200.0,
            }
        )
        self.assertEqual(lead.stage, "contacted")
        self.assertEqual(lead.contact_name, "Ada Lovelace")
        self.assertEqual(lead.expected_revenue, 1200.0)

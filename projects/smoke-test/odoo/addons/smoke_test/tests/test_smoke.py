# Copyright 2026 Core Odoo contributors
# SPDX-License-Identifier: LGPL-3.0

from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged("post_install", "-at_install")
class TestSmokePartner(TransactionCase):
    def test_partner_nickname(self):
        partner = self.env["res.partner"].create(
            {
                "name": "Smoke Test Partner",
                "nickname": "smokey",
            }
        )

        self.assertEqual(partner.name, "Smoke Test Partner")
        self.assertEqual(partner.nickname, "smokey")
        self.assertTrue(partner.id)

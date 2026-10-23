# Copyright 2026 Core Odoo contributors
# SPDX-License-Identifier: LGPL-3.0

from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged("post_install", "-at_install")
class TestExampleModel(TransactionCase):
    def test_create_example(self):
        record = self.env["__MODULE__.example"].create({"name": "Example"})

        self.assertEqual(record.name, "Example")
        self.assertTrue(record.active)

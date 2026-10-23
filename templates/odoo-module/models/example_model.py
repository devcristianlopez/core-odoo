# Copyright 2026 Core Odoo contributors
# SPDX-License-Identifier: LGPL-3.0

from odoo import fields, models


class ExampleModel(models.Model):
    _name = "__MODULE__.example"
    _description = "__MODULE_TITLE__ example record"

    name = fields.Char(required=True, translate=True)
    description = fields.Text()
    active = fields.Boolean(default=True)

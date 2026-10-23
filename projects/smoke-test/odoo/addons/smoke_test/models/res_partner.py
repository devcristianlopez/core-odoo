# Copyright 2026 Core Odoo contributors
# SPDX-License-Identifier: LGPL-3.0

from odoo import fields, models


class ResPartner(models.Model):
    _inherit = "res.partner"

    nickname = fields.Char(string="Nickname", index=True)

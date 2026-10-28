# Executed by `odoo shell` after the database is initialised.
import os

# Creates a least-privilege gateway user and a persistent JSON-2 API key.
bot = env["res.users"].search([("login", "=", "core_gateway")], limit=1)
if not bot:
    bot = env["res.users"].with_context(no_reset_password=True).create(
        {
            "name": "Core Gateway",
            "login": "core_gateway",
            "group_ids": [(6, 0, [env.ref("base.group_user").id, env.ref("base.group_partner_manager").id])],
        }
    )
else:
    bot.write(
        {
            "group_ids": [
                (4, env.ref("base.group_user").id),
                (4, env.ref("base.group_partner_manager").id),
            ]
        }
    )
# Email and report links must point at the environment's public URL; the
# gateway logs in through http://odoo:8069 and would otherwise overwrite it.
public_url = os.environ.get("CORE_PUBLIC_URL")
if public_url:
    params = env["ir.config_parameter"].sudo()
    for key, value in (("web.base.url", public_url), ("web.base.url.freeze", "True")):
        record = params.search([("key", "=", key)], limit=1)
        if record:
            record.write({"value": value})
        else:
            params.create({"key": key, "value": value})

keys = env["res.users.apikeys"].with_user(bot).sudo()
keys.search([("name", "=", "core-gateway")]).unlink()
key = keys._generate("rpc", "core-gateway", None)
print(f"CORE_API_KEY={key}")
env.cr.commit()

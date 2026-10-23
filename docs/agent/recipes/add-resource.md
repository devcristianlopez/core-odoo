# Recipe: expose an existing model

1. Inspect fields and ACL:
   ```bash
   core-odoo --json catalog models <project> --stage dev --model res.partner
   ```
2. Add the resource:
   ```bash
   core-odoo generate resource <project> contacts \
     --model res.partner \
     --fields name,email,phone,city \
     --search-fields name,email
   ```
3. Deploy:
   ```bash
   core-odoo deploy <project> --stage dev
   ```
4. Verify the gateway rejects undeclared fields and operations.
5. For authenticated apps, use `auth.mode: jwt` and call `/auth/login`.

# Recipe: add a module

1. Inspect the catalogue:
   ```bash
   core-odoo --json catalog models <project> --stage dev
   ```
2. Check whether an existing model already covers the need.
3. Generate the module:
   ```bash
   core-odoo generate module <project> <module> \
     --title "..." --model <model> --fields "name:char;..."
   ```
4. Add the BFF resource:
   ```bash
   core-odoo generate resource <project> <resource> \
     --model <module>.<model> --fields ...
   ```
5. Write domain tests in `projects/<project>/odoo/addons/<module>/tests/`.
6. Deploy to `dev`, then test through the gateway.
7. Do not expose Odoo directly; the gateway is the only browser-facing API.

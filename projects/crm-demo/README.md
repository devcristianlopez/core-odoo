# CRM Demo

Pequeño CRM de prueba construido sobre Core Odoo.

- **URL dev:** `http://crm-demo-dev.core-odoo.192.168.1.12.nip.io`
- **Login:** `admin` / `admin` (usuario admin de Odoo, solo para pruebas locales)
- **Módulo:** `crm_demo` (`crm.demo.lead`)
- **Recursos BFF:** `leads`, `contacts`
- **Etapas:** `new`, `contacted`, `proposal`, `won`, `lost`

> Este proyecto es un fixture de prueba. No usar `admin/admin` en producción.

## Desarrollo

```bash
core-odoo project create crm-demo --template odoo-module
core-odoo deploy crm-demo dev --modules crm_demo
```

## Borrar

```bash
core-odoo env delete crm-demo dev
core-odoo project delete crm-demo
```

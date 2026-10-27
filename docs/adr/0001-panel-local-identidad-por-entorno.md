# ADR 0001 — Panel local para desarrolladores, identidad de clientes por entorno

- **Estado:** aceptado
- **Fecha:** 2026-10-27
- **Contexto:** Sprint 2

## Contexto

Core Odoo tiene dos superficies con usuarios distintos:

- **Mission Control** (panel): proyectos, entornos, métricas, logs, iteraciones y
  aprobaciones. Es una herramienta de operación, no un producto para clientes.
- **Las apps generadas** (`crm-demo`, cualquier frontend sobre el BFF): su login
  lo valida el gateway contra `/web/session/authenticate` de la Odoo **de ese
  entorno**. Los usuarios finales son `res.users` de esa base.

Hoy el panel guarda sus propios usuarios en la base del orquestador (argon2 +
JWT), con roles `admin`/`operator`/`viewer` y membresía por proyecto. Es una
identidad separada de Odoo.

El roadmap de Sprint 2 listaba "SSO with Odoo accounts" sin diseño. Ese ítem
asumía que panel y apps compartirían identidad, algo que no se corresponde con
el modelo de la factory: cada proyecto tiene su propia base Odoo, así que "la
Odoo" contra la que validar no es única.

## Decisión

1. El panel es **interno y local**: lo usan los desarrolladores del proyecto. No
   se expone a clientes ni se integra con la identidad de las apps.
2. La identidad de los usuarios finales vive en la **Odoo de cada entorno**. Un
   usuario de `prod` no existe en `staging` ni en `dev`.
3. **No se implementa SSO.** Se descarta "SSO with Odoo accounts" y se
   reemplaza por autoservicio de contraseña y sesiones para el panel.
4. El router de Traefik del panel se limita a **redes privadas** mediante
   `IPAllowList` (`CORE_PANEL_ALLOWED_CIDRS`). Publicarlo es una decisión
   explícita, no el comportamiento por defecto.

## Consecuencias

- Los roles del panel (`admin`/`operator`/`viewer`) y la membresía por proyecto
  siguen siendo la fuente de autorización; no dependen de grupos de Odoo.
- La provisión de usuarios de una app es **por entorno**. Promover a `prod` con
  un clonado exige **neutralizar** los usuarios y datos de prueba del origen.
- Hasta que exista autoservicio, un `admin` mantiene las credenciales del panel
  (`PATCH /users/{username}`).
- El acceso remoto se habilita agregando rangos a `CORE_PANEL_ALLOWED_CIDRS`;
  con el perfil `tunnel` (cloudflared) el allowlist no filtra, porque Traefik ve
  la IP del túnel.
- Si más adelante hacen falta MFA o varios paneles, la decisión a revisar es un
  IdP OIDC central, no la identidad de una Odoo concreta.

## Alternativas descartadas

- **Panel validando contra una Odoo canónica:** requiere elegir una instancia
  como fuente de identidad y deja al resto de proyectos fuera.
- **OIDC/OAuth2 central (Authentik/Keycloak):** técnicamente correcto para SSO
  real, pero no hay necesidad mientras el panel sea interno y de un solo equipo.
- **LDAP:** Odoo 20 no lo trae nativo y el panel necesitaría un cliente LDAP.

# site/

Landing pública de Kizuku. Es HTML, CSS y JavaScript sin build: no hay
framework, bundler, npm, fuentes remotas, imágenes remotas ni pedidos externos.
El sitio se puede publicar tal cual en GitHub Pages.

## Archivos

| Archivo | Uso |
|---|---|
| `index.html` | Contenido, estructura y textos ES/EN |
| `styles.css` | Tokens, temas, layout responsive, diagrama y motion |
| `main.js` | Idioma, tema, navegación móvil, copiar, reveal y año |
| `favicon.svg` | Ícono local; se referencia con `<link rel="icon">` |
| `README.md` | Este documento |

## Bilingüe

El español es el idioma por defecto (`<html lang="es" data-lang="es">`). La
traducción vive en el mismo HTML, en pares de spans:

```html
<p class="t">
  <span data-lang="es" lang="es">Texto en español</span>
  <span data-lang="en" lang="en">English text</span>
</p>
```

- `.t` es un grid; los dos spans ocupan la misma celda (`grid-area: 1 / 1`).
- El idioma inactivo se oculta con `visibility: hidden` según
  `html[data-lang="es"]` / `html[data-lang="en"]`. Como sigue ocupando su celda,
  cambiar de idioma no produce saltos de layout.
- Dentro del SVG el grid no existe, así que el texto usa `<tspan>` y el idioma
  inactivo se oculta con `display: none`: con `visibility: hidden` se
  renderizarían los dos idiomas uno al lado del otro y el título se saldría del
  nodo.
- Los bloques de código usan el mismo patrón con `.code-variant` dentro de un
  `code.t`; así los placeholders también se traducen y el botón de copiar toma
  solo la variante activa.
- Los atributos no se pueden duplicar con spans. Para `aria-label`, `title`,
  `placeholder` y `content` se usa el atributo paralelo `data-en-*`:
  `aria-label` (español) + `data-en-aria-label` (inglés). `main.js` guarda el
  valor original y alterna entre ambos. `<title>` usa `data-en` y
  `<meta name="description">` usa `data-en-content`.
- La preferencia se guarda en `localStorage` con la clave `core-odoo-lang`. Un
  script mínimo en el `<head>` la aplica antes del primer paint para evitar el
  flash de idioma.
- Sin JavaScript, el CSS muestra el español por defecto; el idioma guardado
  necesita el script de arranque. El botón ES/EN y los atributos traducidos
  también necesitan JS.

Al agregar contenido: cada texto traducible debe ser un hijo directo de `.t` y
tener exactamente una variante `data-lang="es"` y una `data-lang="en"`, sin
anidar otros `.t` dentro. Los nombres propios, comandos, métricas y modelos de
Odoo no se traducen.

## Tema

- Oscuro por defecto; claro con `[data-theme="light"]`.
- En la primera visita, sin elección guardada, se respeta
  `prefers-color-scheme` mediante un media query. Al tocar el botón se fija
  `data-theme` y se guarda en `localStorage` (`core-odoo-theme`).
- El script del `<head>` restaura el tema antes del primer paint.
- El botón actualiza `aria-label`, `title` y `<meta name="theme-color">`.

## Comportamiento de `main.js`

- Alterna ES/EN, actualiza textos, `aria-label`, `title`, `<title>`, meta
  description y `html[lang]`, y persiste la elección.
- Alterna tema y escucha cambios del sistema solo mientras no haya una elección
  explícita.
- Navegación móvil: `aria-expanded`, cierre por anchor, `Escape` (devuelve el
  foco al botón), click afuera y al cruzar el breakpoint de escritorio.
- Copiar: `navigator.clipboard` con fallback a `document.execCommand("copy")`.
  Feedback visible y en una región `aria-live` durante 1,5 s. Cada botón declara
  `data-copy-target` y `data-copy-kind`.
- Reveal: `IntersectionObserver` solo para elementos debajo del fold; si no hay
  soporte o el usuario pide movimiento reducido, no se oculta nada.
- Diagrama del sistema: al pasar el mouse (o enfocar un nodo con el teclado) se
  muestra un tooltip con el rol de ese nodo. Sigue al cursor, se mantiene dentro
  de la tarjeta y se oculta al salir, con `Escape` o al cambiar de idioma. En
  pantallas táctiles se abre con un toque. Sin JS, las etiquetas del diagrama
  siguen siendo legibles.
- Año del footer.

Todas las consultas al DOM están guardadas con `if`; si se elimina una sección,
el script no lanza errores. No escribe en consola.

## Accesibilidad

- Skip link, landmarks (`header`, `nav`, `main`, `footer`), un solo `h1` y
  jerarquía de encabezados por sección.
- Foco visible (`:focus-visible`), targets de 44 px en mobile y navegación por
  teclado.
- Los SVG decorativos llevan `aria-hidden="true"` y `focusable="false"`.
- El diagrama es un SVG con `role="img"` y `aria-label` traducible. Cada nodo es
  enfocable (`tabindex="0"`) y el tooltip también se abre con el teclado, así que
  la información no depende solo del hover. Las conexiones se dibujan con
  `stroke-dasharray` animado y el orden de lectura va de izquierda a derecha:
  personas y agentes → una petición → operación.
- El recuadro punteado del carril central agrupa el entorno desplegado (frontend,
  gateway, Odoo y PostgreSQL) para que la flecha de deploy del orquestador tenga
  un destino claro; Odoo aparece dos veces porque son dos puertas al mismo
  contenedor: la API JSON-2 del gateway y la UI web de operadores.
- Los conectores se trazan rectos o por los pasillos entre columnas: ningún
  trazo cruza un nodo.
- Los cinco pasos de “Del prompt al entorno” son una lista ordenada real (`ol`),
  así que el lector de pantalla anuncia la secuencia.
- Los pares de idioma llevan `lang`; el inactivo se marca `aria-hidden` al
  cargar el script.
- Contraste objetivo: WCAG AA en texto normal y grande, en ambos temas.

## Performance

- Dos archivos de CSS/JS (`styles.css`, `main.js`), favicon SVG local y cero
  imágenes/fuentes.
- Los bloques de código hacen scroll horizontal dentro de su caja; la página no
  scrollea horizontalmente.
- Las animaciones son CSS; `prefers-reduced-motion: reduce` las desactiva.
- El contenido es legible sin JavaScript.

## Previsualizar

```bash
cd site
python3 -m http.server 8099
# http://localhost:8099/
```

## Publicar en GitHub Pages

El sitio no necesita build. Lo publica `.github/workflows/pages.yml` en cada
push a `main` que toque `site/**` o el propio workflow (y también a mano con
`workflow_dispatch`): sube `site/` como raíz del artefacto con
`actions/upload-pages-artifact` (`path: site`) y lo despliega con
`actions/deploy-pages`.

El repositorio debe tener Pages configurado con Settings → Pages → Build and
deployment → Source: **GitHub Actions**; con el origen en una rama el job de
build falla. El sitio está publicado en
<https://devcristianlopez.github.io/core-odoo/>.

Los links a documentación apuntan al repositorio en GitHub porque `docs/` no
forma parte del artefacto del sitio.

## Verificación

```bash
node --check site/main.js

cd site
python3 -m http.server 8099
curl -sS -o /dev/null -w '%{http_code}\n' http://127.0.0.1:8099/
curl -sS -o /dev/null -w '%{http_code}\n' http://127.0.0.1:8099/styles.css
curl -sS -o /dev/null -w '%{http_code}\n' http://127.0.0.1:8099/main.js
curl -sS -o /dev/null -w '%{http_code}\n' http://127.0.0.1:8099/favicon.svg
```

Además conviene comprobar que no haya IDs duplicados, que todos los `href`/`src`
locales resuelvan y que cada `.t` tenga sus dos variantes de idioma.

## Fuentes de contenido

Los textos se basan en `README.md`, `docs/ARCHITECTURE.md`, `docs/CONTRACT.md`
(secciones 5–10), `docs/OPERATIONS.md`, `docs/INSTALL.md`, `AGENTS.md`,
`docs/agent/*.md`, `skills/`, `opencode.json`, `Makefile` y
`orchestrator/app/providers/docker.py` (límites por stage). Si el código y esta
página difieren, mandan el repositorio y `docs/`.

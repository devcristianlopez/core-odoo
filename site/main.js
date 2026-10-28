/* ==========================================================================
   Core Odoo — landing page behaviour
   Vanilla JS. No dependencies, no external calls, no console output.
   Content stays readable with JS disabled: CSS handles the language stack.
   ========================================================================== */
(function () {
  "use strict";

  var LANG_KEY = "core-odoo-lang";
  var THEME_KEY = "core-odoo-theme";
  var COPY_RESET_MS = 1500;

  var root = document.documentElement;
  var lang = root.getAttribute("data-lang") === "en" ? "en" : "es";

  var mqReduced = window.matchMedia("(prefers-reduced-motion: reduce)");
  var mqSystemLight = window.matchMedia("(prefers-color-scheme: light)");
  var mqDesktop = window.matchMedia("(min-width: 981px)");

  var attrOriginals = new WeakMap();

  var COPY_LABELS = {
    es: {
      copy: "Copiar",
      copied: "Copiado",
      failed: "Error",
      commands: "Copiar comandos",
      command: "Copiar comando",
      text: "Copiar dirección"
    },
    en: {
      copy: "Copy",
      copied: "Copied",
      failed: "Failed",
      commands: "Copy commands",
      command: "Copy command",
      text: "Copy address"
    }
  };

  var titleEl = document.querySelector("title[data-en]");
  var titleEs = titleEl
    ? (titleEl.getAttribute("data-es") || titleEl.textContent)
    : "";
  var titleEn = titleEl ? titleEl.getAttribute("data-en") : "";

  function focusElement(el) {
    if (!el || typeof el.focus !== "function") return;
    try {
      el.focus({ preventScroll: true });
    } catch (error) {
      try {
        el.focus();
      } catch (ignored) {
        /* Nothing to do; the target is not focusable. */
      }
    }
  }

  /* ------------------------------------------------------------------------
     Language
     ------------------------------------------------------------------------ */
  function applyAttributeTranslations() {
    var pairs = [
      ["data-en-aria-label", "aria-label"],
      ["data-en-title", "title"],
      ["data-en-placeholder", "placeholder"],
      ["data-en-content", "content"]
    ];

    document.querySelectorAll(
      "[data-en-aria-label], [data-en-title], [data-en-placeholder], [data-en-content]"
    ).forEach(function (el) {
      var store = attrOriginals.get(el);
      if (!store) {
        store = {};
        attrOriginals.set(el, store);
      }

      pairs.forEach(function (pair) {
        var dataAttr = pair[0];
        var attr = pair[1];
        var translated = el.getAttribute(dataAttr);
        if (translated === null) return;

        if (!Object.prototype.hasOwnProperty.call(store, attr)) {
          if (attr === "content" && el.hasAttribute("data-es-content")) {
            store[attr] = el.getAttribute("data-es-content") || "";
          } else {
            store[attr] = el.getAttribute(attr) || "";
          }
        }

        el.setAttribute(attr, lang === "en" ? translated : store[attr]);
      });
    });
  }

  function updateDocumentMeta() {
    if (titleEl) {
      titleEl.textContent = lang === "en" && titleEn ? titleEn : titleEs;
    }
  }

  function updateLanguageControl() {
    var button = document.getElementById("lang-toggle");
    if (!button) return;

    var label = lang === "es" ? "Cambiar a inglés" : "Switch to Spanish";
    button.setAttribute("aria-label", label);
    button.setAttribute("title", label);
  }

  function resetCopyButton(button) {
    var kindAttribute = button.getAttribute("data-copy-kind");
    var kind = kindAttribute === "commands" || kindAttribute === "text"
      ? kindAttribute
      : "command";
    var text = button.querySelector(".copy-text");

    window.clearTimeout(button._copyTimer);
    button.classList.remove("is-copied");
    button.setAttribute("aria-label", COPY_LABELS[lang][kind]);
    if (text) text.textContent = COPY_LABELS[lang].copy;
  }

  function resetAllCopyButtons() {
    document.querySelectorAll(".copy").forEach(function (button) {
      resetCopyButton(button);
    });
  }

  function updateMenuLabel() {
    var button = document.getElementById("menu-toggle");
    if (!button) return;

    var open = button.getAttribute("aria-expanded") === "true";
    var label;

    if (open) {
      label = lang === "es" ? "Cerrar menú" : "Close menu";
    } else {
      label = lang === "es" ? "Abrir menú" : "Open menu";
    }

    button.setAttribute("aria-label", label);
    button.setAttribute("title", label);
  }

  function setLanguage(nextLang, persist) {
    lang = nextLang === "en" ? "en" : "es";

    root.lang = lang;
    root.setAttribute("data-lang", lang);

    document.querySelectorAll(".t > [data-lang]").forEach(function (el) {
      if (el.getAttribute("data-lang") === lang) {
        el.removeAttribute("aria-hidden");
      } else {
        el.setAttribute("aria-hidden", "true");
      }
    });

    applyAttributeTranslations();
    updateDocumentMeta();
    updateLanguageControl();
    updateMenuLabel();
    updateThemeControl();
    resetAllCopyButtons();

    var status = document.getElementById("copy-status");
    if (status) status.textContent = "";

    if (persist) {
      try {
        localStorage.setItem(LANG_KEY, lang);
      } catch (error) {
        /* Storage unavailable: the choice still applies to this page. */
      }
    }
  }

  /* ------------------------------------------------------------------------
     Theme
     ------------------------------------------------------------------------ */
  function effectiveTheme() {
    var chosen = root.getAttribute("data-theme");
    if (chosen === "light" || chosen === "dark") return chosen;
    return mqSystemLight.matches ? "light" : "dark";
  }

  function updateThemeControl() {
    var theme = effectiveTheme();
    var button = document.getElementById("theme-toggle");
    var label;

    if (theme === "light") {
      label = lang === "es" ? "Activar tema oscuro" : "Switch to dark theme";
    } else {
      label = lang === "es" ? "Activar tema claro" : "Switch to light theme";
    }

    if (button) {
      button.setAttribute("aria-label", label);
      button.setAttribute("title", label);
    }

    var meta = document.getElementById("theme-color");
    if (meta) {
      meta.setAttribute("content", theme === "light" ? "#f6f8fb" : "#0b0f14");
    }
  }

  function toggleTheme() {
    var next = effectiveTheme() === "light" ? "dark" : "light";
    root.setAttribute("data-theme", next);
    updateThemeControl();

    try {
      localStorage.setItem(THEME_KEY, next);
    } catch (error) {
      /* The theme still applies for this page. */
    }
  }

  /* ------------------------------------------------------------------------
     Mobile navigation
     ------------------------------------------------------------------------ */
  function isMenuOpen() {
    var button = document.getElementById("menu-toggle");
    return !!button && button.getAttribute("aria-expanded") === "true";
  }

  function setMenu(open, focusFirstLink) {
    var button = document.getElementById("menu-toggle");
    var header = document.getElementById("site-header");
    var nav = document.getElementById("site-nav");

    if (!button) return;

    button.setAttribute("aria-expanded", open ? "true" : "false");

    if (header) {
      header.setAttribute("data-nav-open", open ? "true" : "false");
    }

    updateMenuLabel();

    if (open && focusFirstLink && nav) {
      var focusFirst = function () {
        if (!isMenuOpen()) return;
        focusElement(nav.querySelector("a"));
      };

      /* Wait for the panel to leave visibility:hidden before moving focus. */
      if (window.requestAnimationFrame) {
        window.requestAnimationFrame(function () {
          window.requestAnimationFrame(focusFirst);
        });
      } else {
        window.setTimeout(focusFirst, 30);
      }
    }
  }

  function closeMenuAndFocusButton() {
    if (!isMenuOpen()) return;

    setMenu(false, false);

    var button = document.getElementById("menu-toggle");
    if (button) button.focus();
  }

  /* ------------------------------------------------------------------------
     Copy to clipboard
     ------------------------------------------------------------------------ */
  function normalizeCode(text) {
    var lines = String(text).replace(/\r\n/g, "\n").split("\n");

    while (lines.length && !lines[0].trim()) lines.shift();
    while (lines.length && !lines[lines.length - 1].trim()) lines.pop();

    var indents = lines.filter(function (line) {
      return line.trim().length > 0;
    }).map(function (line) {
      var match = line.match(/^[ \t]*/);
      return match ? match[0].length : 0;
    });

    var minimum = indents.length ? Math.min.apply(null, indents) : 0;

    return lines.map(function (line) {
      return line.slice(minimum).replace(/[ \t]+$/, "");
    }).join("\n");
  }

  function textForCopy(target) {
    if (!target) return "";

    var variants = target.querySelectorAll(".code-variant");
    if (variants.length) {
      var active = target.querySelector('.code-variant[data-lang="' + lang + '"]');
      return normalizeCode((active || variants[0]).textContent);
    }

    return normalizeCode(target.textContent);
  }

  function legacyCopy(text) {
    var previousFocus = document.activeElement;
    var field = document.createElement("textarea");
    field.value = text;
    field.setAttribute("readonly", "");
    field.style.position = "fixed";
    field.style.top = "-1000px";
    field.style.left = "-1000px";
    field.style.opacity = "0";

    document.body.appendChild(field);

    var copied = false;
    try {
      field.select();
      field.setSelectionRange(0, field.value.length);
      copied = document.execCommand("copy");
    } catch (error) {
      copied = false;
    }

    field.remove();

    focusElement(previousFocus);

    return copied;
  }

  function writeClipboard(text) {
    if (
      navigator.clipboard &&
      typeof navigator.clipboard.writeText === "function" &&
      window.isSecureContext
    ) {
      return navigator.clipboard.writeText(text).then(function () {
        return true;
      }).catch(function () {
        return legacyCopy(text);
      });
    }

    return Promise.resolve(legacyCopy(text));
  }

  function showCopyFeedback(button, copied) {
    var labels = COPY_LABELS[lang];
    var text = button.querySelector(".copy-text");
    var status = document.getElementById("copy-status");
    var feedback = copied ? labels.copied : labels.failed;

    button.classList.toggle("is-copied", copied);
    if (text) text.textContent = feedback;
    if (status) status.textContent = feedback;

    window.clearTimeout(button._copyTimer);
    button._copyTimer = window.setTimeout(function () {
      resetCopyButton(button);
      if (status) status.textContent = "";
    }, COPY_RESET_MS);
  }

  function handleCopy(button) {
    var targetId = button.getAttribute("data-copy-target");
    var target = targetId ? document.getElementById(targetId) : null;
    var text = textForCopy(target);

    if (!text) return;

    Promise.resolve().then(function () {
      return writeClipboard(text);
    }).then(function (copied) {
      showCopyFeedback(button, copied);
    }).catch(function () {
      showCopyFeedback(button, false);
    });
  }

  /* ------------------------------------------------------------------------
     Reveal on scroll
     ------------------------------------------------------------------------ */
  function setupReveal() {
    var elements = document.querySelectorAll(".reveal");
    if (!elements.length) return;

    if (mqReduced.matches || !("IntersectionObserver" in window)) return;

    var observer = new IntersectionObserver(function (entries, currentObserver) {
      entries.forEach(function (entry) {
        if (!entry.isIntersecting) return;
        entry.target.classList.add("is-visible");
        currentObserver.unobserve(entry.target);
      });
    }, {
      rootMargin: "0px 0px -8% 0px",
      threshold: 0.08
    });

    elements.forEach(function (el) {
      var rect = el.getBoundingClientRect();

      if (rect.top > window.innerHeight * 0.92) {
        el.classList.add("will-reveal");
        observer.observe(el);
      }
    });
  }

  /* ------------------------------------------------------------------------
     Wiring
     ------------------------------------------------------------------------ */
  function init() {
    applyAttributeTranslations();
    setLanguage(lang, false);
    updateThemeControl();
    updateMenuLabel();

    var langButton = document.getElementById("lang-toggle");
    if (langButton) {
      langButton.addEventListener("click", function () {
        setLanguage(lang === "es" ? "en" : "es", true);
      });
    }

    var themeButton = document.getElementById("theme-toggle");
    if (themeButton) {
      themeButton.addEventListener("click", toggleTheme);
    }

    var menuButton = document.getElementById("menu-toggle");
    if (menuButton) {
      menuButton.addEventListener("click", function () {
        setMenu(!isMenuOpen(), true);
      });
    }

    var nav = document.getElementById("site-nav");
    if (nav) {
      nav.addEventListener("click", function (event) {
        var link = event.target.closest ? event.target.closest("a") : null;
        if (!link) return;

        var hash = link.getAttribute("href") || "";
        var wasOpen = isMenuOpen();

        if (wasOpen) setMenu(false, false);

        /* Keep keyboard focus inside the section the user just navigated to,
           instead of leaving it on a link that is now visibility:hidden. */
        if (wasOpen && hash.charAt(0) === "#" && hash.length > 1) {
          var target = document.getElementById(hash.slice(1));
          if (target) {
            if (!target.hasAttribute("tabindex")) {
              target.setAttribute("tabindex", "-1");
            }
            var moveFocus = function () {
              focusElement(target);
            };

            if (window.requestAnimationFrame) {
              window.requestAnimationFrame(moveFocus);
            } else {
              window.setTimeout(moveFocus, 0);
            }
          }
        }
      });
    }

    document.addEventListener("keydown", function (event) {
      if (event.key === "Escape" && isMenuOpen()) {
        closeMenuAndFocusButton();
      }
    });

    document.addEventListener("click", function (event) {
      var header = document.getElementById("site-header");
      if (!isMenuOpen() || !header) return;
      if (!header.contains(event.target)) setMenu(false, false);
    });

    var desktopListener = function () {
      if (mqDesktop.matches && isMenuOpen()) setMenu(false, false);
    };

    if (mqDesktop.addEventListener) {
      mqDesktop.addEventListener("change", desktopListener);
    } else if (mqDesktop.addListener) {
      mqDesktop.addListener(desktopListener);
    }

    var systemThemeListener = function () {
      if (!root.getAttribute("data-theme")) {
        updateThemeControl();
      }
    };

    if (mqSystemLight.addEventListener) {
      mqSystemLight.addEventListener("change", systemThemeListener);
    } else if (mqSystemLight.addListener) {
      mqSystemLight.addListener(systemThemeListener);
    }

    document.querySelectorAll(".copy").forEach(function (button) {
      button.addEventListener("click", function () {
        handleCopy(button);
      });
    });

    var year = document.getElementById("year");
    if (year) year.textContent = String(new Date().getFullYear());

    setupReveal();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init, { once: true });
  } else {
    init();
  }
})();

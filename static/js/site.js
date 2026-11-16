/* RLM site behaviour. Progressive enhancement only: every page works without this file.
   Loaded as an external file (CSP: script-src 'self' + nonce; no inline handlers, no eval). */
(function () {
  "use strict";

  // YouTube facade: swap the thumbnail for a privacy-enhanced (nocookie) iframe on click.
  document.addEventListener("click", function (event) {
    var button = event.target.closest("[data-yt]");
    if (!button) return;
    event.preventDefault();
    var id = button.getAttribute("data-yt");
    if (!/^[A-Za-z0-9_-]{11}$/.test(id)) return;
    var iframe = document.createElement("iframe");
    iframe.src = "https://www.youtube-nocookie.com/embed/" + id + "?autoplay=1&rel=0";
    iframe.title = button.getAttribute("data-title") || "YouTube video";
    iframe.allow = "accelerometer; autoplay; encrypted-media; gyroscope; picture-in-picture";
    iframe.allowFullscreen = true;
    iframe.loading = "lazy";
    iframe.referrerPolicy = "strict-origin-when-cross-origin";
    iframe.className = "absolute inset-0 h-full w-full";
    button.replaceWith(iframe);
  });

  // Close the mobile menu (<details>) after choosing a link or pressing Escape.
  var menu = document.getElementById("mobile-menu");
  if (menu) {
    menu.addEventListener("click", function (e) {
      if (e.target.closest("a")) menu.removeAttribute("open");
    });
    document.addEventListener("keydown", function (e) {
      if (e.key === "Escape") menu.removeAttribute("open");
    });
  }

  // Re-render Cloudflare Turnstile widgets that arrive in HTMX-swapped content.
  document.body.addEventListener("htmx:afterSwap", function (event) {
    if (window.turnstile) {
      event.detail.target.querySelectorAll(".cf-turnstile:empty").forEach(function (el) {
        window.turnstile.render(el);
      });
    }
    var focusTarget = event.detail.target.querySelector("[data-focus]");
    if (focusTarget) focusTarget.focus();
  });

  // Consent for (cookieless) analytics. Nothing loads until the visitor agrees.
  var banner = document.getElementById("consent-banner");
  var KEY = "rlm-analytics-consent";
  function readConsent() {
    try { return window.localStorage.getItem(KEY); } catch (e) { return null; }
  }
  function writeConsent(value) {
    try { window.localStorage.setItem(KEY, value); } catch (e) { /* private mode */ }
  }
  function loadAnalytics() {
    var cfg = document.getElementById("analytics-config");
    if (!cfg || !cfg.dataset.src) return;
    var s = document.createElement("script");
    s.src = cfg.dataset.src;
    s.defer = true;
    if (cfg.dataset.provider === "plausible") s.setAttribute("data-domain", cfg.dataset.site);
    if (cfg.dataset.provider === "umami") s.setAttribute("data-website-id", cfg.dataset.site);
    document.head.appendChild(s);
  }
  if (banner) {
    var choice = readConsent();
    if (choice === "yes") loadAnalytics();
    if (!choice) banner.hidden = false;
    banner.addEventListener("click", function (e) {
      var btn = e.target.closest("[data-consent]");
      if (!btn) return;
      var value = btn.getAttribute("data-consent");
      writeConsent(value);
      banner.hidden = true;
      if (value === "yes") loadAnalytics();
    });
    // "Privacy choices" (footer): withdrawing consent must be as easy as giving it.
    document.addEventListener("click", function (e) {
      if (!e.target.closest("[data-consent-reset]")) return;
      try { window.localStorage.removeItem(KEY); } catch (err) { /* private mode */ }
      banner.hidden = false;
      var first = banner.querySelector("[data-consent]");
      if (first) first.focus();
    });
  }
})();

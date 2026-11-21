/* Hero background video: decorative, silent, loaded only when it will not hurt the visitor.
 *
 * Without this script (or when any check fails) the poster image or the theme colour shows, so nothing breaks.
 * The video gets a source only AFTER the page has loaded and been painted, and only when:
 *   - the visitor has not asked for reduced motion,
 *   - Save-Data / data saver is off,
 *   - the connection is not reported as slow (2G/3G or under 1.5 Mbit/s),
 *   - on phones (narrow screens), the connection is reported as fast (4G) - otherwise poster only.
 * A visible button pauses and resumes the loop (WCAG 2.2.2), and videos outside the viewport are paused.
 */
(function () {
  "use strict";

  function connectionAllows() {
    var c = navigator.connection || navigator.mozConnection || navigator.webkitConnection;
    var narrow = window.matchMedia("(max-width: 767px)").matches;
    if (!c) return !narrow; // unknown connection: phones keep the poster (preload="none" also stays)
    if (c.saveData) return false;
    if (/(^|-)(2g|3g)$/.test(c.effectiveType || "")) return false;
    if (typeof c.downlink === "number" && c.downlink > 0 && c.downlink < 1.5) return false;
    if (narrow && c.effectiveType && c.effectiveType !== "4g") return false;
    return true;
  }

  function allowed() {
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return false;
    return connectionAllows();
  }

  function setUp(video) {
    var hero = video.closest("[data-hero-bg]");
    var toggle = hero ? hero.querySelector("[data-hero-video-toggle]") : null;
    var userPaused = false;
    video.querySelectorAll("source[data-src]").forEach(function (source) {
      source.src = source.getAttribute("data-src");
      source.removeAttribute("data-src");
    });
    video.muted = true; // never any sound
    video.load();

    function play() {
      if (userPaused) return;
      var p = video.play();
      if (p && p.catch) p.catch(function () { /* autoplay refused: the poster stays */ });
    }
    video.addEventListener("playing", function () {
      video.classList.add("is-playing");
      if (toggle) toggle.hidden = false;
    });
    video.addEventListener("error", function () { video.remove(); }, true);

    if (toggle) {
      toggle.addEventListener("click", function () {
        userPaused = !video.paused;
        if (userPaused) { video.pause(); } else { play(); }
        toggle.setAttribute("aria-pressed", userPaused ? "true" : "false");
        toggle.textContent = userPaused ? "Play background video" : "Pause background video";
      });
    }
    if ("IntersectionObserver" in window) {
      new IntersectionObserver(function (entries) {
        entries.forEach(function (e) { if (e.isIntersecting) { play(); } else { video.pause(); } });
      }, { threshold: 0.25 }).observe(video);
    } else {
      play();
    }
  }

  function start() {
    if (!allowed()) return;
    document.querySelectorAll("video[data-hero-video]").forEach(setUp);
  }

  // After the first paint and the load event, so the video never delays the page.
  function later() {
    if ("requestIdleCallback" in window) {
      window.requestIdleCallback(start, { timeout: 3000 });
    } else {
      window.setTimeout(start, 1200);
    }
  }
  if (document.readyState === "complete") { later(); } else { window.addEventListener("load", later); }
})();

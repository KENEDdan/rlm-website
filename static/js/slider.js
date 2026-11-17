/* RLM slider: progressive enhancement for templates/includes/slider.html (no dependencies).
   Without this file every slider is still a CSS scroll-snap strip (swipe, scroll, arrow keys).
   Adds: arrow buttons, dots, keyboard keys, mouse drag, hero autoplay (paused on hover/focus/touch, a
   visible pause button, never with prefers-reduced-motion), the photo lightbox and the partner logo strip.
   CSP: external file, no inline handlers, no eval; styles are set only through the CSSOM. */
(function () {
  "use strict";
  if (window.RLMSlider) return;

  var motionQuery = window.matchMedia ? window.matchMedia("(prefers-reduced-motion: reduce)") : null;
  function reducedMotion() { return !!(motionQuery && motionQuery.matches); }
  function each(list, fn) { Array.prototype.forEach.call(list, fn); }

  function Slider(root) {
    var track = root.querySelector("[data-slider-track]");
    var slides = Array.prototype.filter.call(track.children, function (el) { return el.hasAttribute("data-slide"); });
    var controls = root.querySelector("[data-slider-controls]");
    var dotsBox = root.querySelector("[data-slider-dots]");
    var prevBtn = root.querySelector("[data-slider-prev]");
    var nextBtn = root.querySelector("[data-slider-next]");
    var playBtn = root.querySelector("[data-slider-play]");
    var progress = root.querySelector("[data-slider-progress]");
    var status = root.querySelector("[data-slider-status]");
    var thumbs = document.querySelector('[data-slider-thumbs="' + root.id + '"]');
    var delay = parseInt(root.getAttribute("data-autoplay"), 10) || 0;
    var current = 0, last = 0, timer = null, userPaused = false, hovering = false;
    var self = this;

    function offset(i) { return slides[i].offsetLeft - slides[0].offsetLeft; }
    function maxScroll() { return Math.max(0, track.scrollWidth - track.clientWidth); }
    function lastIndex() {
      var max = maxScroll();
      for (var i = 0; i < slides.length; i++) if (offset(i) >= max - 2) return i;
      return slides.length - 1;
    }
    function nearest() {
      var left = track.scrollLeft, best = 0, dist = Infinity;
      if (left >= maxScroll() - 2) return last;
      for (var i = 0; i <= last; i++) {
        var d = Math.abs(offset(i) - left);
        if (d < dist) { dist = d; best = i; }
      }
      return best;
    }

    function setLive(mode) { if (status) status.setAttribute("aria-live", mode); }
    function announce() {
      if (!status) return;
      var slide = slides[current], heading = null;
      ["h1, h2, h3", "figcaption", "img[alt]"].some(function (sel) { heading = slide.querySelector(sel); return heading; });
      var text = heading ? (heading.getAttribute("alt") || heading.textContent || "").trim() : "";
      status.textContent = "Slide " + (current + 1) + " of " + slides.length + (text ? ": " + text : "");
    }

    function render(silent) {
      if (dotsBox) each(dotsBox.children, function (dot, i) {
        if (i === current) dot.setAttribute("aria-current", "true"); else dot.removeAttribute("aria-current");
      });
      if (!delay) {
        if (prevBtn) prevBtn.setAttribute("aria-disabled", String(current === 0));
        if (nextBtn) nextBtn.setAttribute("aria-disabled", String(current >= last));
      }
      if (thumbs) each(thumbs.querySelectorAll("[data-slider-goto]"), function (t) {
        if (+t.getAttribute("data-slider-goto") === current) t.setAttribute("aria-current", "true");
        else t.removeAttribute("aria-current");
      });
      if (!silent) announce();
    }

    function goTo(index, instant, silent) {
      if (delay) index = (index + last + 1) % (last + 1); // the hero wraps around
      index = Math.max(0, Math.min(last, index));
      current = index;
      track.scrollTo({ left: Math.min(offset(index), maxScroll()), behavior: instant || reducedMotion() ? "auto" : "smooth" });
      render(silent);
    }

    function buildDots() {
      if (!dotsBox) return;
      dotsBox.textContent = "";
      for (var i = 0; i <= last; i++) {
        var dot = document.createElement("button");
        dot.type = "button";
        dot.className = "slider-dot";
        dot.setAttribute("aria-label", "Go to slide " + (i + 1));
        dot.setAttribute("data-index", String(i));
        dotsBox.appendChild(dot);
      }
    }

    // Layout is read in measure() and written in apply(), so a page with many sliders is measured in ONE
    // layout pass at start-up instead of one forced reflow per slider (this kept Total Blocking Time low).
    function measure() { last = lastIndex(); }
    function apply(initial) {
      var needed = last > 0;
      if (controls) controls.hidden = !needed;
      root.classList.toggle("is-static", !needed);
      buildDots();
      current = Math.min(current, last);
      if (needed && !(initial && current === 0)) goTo(current, true, true); else render(true);
      syncPlayButton();
    }
    function refresh() { measure(); apply(false); }

    // ------------------------------------------------------------ autoplay (hero only)
    function canPlay() { return delay > 0 && last > 0 && !reducedMotion() && !userPaused && !hovering && !document.hidden; }
    function stop() {
      clearTimeout(timer); timer = null;
      if (progress) progress.classList.remove("is-running");
      setLive("polite");
    }
    function start() {
      stop();
      if (!canPlay()) return;
      setLive("off");
      if (progress) {
        var bar = progress.firstElementChild;
        bar.style.animationDuration = delay + "ms";
        void progress.offsetWidth; // restart the CSS animation
        progress.classList.add("is-running");
      }
      timer = setTimeout(function () { goTo(current + 1); start(); }, delay);
    }
    function syncPlayButton() {
      if (!playBtn) return;
      playBtn.hidden = reducedMotion() || last === 0;
      if (progress) progress.hidden = playBtn.hidden;
      playBtn.setAttribute("aria-label", userPaused ? "Play the slideshow" : "Pause the slideshow");
      playBtn.querySelector("[data-icon-pause]").hidden = userPaused;
      playBtn.querySelector("[data-icon-play]").hidden = !userPaused;
    }
    function pauseByUser() { userPaused = true; syncPlayButton(); stop(); }

    // ------------------------------------------------------------ events
    if (prevBtn) prevBtn.addEventListener("click", function () { if (delay) pauseByUser(); goTo(current - 1); });
    if (nextBtn) nextBtn.addEventListener("click", function () { if (delay) pauseByUser(); goTo(current + 1); });
    if (dotsBox) dotsBox.addEventListener("click", function (e) {
      var dot = e.target.closest("[data-index]");
      if (!dot) return;
      if (delay) pauseByUser();
      goTo(+dot.getAttribute("data-index"));
    });
    if (playBtn) playBtn.addEventListener("click", function () {
      userPaused = !userPaused;
      syncPlayButton();
      if (userPaused) stop(); else { goTo(current + 1); start(); }
    });
    if (thumbs) thumbs.addEventListener("click", function (e) {
      var t = e.target.closest("[data-slider-goto]");
      if (!t) return;
      e.preventDefault();
      goTo(+t.getAttribute("data-slider-goto"));
    });

    root.addEventListener("keydown", function (e) {
      if (e.target.closest("input, textarea, select")) return;
      var map = { ArrowLeft: current - 1, ArrowRight: current + 1, Home: 0, End: last };
      if (!(e.key in map) || e.altKey || e.ctrlKey || e.metaKey) return;
      e.preventDefault();
      if (delay) pauseByUser();
      goTo(map[e.key]);
    });

    var scrollTimer = null;
    track.addEventListener("scroll", function () {
      clearTimeout(scrollTimer);
      scrollTimer = setTimeout(function () {
        if (drag) return;
        var i = nearest();
        if (i !== current) { current = i; render(); }
      }, 80);
    }, { passive: true });

    if (delay) {
      root.addEventListener("mouseenter", function () { hovering = true; stop(); });
      root.addEventListener("mouseleave", function () { hovering = false; start(); });
      // Keyboard focus or a touch means the visitor is reading: stop until they press Play.
      root.addEventListener("focusin", function (e) { if (e.target !== playBtn) pauseByUser(); });
      track.addEventListener("touchstart", pauseByUser, { passive: true });
      document.addEventListener("visibilitychange", function () { if (document.hidden) stop(); else start(); });
      if (motionQuery && motionQuery.addEventListener) {
        motionQuery.addEventListener("change", function () { syncPlayButton(); start(); });
      }
    }

    // Mouse drag (touch and pen already swipe natively).
    var drag = null, suppressClick = false;
    track.addEventListener("pointerdown", function (e) {
      if (e.pointerType !== "mouse" || e.button !== 0 || last === 0) return;
      drag = { x: e.clientX, left: track.scrollLeft, moved: false, id: e.pointerId };
    });
    track.addEventListener("pointermove", function (e) {
      if (!drag) return;
      var dx = e.clientX - drag.x;
      if (!drag.moved && Math.abs(dx) > 6) {
        drag.moved = true;
        root.classList.add("is-dragging");
        try { track.setPointerCapture(drag.id); } catch (err) { /* pointer already gone */ }
      }
      if (drag.moved) track.scrollLeft = drag.left - dx;
    });
    function endDrag(e) {
      if (!drag) return;
      var moved = drag.moved, dx = e.clientX - drag.x;
      drag = null;
      if (!moved) return;
      root.classList.remove("is-dragging");
      suppressClick = true;
      setTimeout(function () { suppressClick = false; }, 0);
      if (delay) pauseByUser();
      var target = nearest();
      if (target === current && Math.abs(dx) > 40) target = current + (dx < 0 ? 1 : -1);
      goTo(target);
    }
    track.addEventListener("pointerup", endDrag);
    track.addEventListener("pointercancel", endDrag);
    track.addEventListener("click", function (e) {
      if (suppressClick) { e.preventDefault(); e.stopPropagation(); }
    }, true);
    track.addEventListener("dragstart", function (e) { e.preventDefault(); });

    var resizeTimer = null;
    window.addEventListener("resize", function () {
      clearTimeout(resizeTimer);
      resizeTimer = setTimeout(refresh, 150);
    });

    self.goTo = goTo;
    self.refresh = refresh;
    self.measure = measure;
    self.apply = apply;
    self.start = start;
    self.current = function () { return current; };
    root.rlmSlider = self;
  }

  // ------------------------------------------------------------ photo lightbox (<dialog>, keyboard-accessible)
  function Lightbox(dialog) {
    var inner = dialog.querySelector("[data-slider]");
    var opener = null;
    if (!inner || typeof dialog.showModal !== "function") return; // links keep opening the full image
    document.addEventListener("click", function (e) {
      var link = e.target.closest("[data-lightbox-open]");
      if (!link || !inner.rlmSlider) return;
      e.preventDefault();
      opener = link;
      dialog.showModal();
      inner.rlmSlider.refresh();
      inner.rlmSlider.goTo(+link.getAttribute("data-lightbox-open"), true);
      var closeBtn = dialog.querySelector("[data-lightbox-close]");
      if (closeBtn) closeBtn.focus();
    });
    // Arrow keys work wherever focus is inside the viewer (e.g. on the Close button).
    dialog.addEventListener("keydown", function (e) {
      if (!inner.rlmSlider || inner.contains(e.target)) return;
      var step = { ArrowLeft: -1, ArrowRight: 1 }[e.key];
      if (!step) return;
      e.preventDefault();
      inner.rlmSlider.goTo(inner.rlmSlider.current() + step);
    });
    dialog.addEventListener("click", function (e) {
      if (e.target === dialog || e.target.closest("[data-lightbox-close]")) dialog.close();
    });
    dialog.addEventListener("close", function () {
      var main = opener && opener.closest("[data-slider]");
      if (main && main.rlmSlider) main.rlmSlider.goTo(inner.rlmSlider.current(), true);
      if (opener) {
        var same = main && main.querySelector('[data-lightbox-open="' + inner.rlmSlider.current() + '"]');
        (same || opener).focus();
      }
    });
  }

  // ------------------------------------------------------------ partner logo strip (slow, pausable)
  function Marquee(box) {
    var list = box.querySelector("[data-marquee-list]");
    var toggle = box.parentNode.querySelector("[data-marquee-toggle]");
    if (!list || reducedMotion() || list.scrollWidth <= box.clientWidth) return; // static row
    var copy = list.cloneNode(true);
    copy.setAttribute("aria-hidden", "true");
    copy.setAttribute("inert", "");
    each(copy.querySelectorAll("a"), function (a) { a.setAttribute("tabindex", "-1"); });
    list.parentNode.appendChild(copy);
    box.classList.add("is-animated");
    if (toggle) {
      toggle.hidden = false;
      toggle.addEventListener("click", function () {
        var paused = box.classList.toggle("is-paused");
        toggle.textContent = paused ? "Play logos" : "Pause logos";
      });
    }
  }

  function init(scope) {
    var roots = Array.prototype.filter.call((scope || document).querySelectorAll("[data-slider]"), function (r) {
      return !r.rlmSlider;
    });
    // Batch: all layout reads first (layout is still clean after the first frame, so they are cheap), then all
    // DOM writes; autoplay starts on the next frame. Hiding the scrollbar (is-ready) does not change widths.
    var sliders = roots.map(function (r) { return new Slider(r); });
    sliders.forEach(function (s) { s.measure(); });
    roots.forEach(function (r) { r.classList.add("is-ready"); });
    sliders.forEach(function (s) { s.apply(true); });
    window.requestAnimationFrame(function () { sliders.forEach(function (s) { s.start(); }); });
  }
  function boot() {
    init();
    each(document.querySelectorAll("[data-lightbox]"), function (d) { new Lightbox(d); });
    // Separate task: the logo strip measures its own width after the sliders' DOM writes.
    window.requestAnimationFrame(function () {
      setTimeout(function () { each(document.querySelectorAll("[data-marquee]"), function (m) { new Marquee(m); }); }, 0);
    });
  }
  // Start after the first frame has been laid out and painted: the page is already usable (scroll-snap) and
  // the enhancement then costs one cheap measurement instead of the page's first full layout.
  window.RLMSlider = { init: init };
  window.requestAnimationFrame(function () { setTimeout(boot, 0); });
})();

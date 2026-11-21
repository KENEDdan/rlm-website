/* Live preview for the hero editor in the staff portal (no inline script; CSP-safe CSSOM only).
 * Mirrors the server's contrast check (core/hero.py): brightest-10% luminance of the photo, blended with the
 * dark overlay, against the chosen text colour; warns below WCAG AA 4.5:1. The server re-checks on save. */
(function () {
  "use strict";
  var form = document.querySelector("[data-hero-form]");
  var box = document.querySelector("[data-hero-preview]");
  if (!form || !box) return;

  var $ = function (name) { return form.querySelector('[name="' + name + '"]'); };
  var img = box.querySelector("[data-preview-img]");
  var shade = box.querySelector("[data-preview-shade]");
  var contrastOut = document.querySelector("[data-preview-contrast]");
  var luminance = { photo: parseFloat(box.dataset.luminance), video: parseFloat(box.dataset.posterLuminance) };
  var sources = { photo: box.dataset.photo || "", video: box.dataset.poster || "" };
  var BLACK = 0.003;

  function channel(v) { v = v / 255; return v <= 0.04045 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4); }
  function measure(dataUrl, done) {
    var probe = new Image();
    probe.onload = function () {
      var c = document.createElement("canvas"); var s = 64;
      var r = Math.min(1, s / Math.max(probe.width, probe.height));
      c.width = Math.max(1, Math.round(probe.width * r)); c.height = Math.max(1, Math.round(probe.height * r));
      var ctx = c.getContext("2d"); ctx.drawImage(probe, 0, 0, c.width, c.height);
      var d = ctx.getImageData(0, 0, c.width, c.height).data; var vals = [];
      for (var i = 0; i < d.length; i += 4) vals.push(0.2126 * channel(d[i]) + 0.7152 * channel(d[i + 1]) + 0.0722 * channel(d[i + 2]));
      vals.sort(function (a, b) { return a - b; });
      done(vals[Math.max(0, Math.floor(vals.length * 0.9) - 1)]);
    };
    probe.src = dataUrl;
  }
  function ratio(a, b) { var hi = Math.max(a, b), lo = Math.min(a, b); return (hi + 0.05) / (lo + 0.05); }

  function bgType() {
    var t = ($("background_type") || {}).value || "theme";
    if (t === "photo" && sources.photo) return "photo";
    if (t === "video" && sources.video) return "video"; // the poster is what shows behind the text
    return "theme";
  }

  function update() {
    var t = ($("background_type") || {}).value || "theme";
    form.querySelectorAll("[data-show-for]").forEach(function (el) {
      el.hidden = el.getAttribute("data-show-for").split(" ").indexOf(t) < 0;
    });
    box.querySelector("[data-preview-title]").textContent = $("title").value || "Headline";
    box.querySelector("[data-preview-subtitle]").textContent = $("subtitle").value;
    [["button_text", "[data-preview-button1]"], ["button2_text", "[data-preview-button2]"]].forEach(function (p) {
      var el = box.querySelector(p[1]); el.textContent = $(p[0]).value; el.hidden = !$(p[0]).value;
    });
    var tone = $("text_tone").value, align = $("text_align").value;
    box.className = "hero-mini hero-tone-" + tone + " hero-align-" + align;
    var bg = bgType();
    box.classList.toggle("hero-glow", bg === "theme");
    img.hidden = shade.hidden = bg === "theme";
    if (bg !== "theme") {
      if (img.getAttribute("src") !== sources[bg]) img.src = sources[bg];
      img.style.objectPosition = $("focal_x").value + "% " + $("focal_y").value + "%";
      shade.style.background = "rgba(10,10,10," + (parseInt($("overlay_opacity").value || "0", 10) / 100) + ")";
    }
    form.querySelectorAll("output[data-output-for]").forEach(function (o) {
      var input = document.getElementById(o.getAttribute("data-output-for")); if (input) o.textContent = input.value;
    });
    var text = tone === "light" ? 1 : BLACK, behind = BLACK;
    if (bg !== "theme" && !isNaN(luminance[bg])) {
      var a = Math.min(80, Math.max(0, parseInt($("overlay_opacity").value || "0", 10))) / 100;
      behind = luminance[bg] * (1 - a) + BLACK * a;
    }
    var r = Math.round(ratio(text, behind) * 100) / 100;
    contrastOut.textContent = r >= 4.5
      ? "Readable: text contrast about " + r + ":1 (meets WCAG AA)."
      : "Readability warning: text contrast about " + r + ":1, below the 4.5:1 WCAG AA needs. " +
        (tone === "light" ? "Increase the dark overlay or choose dark text." : "Choose light text or lower the overlay.");
    contrastOut.className = "mt-3 text-sm " + (r >= 4.5 ? "text-rlm-ink" : "font-semibold text-rlm-flame-deep");
  }

  function watchFile(name, key) {
    var input = $(name); if (!input) return;
    input.addEventListener("change", function () {
      var f = input.files && input.files[0]; if (!f || !/^image\//.test(f.type)) return;
      var reader = new FileReader(); // data: URL (allowed by the CSP img-src), never uploaded until Save
      reader.onload = function () { sources[key] = reader.result; measure(reader.result, function (l) { luminance[key] = l; update(); }); update(); };
      reader.readAsDataURL(f);
    });
  }
  watchFile("image", "photo");
  watchFile("video_poster", "video");
  form.addEventListener("input", update);
  form.addEventListener("change", update);
  update();
})();

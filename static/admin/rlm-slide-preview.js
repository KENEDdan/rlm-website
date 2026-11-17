/* Live preview for the Hero slide form: mirrors the heading, text, button and a newly chosen photo.
   External file (CSP: no inline script); the photo is read locally as a data: URL and never uploaded here. */
(function () {
  "use strict";
  var box = document.querySelector("[data-slide-preview]");
  if (!box) return;
  function bind(id, selector, fallback) {
    var input = document.getElementById(id);
    var target = box.querySelector(selector);
    if (!input || !target) return;
    input.addEventListener("input", function () {
      var value = input.value.trim();
      target.textContent = value || fallback;
      if (selector === "[data-preview-button]") target.hidden = !value;
    });
  }
  bind("id_title", "[data-preview-title]", "Slide heading");
  bind("id_subtitle", "[data-preview-subtitle]", "");
  bind("id_button_text", "[data-preview-button]", "");

  var file = document.getElementById("id_image");
  var img = box.querySelector("[data-preview-img]");
  if (file && img && window.FileReader) {
    file.addEventListener("change", function () {
      var chosen = file.files && file.files[0];
      if (!chosen || !/^image\/(jpeg|png|webp)$/.test(chosen.type) || chosen.size > 20 * 1024 * 1024) return;
      var reader = new FileReader();
      reader.onload = function () {
        if (typeof reader.result === "string" && reader.result.indexOf("data:image/") === 0) {
          img.src = reader.result;
          img.hidden = false;
        }
      };
      reader.readAsDataURL(chosen);
    });
  }
})();

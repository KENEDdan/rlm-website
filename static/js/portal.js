/* Staff portal behaviour. Progressive enhancement only: every screen works without this file.
   External file (CSP: script-src 'self' + nonce): no inline handlers, no eval. */
(function () {
  "use strict";

  // Confirmation for destructive or irreversible buttons: <button data-confirm="Are you sure?">
  document.addEventListener("submit", function (event) {
    var form = event.target;
    var button = event.submitter || form.querySelector("[data-confirm]");
    var message = (button && button.getAttribute("data-confirm")) || form.getAttribute("data-confirm");
    if (message && !window.confirm(message)) event.preventDefault();
  });

  // Print buttons on report pages (the browser's "Save as PDF" makes the PDF).
  document.addEventListener("click", function (event) {
    if (event.target.closest("[data-print]")) {
      event.preventDefault();
      window.print();
    }
  });

  // Close the mobile menu after choosing a link, or with Escape.
  var menu = document.getElementById("portal-menu");
  if (menu) {
    menu.addEventListener("click", function (e) {
      if (e.target.closest("a")) menu.removeAttribute("open");
    });
    document.addEventListener("keydown", function (e) {
      if (e.key === "Escape") menu.removeAttribute("open");
    });
  }

  // Move focus to swapped-in results so keyboard and screen-reader users notice the update.
  document.body.addEventListener("htmx:afterSwap", function (event) {
    var target = event.detail.target.querySelector("[data-focus]");
    if (target) target.focus();
  });
})();

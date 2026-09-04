// theme.js
// Handles switching between dark and light mode. We store the choice in
// localStorage so it's remembered next time you visit, and if you've
// never picked one before we just go with whatever your operating
// system / browser prefers.
//
// This file is loaded in the <head> (not at the bottom of the page) and
// runs immediately, before the page paints, so there's no "flash" of the
// wrong theme for a split second when the page loads.

(function () {
  var STORAGE_KEY = "abaksa-theme";

  function getPreferredTheme() {
    var saved = localStorage.getItem(STORAGE_KEY);
    if (saved === "dark" || saved === "light") {
      return saved;
    }
    var systemPrefersDark = window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches;
    return systemPrefersDark ? "dark" : "light";
  }

  function applyTheme(theme) {
    document.documentElement.setAttribute("data-theme", theme);
    document.dispatchEvent(new CustomEvent("abaksa:themechange", { detail: { theme: theme } }));
  }

  // apply immediately so there's no flash of unstyled content
  applyTheme(getPreferredTheme());

  window.ABAKSA_setTheme = function (theme) {
    localStorage.setItem(STORAGE_KEY, theme);
    applyTheme(theme);
  };

  window.ABAKSA_toggleTheme = function () {
    var current = document.documentElement.getAttribute("data-theme");
    var next = current === "dark" ? "light" : "dark";
    window.ABAKSA_setTheme(next);
  };

  // once the DOM is ready, wire up every element with data-theme-toggle
  // on it (there can be more than one - e.g. sidebar footer + mobile menu)
  document.addEventListener("DOMContentLoaded", function () {
    var toggles = document.querySelectorAll("[data-theme-toggle]");
    toggles.forEach(function (el) {
      el.addEventListener("click", function () {
        window.ABAKSA_toggleTheme();
      });
    });
  });
})();

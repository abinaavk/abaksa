// app.js
// Small, framework-free helpers that run on every page: opening/closing
// the mobile sidebar drawer, opening/closing modal popups, the little
// notification/profile dropdown menus in the topbar, and turning flash
// messages into auto-dismissing toast popups.

document.addEventListener("DOMContentLoaded", function () {
  setupMobileSidebar();
  setupModals();
  setupDropdowns();
  setupFlashToasts();
  setupConfirmForms();
});

// ---------------------------------------------------------------------
// Mobile sidebar (hamburger menu)
// ---------------------------------------------------------------------

function setupMobileSidebar() {
  var shell = document.querySelector(".app-shell");
  var hamburger = document.querySelector("[data-hamburger]");
  var backdrop = document.querySelector(".sidebar-backdrop");

  if (!shell || !hamburger) {
    return;
  }

  hamburger.addEventListener("click", function () {
    shell.classList.toggle("sidebar-open");
  });

  if (backdrop) {
    backdrop.addEventListener("click", function () {
      shell.classList.remove("sidebar-open");
    });
  }

  // close the drawer automatically if you click a nav link on mobile
  var navLinks = document.querySelectorAll(".nav-item");
  navLinks.forEach(function (link) {
    link.addEventListener("click", function () {
      shell.classList.remove("sidebar-open");
    });
  });
}

// ---------------------------------------------------------------------
// Modals - any element with data-modal-open="modal-id" opens the modal
// with that id, and anything inside a modal with data-modal-close closes
// the modal it's inside of. Clicking the dark overlay also closes it.
// ---------------------------------------------------------------------

function setupModals() {
  document.querySelectorAll("[data-modal-open]").forEach(function (trigger) {
    trigger.addEventListener("click", function () {
      var modalId = trigger.getAttribute("data-modal-open");
      var overlay = document.getElementById(modalId);
      if (overlay) {
        overlay.classList.add("open");
      }
    });
  });

  document.querySelectorAll(".modal-overlay").forEach(function (overlay) {
    overlay.addEventListener("click", function (event) {
      if (event.target === overlay) {
        overlay.classList.remove("open");
      }
    });
  });

  document.querySelectorAll("[data-modal-close]").forEach(function (btn) {
    btn.addEventListener("click", function () {
      var overlay = btn.closest(".modal-overlay");
      if (overlay) {
        overlay.classList.remove("open");
      }
    });
  });

  document.addEventListener("keydown", function (event) {
    if (event.key === "Escape") {
      document.querySelectorAll(".modal-overlay.open").forEach(function (overlay) {
        overlay.classList.remove("open");
      });
    }
  });
}

// ---------------------------------------------------------------------
// Dropdowns (notification bell / profile menu in the topbar)
// ---------------------------------------------------------------------

function setupDropdowns() {
  var dropdowns = document.querySelectorAll(".dropdown");

  dropdowns.forEach(function (dropdown) {
    var trigger = dropdown.querySelector("[data-dropdown-trigger]");
    if (!trigger) {
      return;
    }
    trigger.addEventListener("click", function (event) {
      event.stopPropagation();
      var wasOpen = dropdown.classList.contains("open");
      dropdowns.forEach(function (d) { d.classList.remove("open"); });
      if (!wasOpen) {
        dropdown.classList.add("open");
      }
    });
  });

  document.addEventListener("click", function () {
    dropdowns.forEach(function (d) { d.classList.remove("open"); });
  });
}

// ---------------------------------------------------------------------
// Flash messages -> toasts
// The server renders flash messages into a hidden <script type="application/json">
// block (see templates/partials/toasts.html) - we read that and pop up a
// real toast notification for each one, then remove it after a few seconds.
// ---------------------------------------------------------------------

function setupFlashToasts() {
  var dataEl = document.getElementById("flash-data");
  if (!dataEl) {
    return;
  }

  var messages;
  try {
    messages = JSON.parse(dataEl.textContent);
  } catch (e) {
    return;
  }

  var container = document.querySelector(".toast-container");
  if (!container) {
    container = document.createElement("div");
    container.className = "toast-container";
    document.body.appendChild(container);
  }

  messages.forEach(function (item, index) {
    setTimeout(function () {
      showToast(container, item.category, item.text);
    }, index * 120);
  });
}

var TOAST_ICONS = {
  success: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M20 6 9 17l-5-5"/></svg>',
  error: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><path d="M15 9l-6 6M9 9l6 6"/></svg>',
  warning: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 9v4M12 17h.01M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0Z"/></svg>',
  info: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><path d="M12 16v-4M12 8h.01"/></svg>'
};

function showToast(container, category, text) {
  var kind = TOAST_ICONS[category] ? category : "info";
  var toast = document.createElement("div");
  toast.className = "toast toast-" + kind;
  toast.innerHTML = TOAST_ICONS[kind] + "<span>" + text + "</span>" +
    '<button type="button" class="toast-close" aria-label="Dismiss">&times;</button>';

  container.appendChild(toast);

  var remove = function () {
    toast.style.opacity = "0";
    toast.style.transform = "translateY(6px)";
    setTimeout(function () { toast.remove(); }, 180);
  };

  toast.querySelector(".toast-close").addEventListener("click", remove);
  setTimeout(remove, 4500);
}

// small helper other pages can call directly for client-side-only messages
// (e.g. "copied to clipboard") without a full page reload
window.ABAKSA_toast = function (category, text) {
  var container = document.querySelector(".toast-container");
  if (!container) {
    container = document.createElement("div");
    container.className = "toast-container";
    document.body.appendChild(container);
  }
  showToast(container, category, text);
};

// ---------------------------------------------------------------------
// Confirm-before-submit forms - add data-confirm="Are you sure?" to any
// <form> and it will ask before actually submitting (used for deletes)
// ---------------------------------------------------------------------

function setupConfirmForms() {
  document.querySelectorAll("form[data-confirm]").forEach(function (form) {
    form.addEventListener("submit", function (event) {
      var message = form.getAttribute("data-confirm");
      if (!window.confirm(message)) {
        event.preventDefault();
      }
    });
  });
}

(function () {
  "use strict";

  var CONTACT_API_URL = String(window.PORTFOLIO_CONTACT_ENDPOINT || "").trim();
  var CONTACT_EMAIL = "matteo.mastore.job@gmail.com";
  var EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

  document.addEventListener("DOMContentLoaded", function () {
    setYear();
    refreshIcons();
    initNavigation();
    initReveal();
    initProjectFilters();
    initContactForm();
  });

  function refreshIcons() {
    if (window.lucide && typeof window.lucide.createIcons === "function") {
      window.lucide.createIcons({
        attrs: {
          "aria-hidden": "true",
          "stroke-width": "2",
        },
      });
    }
  }

  function setYear() {
    document.querySelectorAll("[data-year]").forEach(function (element) {
      element.textContent = String(new Date().getFullYear());
    });
  }

  function initNavigation() {
    var toggle = document.querySelector(".nav-toggle");
    var navigation = document.querySelector(".site-nav");

    function setOpen(open) {
      if (!toggle || !navigation) return;
      navigation.classList.toggle("open", open);
      toggle.setAttribute("aria-expanded", open ? "true" : "false");
      toggle.setAttribute("aria-label", open ? "Close navigation" : "Open navigation");
      toggle.innerHTML =
        '<i data-lucide="' + (open ? "x" : "menu") + '" aria-hidden="true"></i>';
      refreshIcons();
    }

    if (toggle && navigation) {
      toggle.addEventListener("click", function () {
        setOpen(!navigation.classList.contains("open"));
      });

      navigation.querySelectorAll("a").forEach(function (link) {
        link.addEventListener("click", function () {
          setOpen(false);
        });
      });

      document.addEventListener("click", function (event) {
        var eventPath =
          typeof event.composedPath === "function" ? event.composedPath() : [];
        if (
          navigation.classList.contains("open") &&
          !navigation.contains(event.target) &&
          !toggle.contains(event.target) &&
          eventPath.indexOf(toggle) === -1
        ) {
          setOpen(false);
        }
      });

      document.addEventListener("keydown", function (event) {
        if (event.key === "Escape" && navigation.classList.contains("open")) {
          setOpen(false);
          toggle.focus();
        }
      });
    }

    var current = window.location.pathname.split("/").pop() || "index.html";
    document.querySelectorAll(".site-nav a").forEach(function (link) {
      if (link.getAttribute("href") === current) {
        link.classList.add("active");
        link.setAttribute("aria-current", "page");
      }
    });
  }

  function initReveal() {
    var elements = document.querySelectorAll(".reveal");
    if (!elements.length) return;

    if (
      !("IntersectionObserver" in window) ||
      window.matchMedia("(prefers-reduced-motion: reduce)").matches
    ) {
      elements.forEach(function (element) {
        element.classList.add("visible");
      });
      return;
    }

    var observer = new IntersectionObserver(
      function (entries) {
        entries.forEach(function (entry) {
          if (entry.isIntersecting) {
            entry.target.classList.add("visible");
            observer.unobserve(entry.target);
          }
        });
      },
      { threshold: 0.08, rootMargin: "0px 0px -32px 0px" }
    );

    elements.forEach(function (element) {
      observer.observe(element);
    });
  }

  function initProjectFilters() {
    var buttons = document.querySelectorAll("[data-project-filter]");
    var cards = document.querySelectorAll("[data-project-card]");
    var count = document.getElementById("projectCount");
    if (!buttons.length || !cards.length) return;

    buttons.forEach(function (button) {
      button.addEventListener("click", function () {
        var filter = button.getAttribute("data-project-filter") || "all";
        var visible = 0;

        buttons.forEach(function (candidate) {
          candidate.setAttribute(
            "aria-pressed",
            candidate === button ? "true" : "false"
          );
        });

        cards.forEach(function (card) {
          var categories = String(card.getAttribute("data-category") || "").split(/\s+/);
          var show = filter === "all" || categories.indexOf(filter) !== -1;
          card.hidden = !show;
          if (show) visible += 1;
        });

        if (count) {
          count.textContent = visible + (visible === 1 ? " project" : " projects");
        }
      });
    });
  }

  function initContactForm() {
    var form = document.getElementById("contact-form");
    if (!form) return;

    var status = document.getElementById("form-status");
    var submit = form.querySelector(".button-submit");

    form.addEventListener("submit", function (event) {
      event.preventDefault();
      submitContact(form, status, submit);
    });

    form.querySelectorAll("input, textarea").forEach(function (input) {
      input.addEventListener("input", function () {
        clearFieldError(input);
      });
    });
  }

  async function submitContact(form, status, submit) {
    var data = {
      name: valueOf(form, "name"),
      email: valueOf(form, "email"),
      subject: valueOf(form, "subject"),
      message: valueOf(form, "message"),
    };
    var errors = validateContact(data);
    applyErrors(form, errors);

    if (Object.keys(errors).length) {
      setStatus(status, "Please check the highlighted fields.", "error");
      return;
    }

    if (!CONTACT_API_URL) {
      openEmailDraft(data);
      form.reset();
      setStatus(status, "Your email draft is ready.", "success");
      return;
    }

    submit.disabled = true;
    setStatus(status, "Sending message...", "");

    try {
      var response = await fetch(CONTACT_API_URL, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(data),
      });
      var payload = await response.json().catch(function () {
        return {};
      });

      if (response.ok) {
        form.reset();
        setStatus(status, "Message sent. Thank you.", "success");
        return;
      }

      if (response.status === 400 && payload.fields) {
        applyErrors(form, payload.fields);
        setStatus(status, "Please check the highlighted fields.", "error");
        return;
      }

      setStatus(status, "The message could not be sent. Please email me directly.", "error");
    } catch (_error) {
      setStatus(status, "The message could not be sent. Please email me directly.", "error");
    } finally {
      submit.disabled = false;
    }
  }

  function valueOf(form, name) {
    var element = form.elements.namedItem(name);
    return element && typeof element.value === "string" ? element.value.trim() : "";
  }

  function validateContact(data) {
    var errors = {};
    if (!data.name) errors.name = "Enter your name.";
    if (!data.email) {
      errors.email = "Enter your email.";
    } else if (!EMAIL_RE.test(data.email)) {
      errors.email = "Enter a valid email address.";
    }
    if (!data.subject) errors.subject = "Enter a subject.";
    if (!data.message) errors.message = "Enter a message.";
    return errors;
  }

  function applyErrors(form, errors) {
    ["name", "email", "subject", "message"].forEach(function (name) {
      var input = form.elements.namedItem(name);
      if (!input) return;
      var field = input.closest(".field");
      if (!field) return;
      var output = field.querySelector('[data-error-for="' + name + '"]');
      var message = errors[name] || "";
      field.classList.toggle("invalid", Boolean(message));
      input.setAttribute("aria-invalid", message ? "true" : "false");
      if (output) output.textContent = message;
    });
  }

  function clearFieldError(input) {
    var field = input.closest(".field");
    if (!field) return;
    field.classList.remove("invalid");
    input.setAttribute("aria-invalid", "false");
    var output = field.querySelector(".field-error");
    if (output) output.textContent = "";
  }

  function setStatus(element, message, kind) {
    if (!element) return;
    element.textContent = message;
    element.classList.remove("success", "error");
    if (kind) element.classList.add(kind);
  }

  function openEmailDraft(data) {
    var body = [
      "Name: " + data.name,
      "Email: " + data.email,
      "",
      data.message,
    ].join("\n");
    window.location.href =
      "mailto:" +
      CONTACT_EMAIL +
      "?subject=" +
      encodeURIComponent(data.subject) +
      "&body=" +
      encodeURIComponent(body);
  }
})();

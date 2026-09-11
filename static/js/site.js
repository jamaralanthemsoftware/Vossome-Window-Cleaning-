document.addEventListener("DOMContentLoaded", function () {
  document.documentElement.classList.add("has-js");

  const trackEvent = (name, data) => {
    try {
      window.umami?.track(name, data);
    } catch {
      // Analytics must never prevent the requested navigation.
    }
    try {
      window.gtag?.("event", name, data || {});
    } catch {
      // Analytics must never prevent the requested navigation.
    }
  };

  const bookingContextKey = "vossome_quote_context";
  const bookingContextMaxAge = 24 * 60 * 60 * 1000;

  document.querySelectorAll(".service-text-button[data-service-slug]").forEach((link) => {
    link.addEventListener("click", () => {
      trackEvent("text_cta_clicked", {
        service_slug: link.dataset.serviceSlug,
      });
    });
  });

  document.querySelectorAll('a[href^="tel:"], a[href^="sms:"]').forEach((link) => {
    link.addEventListener("click", () => trackEvent("text_cta_clicked", {
      link_type: link.getAttribute("href").startsWith("sms:") ? "sms" : "phone",
    }));
  });

  document.querySelectorAll('a[href*="/contact/"]').forEach((link) => {
    link.addEventListener("click", () => trackEvent("booking_cta_clicked", {
      cta_location: link.dataset.ctaLocation || "website",
      purpose: "quote_or_contact",
    }));
  });

  document.querySelectorAll("[data-service-slug][data-cta-location]").forEach((link) => {
    link.addEventListener("click", () => {
      try {
        window.localStorage.setItem(
          bookingContextKey,
          JSON.stringify({
            service_slug: link.dataset.serviceSlug,
            cta_location: link.dataset.ctaLocation,
            recorded_at: Date.now(),
          }),
        );
      } catch {
        // Completion tracking remains optional if browser storage is unavailable.
      }
      trackEvent("booking_cta_clicked", {
        service_slug: link.dataset.serviceSlug,
        cta_location: link.dataset.ctaLocation,
      });
    });
  });

  if (document.body.dataset.bookingComplete === "true") {
    try {
      const context = JSON.parse(window.localStorage.getItem(bookingContextKey));
      window.localStorage.removeItem(bookingContextKey);
      if (
        context &&
        typeof context.service_slug === "string" &&
        typeof context.cta_location === "string" &&
        Number.isFinite(context.recorded_at) &&
        Date.now() - context.recorded_at <= bookingContextMaxAge
      ) {
        trackEvent("booking_completed", {
          service_slug: context.service_slug,
          cta_location: context.cta_location,
        });
      }
    } catch {
      // Ignore malformed or unavailable browser storage.
    }
  }

  if (document.body.dataset.contactSubmitted === "true") {
    trackEvent("contact_form_submitted");
  }

  const recaptchaForm = document.querySelector(
    ".contact-form[data-recaptcha-site-key]",
  );
  recaptchaForm?.addEventListener("submit", (event) => {
    if (recaptchaForm.dataset.recaptchaState === "submitting") return;
    event.preventDefault();
    if (recaptchaForm.dataset.recaptchaState === "pending") return;
    recaptchaForm.dataset.recaptchaState = "pending";
    const submitButton = recaptchaForm.querySelector('[type="submit"]');
    const errorMessage = recaptchaForm.querySelector(".recaptcha-error");
    const tokenInput = recaptchaForm.querySelector('[name="recaptcha_token"]');
    const originalLabel = submitButton?.textContent;
    if (submitButton) {
      submitButton.disabled = true;
      submitButton.textContent = "Checking…";
    }
    if (errorMessage) errorMessage.hidden = true;

    const failVerification = () => {
      recaptchaForm.dataset.recaptchaState = "idle";
      if (tokenInput) tokenInput.value = "";
      if (submitButton) {
        submitButton.disabled = false;
        submitButton.textContent = originalLabel;
      }
      if (errorMessage) errorMessage.hidden = false;
    };

    if (!window.grecaptcha || !tokenInput) {
      failVerification();
      return;
    }
    window.grecaptcha.ready(() => {
      window.grecaptcha
        .execute(recaptchaForm.dataset.recaptchaSiteKey, {
          action: "contact_form",
        })
        .then((token) => {
          tokenInput.value = token;
          recaptchaForm.dataset.recaptchaState = "submitting";
          recaptchaForm.requestSubmit();
        })
        .catch(failVerification);
    });
  });

  window.addEventListener("pageshow", () => {
    if (!recaptchaForm) return;
    recaptchaForm.dataset.recaptchaState = "idle";
    const tokenInput = recaptchaForm.querySelector('[name="recaptcha_token"]');
    if (tokenInput) tokenInput.value = "";
    const submitButton = recaptchaForm.querySelector('[type="submit"]');
    if (submitButton) {
      submitButton.disabled = false;
      submitButton.textContent = "Request my free quote";
    }
  });

  const skipLink = document.querySelector(".skip-link");
  const main = document.querySelector("#main-content");
  skipLink?.addEventListener("click", () => main?.focus());

  const button = document.querySelector(".menu-toggle");
  const navigation = document.querySelector(".main-nav");
  if (!button || !navigation) return;

  const setMenuOpen = (isOpen) => {
    button.setAttribute("aria-expanded", String(isOpen));
    button.setAttribute("aria-label", isOpen ? "Close main menu" : "Open main menu");
    navigation.classList.toggle("is-open", isOpen);
  };

  button.addEventListener("click", () => {
    setMenuOpen(button.getAttribute("aria-expanded") !== "true");
  });

  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && button.getAttribute("aria-expanded") === "true") {
      setMenuOpen(false);
      button.focus();
    }
  });
});

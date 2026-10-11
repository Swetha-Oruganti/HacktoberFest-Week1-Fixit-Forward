(() => {
  const $ = (selector) => document.querySelector(selector);

  function csrfToken() {
    const entry = document.cookie.split("; ").find((item) => item.startsWith("csrftoken="));
    return entry ? decodeURIComponent(entry.split("=").slice(1).join("=")) : "";
  }

  function showPanel(name) {
    document.querySelectorAll("[data-auth-tab]").forEach((tab) => {
      const active = tab.dataset.authTab === name;
      tab.classList.toggle("active", active);
      tab.setAttribute("aria-selected", String(active));
    });
    $("#login-panel").classList.toggle("hidden", name !== "login");
    $("#register-panel").classList.toggle("hidden", name !== "register");
    $(`#${name}-error`).textContent = "";
    const firstField = $(`#${name}-panel input`);
    if (firstField) firstField.focus({ preventScroll: true });
  }

  document.querySelectorAll("[data-auth-tab], [data-switch-auth]").forEach((control) => {
    control.addEventListener("click", () => showPanel(control.dataset.authTab || control.dataset.switchAuth));
  });

  document.querySelectorAll("[data-password-toggle]").forEach((button) => {
    button.addEventListener("click", () => {
      const input = document.getElementById(button.dataset.passwordToggle);
      const reveal = input.type === "password";
      input.type = reveal ? "text" : "password";
      button.textContent = reveal ? "Hide" : "Show";
      button.setAttribute("aria-label", `${reveal ? "Hide" : "Show"} password`);
    });
  });

  async function submit(form, endpoint, errorSelector, payload) {
    const button = form.querySelector("button[type=submit]");
    const original = button.innerHTML;
    const errorBox = $(errorSelector);
    errorBox.textContent = "";
    button.disabled = true;
    button.innerHTML = '<span class="auth-spinner"></span> Please wait';
    try {
      const response = await fetch(endpoint, {
        method: "POST",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json", "X-CSRFToken": csrfToken() },
        body: JSON.stringify(payload),
      });
      const result = await response.json();
      if (!response.ok) throw new Error(result.error || "Could not complete that request.");
      window.location.reload();
    } catch (error) {
      errorBox.textContent = error.message || "Connection failed. Please try again.";
      button.disabled = false;
      button.innerHTML = original;
    }
  }

  $("#login-form").addEventListener("submit", (event) => {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    submit(event.currentTarget, "/api/auth/login/", "#login-error", {
      email: form.get("email"), password: form.get("password"),
    });
  });

  $("#register-form").addEventListener("submit", (event) => {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const password = form.get("password");
    if (password.length < 12) { $("#register-error").textContent = "Use a password with at least 12 characters."; return; }
    if (password !== form.get("password_confirmation")) { $("#register-error").textContent = "Those passwords do not match."; return; }
    submit(event.currentTarget, "/api/auth/register/", "#register-error", {
      name: form.get("name"), email: form.get("email"), password,
      password_confirmation: form.get("password_confirmation"),
    });
  });
})();

(() => {
  const $ = (selector) => document.querySelector(selector);
  const state = { photo: null, previewUrl: null, draft: null, report: null, coordinates: null };
  const labels = {
    overflowing_bin: "Overflowing bin", pothole: "Pothole or damaged road", streetlight: "Broken streetlight",
    sidewalk: "Damaged pavement or sidewalk", drain: "Blocked drain or waterlogging",
    public_space: "Neglected public space", other: "Other civic issue",
  };
  const departments = {
    overflowing_bin: "Sanitation / Solid Waste", pothole: "Roads / Public Works", streetlight: "Street Lighting",
    sidewalk: "Roads / Public Works", drain: "Stormwater / Drainage", public_space: "Parks / Public Spaces", other: "Local Civic Authority",
  };
  const statusLabels = {
    ready_to_submit: "Ready to submit", submitted_by_user: "Submitted by me", acknowledged: "Acknowledged",
    in_progress: "In progress", resolved: "Resolved",
  };

  function setStep(activeStep) {
    document.querySelectorAll(".step-indicator [data-step]").forEach((node) => {
      const step = Number(node.dataset.step);
      node.classList.toggle("step-active", step === activeStep);
      node.classList.toggle("step-done", step < activeStep);
      if (step === activeStep) node.setAttribute("aria-current", "step");
      else node.removeAttribute("aria-current");
    });
  }

  function toast(message) {
    const node = $("#toast");
    node.textContent = message;
    node.classList.add("visible");
    window.setTimeout(() => node.classList.remove("visible"), 2800);
  }

  function setError(id, message = "") { $(id).textContent = message; }

  async function api(url, options = {}) {
    const response = await fetch(url, { credentials: "same-origin", ...options });
    const type = response.headers.get("content-type") || "";
    const body = type.includes("application/json") ? await response.json() : await response.text();
    if (!response.ok) throw new Error(body.error || "Something went wrong. Please try again.");
    return body;
  }

  function csrfToken() {
    const entry = document.cookie.split("; ").find((item) => item.startsWith("csrftoken="));
    return entry ? decodeURIComponent(entry.split("=").slice(1).join("=")) : "";
  }

  function selectPhoto(file) {
    setError("#upload-error");
    if (!file) return;
    if (!file.type.startsWith("image/")) { setError("#upload-error", "Choose a JPG, PNG, or WebP image."); return; }
    if (file.size > Number(document.querySelector(".file-note").textContent.match(/\d+/)?.[0] || 10) * 1024 * 1024) {
      setError("#upload-error", "That photo is too large. Choose a smaller image."); return;
    }
    state.photo = file;
    if (state.previewUrl) URL.revokeObjectURL(state.previewUrl);
    state.previewUrl = URL.createObjectURL(file);
    $("#preview-image").src = state.previewUrl;
    $("#editor-image").src = state.previewUrl;
    $("#file-name").textContent = file.name;
    $("#editor-file-name").textContent = file.name;
    $("#upload-empty").classList.add("hidden");
    $("#upload-preview").classList.remove("hidden");
    $("#analyze-button").disabled = false;
    $("#analyze-button span").textContent = "Analyze photo";
  }

  function resetFlow() {
    state.photo = null;
    state.draft = null;
    state.coordinates = null;
    $("#photo-input").value = "";
    $("#upload-empty").classList.remove("hidden");
    $("#upload-preview").classList.add("hidden");
    $("#analyze-button").disabled = true;
    $("#editor-section").classList.add("hidden");
    $("#success-section").classList.add("hidden");
    setStep(1);
    $("#workspace").scrollIntoView({ behavior: "smooth", block: "start" });
  }

  async function analyze() {
    if (!state.photo) return;
    const button = $("#analyze-button");
    button.disabled = true;
    button.classList.add("is-loading");
    button.querySelector("span").textContent = "Looking at your photo…";
    setError("#upload-error");
    const data = new FormData();
    data.append("photo", state.photo);
    try {
      const result = await api("/api/analyze/", { method: "POST", headers: { "X-CSRFToken": csrfToken() }, body: data });
      state.draft = result.draft;
      $("#category-field").value = result.draft.category;
      $("#title-field").value = result.draft.title;
      $("#description-field").value = result.draft.description;
      $("#department-field").textContent = result.draft.department;
      $("#classification-label").textContent = result.draft.category_label;
      $("#classification-method").textContent = result.draft.classifier === "local-open-weight" ? "Local open-weight model · review before saving" : "Demo suggestion · review before saving";
      $("#confidence-tag").textContent = result.draft.confidence ? `${Math.round(result.draft.confidence * 100)}% match` : "Demo mode";
      $("#editor-section").classList.remove("hidden");
      setStep(2);
      $("#editor-section").scrollIntoView({ behavior: "smooth", block: "start" });
    } catch (error) {
      setError("#upload-error", error.message);
    } finally {
      button.disabled = false;
      button.classList.remove("is-loading");
      button.querySelector("span").textContent = "Analyze photo";
    }
  }

  function categoryChanged() {
    const category = $("#category-field").value;
    $("#department-field").textContent = departments[category];
    if (state.draft && $("#title-field").value === state.draft.title) $("#title-field").value = labels[category];
  }

  async function saveReport() {
    if (!state.photo) return;
    const button = $("#save-button");
    button.disabled = true;
    button.querySelector("span").textContent = "Saving your report…";
    setError("#save-error");
    const form = new FormData();
    form.append("photo", state.photo);
    form.append("report", JSON.stringify({
      category: $("#category-field").value,
      title: $("#title-field").value,
      description: $("#description-field").value,
      severity: $("#severity-field").value,
      location: $("#location-field").value,
      coordinates: state.coordinates,
      confidence: state.draft?.confidence ?? null,
      classifier: state.draft?.classifier ?? "user-edited",
    }));
    try {
      const result = await api("/api/reports/", { method: "POST", headers: { "X-CSRFToken": csrfToken() }, body: form });
      state.report = result.report;
      showSaved(result.report);
      await loadReports();
    } catch (error) {
      setError("#save-error", error.message);
    } finally {
      button.disabled = false;
      button.querySelector("span").textContent = "Save my report";
    }
  }

  function showSaved(report) {
    $("#editor-section").classList.add("hidden");
    $("#success-section").classList.remove("hidden");
    setStep(3);
    $("#reference-chip").textContent = report.reference;
    $("#success-message").textContent = `“${report.title}” is saved and ready for you to share.`;
    $("#download-report").href = `/api/reports/${report.id}/?format=txt`;
    $("#status-field").value = report.status;
    $("#success-section").scrollIntoView({ behavior: "smooth", block: "start" });
  }

  async function copyReport() {
    if (!state.report) return;
    try {
      const text = await api(`/api/reports/${state.report.id}/?format=txt`);
      await navigator.clipboard.writeText(text);
      toast("Report copied to clipboard.");
    } catch (_) { toast("Could not copy. Use Download .txt instead."); }
  }

  async function updateStatus() {
    if (!state.report) return;
    const status = $("#status-field").value;
    try {
      const result = await api(`/api/reports/${state.report.id}/status/`, {
        method: "POST", headers: { "Content-Type": "application/json", "X-CSRFToken": csrfToken() }, body: JSON.stringify({ status }),
      });
      state.report = result.report;
      await loadReports();
      toast("Your status note was updated.");
    } catch (error) { toast(error.message); }
  }

  async function useLocation() {
    if (!navigator.geolocation) { toast("Location is not available in this browser."); return; }
    const button = $("#location-button");
    button.textContent = "…";
    navigator.geolocation.getCurrentPosition((position) => {
      const latitude = Number(position.coords.latitude.toFixed(6));
      const longitude = Number(position.coords.longitude.toFixed(6));
      state.coordinates = { latitude, longitude };
      $("#coordinate-note").textContent = `${latitude}, ${longitude} · you can still add a street or landmark`;
      $("#coordinate-note").classList.remove("hidden");
      button.textContent = "✓";
      toast("Location added. Check the pin is near the issue.");
    }, () => { button.textContent = "⌖"; toast("Location wasn’t added. You can enter a place manually."); }, { enableHighAccuracy: false, timeout: 10000, maximumAge: 60000 });
  }

  function renderReports(reports) {
    const list = $("#report-list");
    $("#saved-count").textContent = `${reports.length} ${reports.length === 1 ? "report" : "reports"}`;
    list.replaceChildren();
    if (!reports.length) {
      const empty = document.createElement("div");
      empty.className = "empty-reports";
      empty.innerHTML = '<span class="empty-icon">↗</span><span>Your saved reports will show up here.</span>';
      list.append(empty);
      return;
    }
    for (const report of reports) {
      const article = document.createElement("article");
      article.className = "report-row";
      const img = document.createElement("img");
      img.className = "report-thumb";
      img.src = report.photo_url;
      img.alt = "";
      const copy = document.createElement("div");
      copy.className = "report-row-copy";
      const title = document.createElement("b");
      title.textContent = report.title;
      const meta = document.createElement("span");
      meta.textContent = `${report.reference} · ${report.category_label}`;
      copy.append(title, meta);
      const status = document.createElement("span");
      status.className = "report-status";
      status.textContent = statusLabels[report.status] || report.status;
      const link = document.createElement("a");
      link.href = `/api/reports/${report.id}/?format=txt`;
      link.className = "report-download";
      link.textContent = "Download ↗";
      link.setAttribute("aria-label", `Download report ${report.reference}`);
      article.append(img, copy, status, link);
      list.append(article);
    }
  }

  async function loadReports() {
    try { renderReports((await api("/api/reports/list/")).reports); }
    catch (_) { $("#saved-count").textContent = "Offline"; }
  }

  const input = $("#photo-input");
  $("#browse-button").addEventListener("click", () => input.click());
  $("#drop-zone").addEventListener("click", (event) => { if (!event.target.closest("button")) input.click(); });
  $("#drop-zone").addEventListener("keydown", (event) => { if (event.key === "Enter" || event.key === " ") { event.preventDefault(); input.click(); } });
  input.addEventListener("change", () => selectPhoto(input.files[0]));
  $("#change-photo").addEventListener("click", (event) => { event.stopPropagation(); input.click(); });
  ["dragenter", "dragover"].forEach((name) => $("#drop-zone").addEventListener(name, (event) => { event.preventDefault(); $("#drop-zone").classList.add("dragging"); }));
  ["dragleave", "drop"].forEach((name) => $("#drop-zone").addEventListener(name, (event) => { event.preventDefault(); $("#drop-zone").classList.remove("dragging"); }));
  $("#drop-zone").addEventListener("drop", (event) => selectPhoto(event.dataTransfer.files[0]));
  $("#analyze-button").addEventListener("click", analyze);
  $("#category-field").addEventListener("change", categoryChanged);
  $("#save-button").addEventListener("click", saveReport);
  $("#start-over").addEventListener("click", resetFlow);
  $("#new-report").addEventListener("click", resetFlow);
  $("#copy-report").addEventListener("click", copyReport);
  $("#status-field").addEventListener("change", updateStatus);
  $("#location-button").addEventListener("click", useLocation);
  $("#logout-button").addEventListener("click", async () => {
    const button = $("#logout-button");
    button.disabled = true;
    try {
      await api("/api/auth/logout/", { method: "POST", headers: { "X-CSRFToken": csrfToken() } });
      window.location.reload();
    } catch (error) {
      button.disabled = false;
      toast(error.message);
    }
  });
  loadReports();
})();

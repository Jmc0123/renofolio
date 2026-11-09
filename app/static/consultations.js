// Enhances the same inbox routes with a drawer while keeping the full page links usable.
(() => {
  const drawer = document.getElementById("consultation-drawer");
  if (!drawer || !drawer.showModal || !window.fetch) return;
  const content = drawer.querySelector("[data-consultation-content]");
  const notice = drawer.querySelector("[data-consultation-notice]");
  const fullPage = drawer.querySelector("[data-consultation-full-page]");
  let busy = false;
  let currentUrl;

  // 9 November: shows the number of conversations with unread messages on every Messages badge (hidden at 0).
  function updateBadges(count) {
    document.querySelectorAll("[data-unread-badge]").forEach((badge) => {
      badge.hidden = count === 0;
      badge.querySelector("[data-unread-count]").textContent = count;
    });
  }

  // Loads the inbox, a conversation or a form result into the drawer, keeping any unsent draft.
  async function load(url, form) {
    if (busy) return;
    busy = true;
    const keepDraft = !form && url === currentUrl ? content.querySelector("textarea")?.value : "";
    if (!form) fullPage.href = url;
    notice.hidden = false;
    notice.textContent = form ? "Saving…" : "Loading messages…";
    content.setAttribute("aria-busy", "true");
    try {
      const response = await fetch(url, {
        method: form ? "POST" : "GET",
        body: form ? new FormData(form) : undefined,
        headers: { "X-Consultation-Fragment": "1" },
        credentials: "same-origin",
      });
      if (response.headers.get("X-Consultation-Fragment") !== "1") {
        if (response.redirected) {
          window.location.assign(response.url);
          return;
        }
        throw new Error("Messages response unavailable");
      }
      content.innerHTML = await response.text();
      const unread = response.headers.get("X-Consultation-Unread");
      if (unread !== null) updateBadges(Number(unread));
      currentUrl = response.url;
      fullPage.href = currentUrl;
      const input = content.querySelector("textarea");
      if (input && keepDraft) input.value = keepDraft;
      notice.hidden = true;
      const thread = content.querySelector(".consultation-thread");
      if (thread) thread.scrollTop = thread.scrollHeight;
    } catch {
      notice.textContent = form
        ? "Could not confirm the message. Refresh before sending again."
        : "Could not load messages. Try again or open the full page.";
    } finally {
      busy = false;
      content.removeAttribute("aria-busy");
    }
  }

  // Opens the drawer from any Messages button, or follows a link inside the drawer.
  document.addEventListener("click", (event) => {
    const launch = event.target.closest("[data-consultation-launch]");
    const link = event.target.closest("[data-consultation-link]");
    const target = launch || (link && drawer.contains(link) ? link : null);
    if (!target || event.button !== 0 || event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return;
    event.preventDefault();
    if (busy) return;
    if (!drawer.open) {
      content.replaceChildren();
      drawer.showModal();
    }
    load(target.href);
  });

  // Sends a drawer form in the background and shows the result in the drawer.
  drawer.addEventListener("submit", (event) => {
    if (!event.target.matches("[data-consultation-form]")) return;
    event.preventDefault();
    // getAttribute is used because the Close form has a field named "action", which hides form.action.
    load(event.target.getAttribute("action"), event.target);
  });

  // Closes the drawer with its × button.
  drawer.querySelector("[data-consultation-close]").addEventListener("click", () => drawer.close());
})();

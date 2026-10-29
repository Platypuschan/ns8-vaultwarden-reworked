/* Uses the authenticated NS8 task/event bridge already used by application UIs. */
(() => {
  "use strict";
  const status = document.getElementById("status");
  const button = document.getElementById("open");
  const tabName = "vaultwarden-admin";
  // Renews the admin session; it never leaves this page and Vaultwarden
  // keeps only its hash. A renewal also needs a fresh NS8 ticket.
  const handle = (() => {
    const bytes = crypto.getRandomValues(new Uint8Array(32));
    return btoa(String.fromCharCode(...bytes)).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
  })();
  let newTab = false;
  let renewal = null;

  // Run open-admin: NS8 checks the rights of the current user and the
  // action returns a one-time ticket for Vaultwarden.
  function openAdminTask() {
    const core = window.parent.core;
    const app = core && core.$children.find(child => typeof child.createModuleTaskForApp === "function");
    const match = /#\/apps\/([a-zA-Z0-9_-]+)/.exec(window.parent.location.hash);
    if (!app || !match) return Promise.reject(new Error("Bitte Vaultwarden über den NS8-Cluster-Manager öffnen."));
    const eventId = crypto.randomUUID();
    const action = "open-admin";
    let cleanup = () => {};
    return new Promise((resolve, reject) => {
      const events = [];
      const timer = setTimeout(() => { cleanup(); reject(new Error("Zeitüberschreitung beim Öffnen.")); }, 60000);
      cleanup = () => { clearTimeout(timer); events.forEach(([name, fn]) => core.$root.$off(name, fn)); };
      const listen = (suffix, fn) => {
        const name = `${action}-${suffix}-${eventId}`;
        const handler = (...args) => { cleanup(); fn(...args); };
        events.push([name, handler]);
        core.$root.$once(name, handler);
      };
      listen("completed", (_context, task) => {
        try { resolve(typeof task.output === "string" ? JSON.parse(task.output) : task.output); }
        catch (_) { reject(new Error("Ungültige Antwort beim Öffnen der Adminoberfläche.")); }
      });
      listen("aborted", () => reject(new Error("Adminoberfläche konnte nicht geöffnet werden. Prüfe, ob Vaultwarden läuft und du als NS8-Administrator angemeldet bist.")));
      listen("validation-failed", () => reject(new Error("Der Adminzugang konnte nicht angefordert werden.")));
      app.createModuleTaskForApp(match[1], { action, data: {},
        extra: { title: "Vaultwarden öffnen", isNotificationHidden: true, eventId }
      }).catch(error => { cleanup(); reject(error); });
    });
  }

  function adminDestination(result) {
    const destination = new URL(result.url);
    if (destination.protocol !== "https:" || destination.pathname !== "/admin/" || destination.username || destination.password)
      throw new Error("Ungültige Adminadresse.");
    if (typeof result.ticket !== "string") throw new Error("Ungültige Antwort beim Öffnen der Adminoberfläche.");
    return destination;
  }

  function startRenewal(seconds) {
    if (renewal) return;
    const renew = async () => {
      try {
        const result = await openAdminTask();
        const destination = adminDestination(result);
        // No cookie: the handle selects the session, also in another tab.
        // The response is opaque, and its resource policy may block it:
        // only a refused ticket ends the renewal.
        fetch(new URL("ns8/renew", destination), { method: "POST", mode: "no-cors",
          credentials: "omit", body: new URLSearchParams({ token: result.ticket + ":" + handle }) }).catch(() => {});
      } catch (error) {
        clearInterval(renewal);
        // The warning stays visible above the embedded admin page
        const message = "Die Adminsitzung kann nicht verlängert werden und endet in Kürze. " + (error.message || "");
        status.textContent = message;
        document.getElementById("warning").textContent = message;
      }
    };
    renewal = setInterval(renew, Math.max(5, seconds / 4) * 1000);
  }

  async function openAdmin(tab) {
    button.disabled = true;
    status.textContent = "Adminoberfläche wird geöffnet …";
    try {
      const result = await openAdminTask();
      const warning = document.getElementById("warning");
      const revocation = result.revocation || {};
      warning.textContent = revocation.reason === "idp_update_required"
        ? "Das IdP-Modul ist zu alt: Alle Vaultwarden-Sitzungen werden beendet, bis das IdP-Modul aktualisiert ist."
        : revocation.state === "warning" ? "Der automatische Zugriffswiderruf ist gestört. Bitte den Modulstatus prüfen." : "";
      const destination = adminDestination(result);
      const cluster = window.parent.location;
      const embed = !tab && (result.frame_ancestors || []).includes(cluster.origin);
      if (!embed && !tab) {
        // Browsers block tabs opened without a click.
        newTab = true;
        throw new Error("Die Adminoberfläche kann hier nicht eingebettet werden. Bitte in neuem Tab öffnen.");
      }
      const form = document.createElement("form");
      form.method = "POST";
      form.action = destination.href;
      // Inside the application frame; never replace the cluster manager.
      if (embed && !document.getElementById("admin-frame")) {
        const frame = document.createElement("iframe");
        frame.id = frame.name = "admin-frame";
        frame.title = "Vaultwarden Administration";
        document.body.appendChild(frame);
      }
      form.target = embed ? "admin-frame" : tabName;
      form.hidden = true;
      const input = document.createElement("input");
      input.type = "hidden"; input.name = "token"; input.value = result.ticket + ":" + handle;
      form.appendChild(input);
      document.body.appendChild(form);
      form.submit();
      form.remove();
      // Embedded, the page shows only the admin frame
      if (embed) document.body.classList.add("embedded");
      startRenewal(result.session_seconds || 120);
      status.textContent = tab
        ? "Adminoberfläche im neuen Tab geöffnet. Diese Seite offen lassen: sie verlängert die Adminsitzung."
        : "Adminoberfläche geöffnet.";
    } catch (error) {
      if (tab) tab.close();
      status.textContent = error.message || "Adminoberfläche konnte nicht geöffnet werden.";
    } finally {
      button.disabled = false;
      if (newTab) button.textContent = "In neuem Tab öffnen";
    }
  }
  button.addEventListener("click", () => openAdmin(newTab ? window.open("", tabName) : null));
  openAdmin(null);
})();

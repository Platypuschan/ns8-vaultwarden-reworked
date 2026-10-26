/* Uses the authenticated NS8 task/event bridge already used by application UIs. */
(() => {
  "use strict";
  const status = document.getElementById("status");
  const button = document.getElementById("open");
  const tabName = "vaultwarden-admin";
  // SameSite=Strict admin cookies only work in a frame of the same site.
  const site = host => host.split(".").slice(-2).join(".");
  let newTab = false;
  async function openAdmin(tab) {
    button.disabled = true;
    status.textContent = "Adminoberfläche wird geöffnet …";
    let cleanup = () => {};
    try {
      const core = window.parent.core;
      const app = core && core.$children.find(child => typeof child.createModuleTaskForApp === "function");
      const match = /#\/apps\/([a-zA-Z0-9_-]+)/.exec(window.parent.location.hash);
      if (!app || !match) throw new Error("Bitte Vaultwarden über den NS8-Cluster-Manager öffnen.");
      const eventId = crypto.randomUUID();
      const action = "open-admin";
      const result = await new Promise((resolve, reject) => {
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
        }).catch(reject);
      });
      const destination = new URL(result.url);
      if (destination.protocol !== "https:" || destination.pathname !== "/admin/" || destination.username || destination.password)
        throw new Error("Ungültige Adminadresse.");
      const cluster = window.parent.location;
      const embed = (result.frame_ancestors || []).includes(cluster.origin)
        && site(cluster.hostname) === site(destination.hostname);
      if (!embed && !tab) {
        // Browsers block tabs opened without a click.
        newTab = true;
        throw new Error("Die Adminoberfläche kann hier nicht eingebettet werden. Bitte in neuem Tab öffnen.");
      }
      const form = document.createElement("form");
      form.method = "POST";
      form.action = destination.href;
      // Inside the application frame; never replace the cluster manager.
      form.target = embed ? "_self" : tabName;
      form.hidden = true;
      for (const key of ["token"]) {
        const input = document.createElement("input");
        input.type = "hidden"; input.name = key; input.value = result[key];
        form.appendChild(input);
      }
      document.body.appendChild(form);
      form.submit();
      form.remove();
      result.token = null;
      status.textContent = "Adminoberfläche geöffnet.";
    } catch (error) {
      if (tab) tab.close();
      status.textContent = error.message || "Adminoberfläche konnte nicht geöffnet werden.";
    } finally {
      cleanup();
      button.disabled = false;
      if (newTab) button.textContent = "In neuem Tab öffnen";
    }
  }
  button.addEventListener("click", () => openAdmin(newTab ? window.open("", tabName) : null));
  openAdmin(null);
})();

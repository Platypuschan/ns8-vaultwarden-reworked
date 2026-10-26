# Vorabversion 0.1.0-rc.4

Direkter Adminzugang für jeden NS8-Administrator über den Cluster-Manager. Branch codex/admin-ui, IdP bleibt auf rc.2. Die Runtime enthält zusätzlich zum API-Key-Gate die kleine NS8-Konfigurationsschutz-Erweiterung; runtime-cache.json pinnt den CI-Build per Digest und Rezept-Hash.

1. Prepare prerelease auf dem Branch mit publish=false: Kandidaten bauen und Unit-/Aktions-, Browser-, Protokoll- und NS8-QEMU-Tests durchführen. Keine Release-Promotion.
2. QEMU prüft das Update einer konfigurierten rc.3-Instanz und Neuinstallation; zwei echte NS8-Admins müssen die Adminoberfläche erreichen, Reader und Modul-Selbstverwaltung müssen abgewiesen werden. Normale Einstellungen speichern und Dienst neu starten. Die pasta-Regression bleibt enthalten.
3. Nach grünen Prüfungen PR nach main übernehmen und Prepare prerelease auf main mit publish=true ausführen. Nur wenn alle Jobs erfolgreich sind, werden die getesteten Digests als rc.4 veröffentlicht. Bestehende Versionen bleiben unverändert.
4. Veröffentlichung, genaue Stände und Digests dokumentieren. Kein automatischer Rollout auf die Nutzerinstanz.

Der Nutzerauftrag vom 26.10.2026 verlangt den direkten Zugang für jeden NS8-Administrator ohne zusätzliche Konten/Rollen/Passworteingaben oder Tunnel. Dafür vorhandene NS8-Owner-Rechte und die normale Vaultwarden-Admin-Sitzung verwenden.

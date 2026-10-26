# Vorabversion 0.1.0-rc.5

Adminoberfläche im Anwendungsbereich des Cluster-Managers statt im ganzen Tab; Direktlink zur SSO-Anmeldung dokumentiert. Branch claude/admin-frame, PR #11, IdP bleibt auf rc.2. Die Runtime-Erweiterung NS8_MANAGED_CONFIG schützt zusätzlich `allowed_iframe_ancestors`; runtime-cache.json pinnt den CI-Build per Digest und Rezept-Hash.

1. Prepare prerelease auf dem Branch mit publish=false: Kandidaten bauen und Unit-/Aktions-, Browser-, Protokoll- und NS8-QEMU-Tests durchführen. Keine Release-Promotion.
2. Browserjob: Adminseite im Anwendungsframe bei unveränderter Cluster-Manager-Adresse, neuer Tab bei nicht einbettbarer Adresse, gespeicherter leerer Wert plus Neustart, SSO-Direktlink ohne E-Mail-Schritt. QEMU prüft das Update einer konfigurierten rc.4-Instanz (erlaubte Cluster-Manager-Adressen gesetzt, übrige Konfiguration und Schlüssel unverändert), Neuinstallation und den echten CSP-Header.
3. Nach grünen Prüfungen PR nach main übernehmen und Prepare prerelease auf main mit publish=true ausführen. Nur wenn alle Jobs erfolgreich sind, werden die getesteten Digests als rc.5 veröffentlicht. Bestehende Versionen bleiben unverändert.
4. Veröffentlichung, genaue Stände und Digests dokumentieren. Kein automatischer Rollout auf die Nutzerinstanz.

Nutzerauftrag 26.10.2026: Adminseite im vorgesehenen Frame statt im Tab des Cluster-Managers öffnen; prüfen, ob sich der Login vereinfachen lässt. Freigabe 26.10.2026: „wenn ci grün ist, merge und mach rc.5“.

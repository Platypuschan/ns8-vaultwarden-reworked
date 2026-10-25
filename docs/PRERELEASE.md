# Vorabversion 0.1.0-rc.2 vorbereiten

Arbeitsbranch: `claude/reworked-hardening` ([PR #3](https://github.com/Platypuschan/ns8-vaultwarden-reworked/pull/3)). Getestete Anwendungsstände unverändert: Keycloak 26.7.4, Vaultwarden 1.37.2 mit API-Key-Patch. Das Runtime-Rezept ist unverändert (`runtime-2c01b1a830e44679`): der Workflow verwendet die mit 0.1.0-rc.1 gebaute und geprüfte Runtime `sha256:80b2af497a96748cf9c34030ccaa4455d6535d69669e11c1bd2eeceb2a4fc0e3` wieder, kein neuer Rust-Build. Der vorige Ablauf ist in [RELEASE-0.1.0-rc.1.md](RELEASE-0.1.0-rc.1.md) belegt.

`IDP_REF` pinnt den IdP-Commit `53c89822fd68`, `IDP_IMAGE` das IdP-Paket `0.1.0-rc.2`. Deshalb zuerst die IdP-Vorabversion veröffentlichen.

Nach ausdrücklicher Nutzerfreigabe der Release-Notizen und nach Veröffentlichung von `idp-reworked:0.1.0-rc.2`:

1. PR #3 nach `main` übernehmen.
2. `Prepare prerelease` auf `main` manuell starten. VERSION erlaubt ausschließlich RC-Versionen.
3. Der Workflow baut Kandidaten (`candidate-<commit>`) und referenziert die Runtime im Modul per Digest.
4. Die echte SSO-Protokollsuite (IdP-Quellstand aus IDP_REF, Keycloak-Runtime aus IDP_IMAGE) und NS8-QEMU auf Debian 13 und Rocky 9 müssen erfolgreich sein. Die NS8-Suite prüft dabei auch Widerruf-Timer und die Sperre von `/admin`.
5. Erst nach grünen Prüfungen werden die geprüften Digests auf `0.1.0-rc.2` kopiert und ein GitHub-Prerelease mit RELEASE_NOTES.md erstellt. Vorhandene Versionstags werden nicht überschrieben. Kein `latest`, keine Katalogaufnahme und kein Produktivrollout.
6. Danach die Prüfnachweise in `docs/RELEASE-0.1.0-rc.2.md` festhalten und README sowie Installationsanleitung auf „veröffentlicht“ ändern.

Die Pakete `vaultwarden-reworked` und `vaultwarden-reworked-server` sind bereits öffentlich; neue Tags erben diese Sichtbarkeit. Ein Update von 0.1.0-rc.1 (Admin-Token, Admin-Route, Timer per `update-module.d/70revocation`) prüft der Workflow nicht.

Die Release-Notizen sind keine Behauptung bereits abgeschlossener RC-Tests. Testberichte und lokale Prüfungen werden getrennt dokumentiert.

Die gemeinsame NS8-Suite verwendet einen per Digest gepinnten Python-/SSH-Runner ohne Browserpakete. So bleibt auf GitHub-Runnern Speicherplatz für QEMU und die Modulimages. Der Runner meldet vor dem Test den freien Hostspeicher.

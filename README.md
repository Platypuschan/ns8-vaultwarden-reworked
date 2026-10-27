# ns8-vaultwarden-reworked

Arbeitsstand der Sicherheitshärtung für NethServer 8: Vaultwarden 1.37.4. Zuletzt veröffentlicht: **0.1.0-rc.5** (noch 1.37.2). Die folgenden Änderungen sind noch nicht veröffentlicht. Vaultwarden mit direktem Adminzugang im Anwendungsbereich des Cluster-Managers, SSO-only und administrativer AD-Gruppenfreigabe über `idp-reworked`.

Ab rc.3 wird ein lokaler IdP unter `pasta` automatisch über Podmans Host-Gateway erreicht. Die Zuordnung wird bei jedem Dienststart erneuert. [Netzwerkkorrektur und Update von rc.2](docs/NETWORK-FIX.md).

Die Runtime sperrt zusätzlich persönliche API-Key-Gerätelogins im SSO-only-Modus. Mitgliedschaft wird durch den IdP bei neuen Anmeldungen und Token-Erneuerung geprüft. Ein Timer des Moduls meldet alle zwei Minuten Benutzer ab, die nicht mehr in der Gruppe sind, ohne administrative Kontosperren zu verändern ([Widerruf](docs/INSTALL-IDP.md#widerruf-bestehender-sitzungen)). Offline-Tresore auf den Geräten lassen sich serverseitig nicht löschen.

- [Installation und Aktivierung](docs/INSTALL-IDP.md)
- [Release-Prüfnachweise und Image-Digests](docs/RELEASE-0.1.0-rc.5.md) ([rc.4](docs/RELEASE-0.1.0-rc.4.md), [rc.1](docs/RELEASE-0.1.0-rc.1.md))
- [Release-Ablauf](docs/PRERELEASE.md)
- [Historische Prototyp-Prüfnachweise](docs/TESTING.md)
- Entscheidungen: [ADR 0003 Widerruf-Timer](docs/decisions/0003-revocation-timer.md)

Eigenständige Paketnamen: `ghcr.io/platypuschan/vaultwarden-reworked` und `ghcr.io/platypuschan/vaultwarden-reworked-server`. Getestet mit `ghcr.io/platypuschan/idp-reworked:0.1.0-rc.2`. Keine Stable-/Katalogfreigabe, keine automatische Migration bestehender Module. Die Pakete sind öffentlich abrufbar; die gemeinsame NS8-Installation ist auf Debian 13 und Rocky 9 geprüft.

Jeder NS8-Administrator öffnet die Vaultwarden-Adminoberfläche direkt über das Modul im Cluster-Manager. Normale Servereinstellungen sind speicherbar; die von NS8 verwalteten SSO-Werte bleiben schreibgeschützt.

Die Gruppenregel wird in der Oberfläche des IdP eingestellt (Seite **Zugriff**, ab IdP 0.1.0-rc.2), Vaultwarden selbst per API. Daten liegen im Modulvolume `vaultwarden-data`, Zugangsdaten ausschließlich im privaten Modul-State. Physische Android-/Biometrieprüfung und vollständige Cluster-Wiederherstellung sind noch offen.

Details zum neuen Adminzugang, erforderlichen IdP-Stand und den bewussten Zurückstellungen: [ADR 0006](docs/decisions/0006-security-decisions.md).

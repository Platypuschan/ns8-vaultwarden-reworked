# ns8-vaultwarden-reworked

Vaultwarden 1.37.4 für NethServer 8, Version **0.1.0-rc.8**: direkter Adminzugang im Anwendungsbereich des Cluster-Managers, SSO-only und administrative AD-Gruppenfreigabe über `idp-reworked` (ab 0.1.0-rc.4).

Ab rc.3 wird ein lokaler IdP unter `pasta` automatisch über Podmans Host-Gateway erreicht. Die Zuordnung wird bei jedem Dienststart erneuert. [Netzwerkkorrektur und Update von rc.2](docs/NETWORK-FIX.md).

Die Runtime sperrt zusätzlich persönliche API-Key-Gerätelogins im SSO-only-Modus. Mitgliedschaft wird durch den IdP bei neuen Anmeldungen und Token-Erneuerung geprüft. Ein Timer des Moduls meldet alle zwei Minuten Benutzer ab, die nicht mehr in der Gruppe sind, ohne administrative Kontosperren zu verändern ([Widerruf](docs/INSTALL-IDP.md#widerruf-bestehender-sitzungen)). Offline-Tresore auf den Geräten lassen sich serverseitig nicht löschen.

- [Installation und Aktivierung](docs/INSTALL-IDP.md)
- [Release-Prüfnachweise und Image-Digests](docs/RELEASE-0.1.0-rc.6.md) ([rc.5](docs/RELEASE-0.1.0-rc.5.md), [rc.4](docs/RELEASE-0.1.0-rc.4.md), [rc.1](docs/RELEASE-0.1.0-rc.1.md))
- [Release-Ablauf](docs/PRERELEASE.md)
- [Historische Prototyp-Prüfnachweise](docs/TESTING.md)
- Entscheidungen: [ADR 0003 Widerruf-Timer](docs/decisions/0003-revocation-timer.md)

Eigenständige Paketnamen: `ghcr.io/platypuschan/vaultwarden-reworked` und `ghcr.io/platypuschan/vaultwarden-reworked-server`. Benötigt `ghcr.io/platypuschan/idp-reworked:0.1.0-rc.4` oder neuer; den IdP zuerst aktualisieren. Keine Stable-/Katalogfreigabe, keine automatische Migration bestehender Module. Die Pakete sind öffentlich abrufbar; die gemeinsame NS8-Installation ist auf Debian 13 und Rocky 9 geprüft.

Jeder NS8-Administrator öffnet die Vaultwarden-Adminoberfläche direkt über das Modul im Cluster-Manager. Dafür stellt NS8 ein einmaliges, 60 Sekunden gültiges Ticket aus; Vaultwarden erhält kein NS8-Anmeldetoken. Solange die Modulseite geöffnet ist, verlängert sie die Adminsitzung. Nach Entzug der NS8-Rechte endet die Sitzung spätestens nach zwei Minuten. Normale Servereinstellungen sind speicherbar; die von NS8 verwalteten SSO-Werte bleiben schreibgeschützt.

Die Gruppenregel wird in der Oberfläche des IdP eingestellt (Seite **Zugriff**, ab IdP 0.1.0-rc.2), Vaultwarden selbst per API. Daten liegen im Modulvolume `vaultwarden-data`, Zugangsdaten ausschließlich im privaten Modul-State. Physische Android-/Biometrieprüfung und vollständige Cluster-Wiederherstellung sind noch offen.

Details zum neuen Adminzugang, erforderlichen IdP-Stand und den bewussten Zurückstellungen: [ADR 0006](docs/decisions/0006-security-decisions.md).

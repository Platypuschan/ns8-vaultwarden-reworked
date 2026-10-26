# ns8-vaultwarden-reworked

Veröffentlichte Vorabversion **0.1.0-rc.3** für NethServer 8. Vaultwarden 1.37.2 mit SSO-only und administrativer AD-Gruppenfreigabe über `idp-reworked`.

Ab rc.3 wird ein lokaler IdP unter `pasta` automatisch über Podmans Host-Gateway erreicht. Die Zuordnung wird bei jedem Dienststart erneuert. [Netzwerkkorrektur und Update von rc.2](docs/NETWORK-FIX.md).

Die Runtime sperrt zusätzlich persönliche API-Key-Gerätelogins im SSO-only-Modus. Mitgliedschaft wird durch den IdP bei neuen Anmeldungen und Token-Erneuerung geprüft. Ein Timer des Moduls deaktiviert alle zwei Minuten die Vaultwarden-Konten von Benutzern, die nicht mehr in der Gruppe sind, und beendet so auch bestehende Sitzungen ([Widerruf](docs/INSTALL-IDP.md#widerruf-bestehender-sitzungen)). Offline-Tresore auf den Geräten lassen sich serverseitig nicht löschen.

- [Installation und Aktivierung](docs/INSTALL-IDP.md)
- [Release-Prüfnachweise und Image-Digests](docs/RELEASE-0.1.0-rc.3.md) ([0.1.0-rc.1](docs/RELEASE-0.1.0-rc.1.md))
- [Release-Ablauf](docs/PRERELEASE.md)
- [Historische Prototyp-Prüfnachweise](docs/TESTING.md)
- Entscheidungen: [ADR 0003 Widerruf-Timer](docs/decisions/0003-revocation-timer.md)

Eigenständige Paketnamen: `ghcr.io/platypuschan/vaultwarden-reworked` und `ghcr.io/platypuschan/vaultwarden-reworked-server`. Getestet mit `ghcr.io/platypuschan/idp-reworked:0.1.0-rc.2`. Keine Stable-/Katalogfreigabe, keine automatische Migration bestehender Module. Die Pakete sind öffentlich abrufbar; die gemeinsame NS8-Installation ist auf Debian 13 und Rocky 9 geprüft.

Die Gruppenregel wird in der Oberfläche des IdP eingestellt (Seite **Zugriff**, ab IdP 0.1.0-rc.2), Vaultwarden selbst per API. Daten liegen im Modulvolume `vaultwarden-data`, Zugangsdaten ausschließlich im privaten Modul-State. Physische Android-/Biometrieprüfung und vollständige Cluster-Wiederherstellung sind noch offen.

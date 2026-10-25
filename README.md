# ns8-vaultwarden-reworked

Vorbereitung der Vorabversion **0.1.0-rc.1** für NethServer 8. Vaultwarden 1.37.2 mit SSO-only und administrativer AD-Gruppenfreigabe über `idp-reworked`.

Die Runtime sperrt zusätzlich persönliche API-Key-Gerätelogins im SSO-only-Modus. Mitgliedschaft wird durch den IdP bei neuen Anmeldungen und Token-Erneuerung geprüft; bestehende Offline-Tresore werden dadurch nicht gelöscht.

- [Installation und Aktivierung](docs/INSTALL-IDP.md)
- [Release-Ablauf](docs/PRERELEASE.md)
- [Historische Prototyp-Prüfnachweise](docs/TESTING.md)

Eigenständige Paketnamen: `ghcr.io/platypuschan/vaultwarden-reworked` und `ghcr.io/platypuschan/vaultwarden-reworked-server`. Benötigt `ghcr.io/platypuschan/idp-reworked:0.1.0-rc.1`. Keine Stable-/Katalogfreigabe, keine automatische Migration bestehender Module. Die Pakete werden erst nach ausdrücklicher Freigabe gebaut und veröffentlicht.

Konfiguration derzeit per API. Daten liegen im Modulvolume `vaultwarden-data`, Zugangsdaten ausschließlich im privaten Modul-State. Physische Android-/Biometrieprüfung und vollständige Cluster-Wiederherstellung sind noch offen.

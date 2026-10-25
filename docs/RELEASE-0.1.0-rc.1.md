# Vaultwarden Reworked 0.1.0-rc.1

Veröffentlicht am 25.10.2026 als Vorabversion, kein Stable-/Katalogrelease.

- [Release](https://github.com/Platypuschan/ns8-vaultwarden-reworked/releases/tag/0.1.0-rc.1)
- Geprüfter Release-Commit: 3c3fa71d323f1035b592409cad54892f9747ea07.
- Abhängigkeit: IdP Reworked 0.1.0-rc.1, Release-Commit fb4b4a4fd4562f18dec9efe42014a7c4bac2620e (IDP_REF/IDP_IMAGE).
- [Build, Protokoll, QEMU und Freigabe](https://github.com/Platypuschan/ns8-vaultwarden-reworked/actions/runs/40227523583): abschließend success. 15 echte Samba/Keycloak/Vaultwarden-Protokolltests grün; Debian13 und Rocky9 je 9/9 gemeinsame Modultests auf Core 3.23.2. Erfolgreiche Jobs wurden beim gezielten Rocky-Infrastruktur-Retry wiederverwendet.
- [Konfigurationsprüfung](https://github.com/Platypuschan/ns8-vaultwarden-reworked/actions/runs/40227523646): 7 Konfigurations-/Bindungstests und Syntaxprüfung grün; diese Prüfungen sind außerdem Teil des erfolgreichen Release-Buildjobs.

| Image | Digest |
| --- | --- |
| ghcr.io/platypuschan/vaultwarden-reworked:0.1.0-rc.1 | sha256:f42c5dae61064233b51c112df598dc050de7dff94f0959bff8e8c31eb4ecc388 |
| ghcr.io/platypuschan/vaultwarden-reworked-server:0.1.0-rc.1 | sha256:80b2af497a96748cf9c34030ccaa4455d6535d69669e11c1bd2eeceb2a4fc0e3 |

Beide Images unabhängig anonym aus GHCR geprüft, amd64. Das Modul referenziert den Runtime per Digest und besitzt die Rolle idp-reworked@any:clientadm. RC-Tags entsprechen den geprüften Kandidaten. Release-Notizen stimmen exakt mit der Nutzerfreigabe überein.

## Build- und Testprovenienz

Der gepatchte Rust-Runtime wurde im [Buildlauf 40217602527](https://github.com/Platypuschan/ns8-vaultwarden-reworked/actions/runs/40217602527) neu kompiliert (10m07s). Für spätere reine Testtreiberkorrekturen wurde exakt dieser Digest wiederverwendet; runtime-cache.json bindet ihn an den unveränderten Hash von Containerfile und Patch. Geänderte Runtime-Rezepte werden neu gebaut.

Zwei Infrastruktur-/Testtreiberprobleme wurden vor der Freigabe behoben: Robot muss die lokale Datei mit OperatingSystem.Get File lesen; die SSH-only-Suite braucht kein großes Browserimage. Dieses hatte auf einem Rocky-Runner den Hostspeicher ausgeschöpft. Der schlanke, gepinnte Python-Runner hatte vor Testbeginn 7.5 GB (Debian) bzw. 6.3 GB (Rocky) frei. Ein weiterer Rocky-Runner blieb schon in APT stehen und wurde gezielt ersetzt; dies war kein bestandener Modultest. Erst der abschließend erfolgreiche Lauf führte zur RC-Promotion.

Keine Produktivinstanz wurde verändert. Physische Mobilgeräte/Biometrie, Migration alter Passwortkonten und vollständige Cluster-Wiederherstellung sind nicht geprüft. Offline-Tresore werden durch Gruppenentzug nicht gelöscht.

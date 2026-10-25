# Vaultwarden Reworked 0.1.0-rc.2

Veröffentlicht am 26.10.2026 als Vorabversion, kein Stable-/Katalogrelease. Release-Notizen vom Nutzer am 25.10.2026 unverändert freigegeben.

- [Release](https://github.com/Platypuschan/ns8-vaultwarden-reworked/releases/tag/0.1.0-rc.2)
- Geprüfter Release-Commit: 83859ade1580446e21de023beeddf99d4b299ee8 (Merge von [PR #3](https://github.com/Platypuschan/ns8-vaultwarden-reworked/pull/3) und [PR #4](https://github.com/Platypuschan/ns8-vaultwarden-reworked/pull/4)).
- Abhängigkeit: IdP Reworked 0.1.0-rc.2, `IDP_REF` 53c89822fd682043f54cf5bfd2543f85f052bada, `IDP_IMAGE` idp-reworked:0.1.0-rc.2.
- [Build, Protokoll, QEMU und Freigabe](https://github.com/Platypuschan/ns8-vaultwarden-reworked/actions/runs/40242897212): vollständig erfolgreich. 15 echte Samba/Keycloak/Vaultwarden-Protokolltests grün, darunter der Widerruf mit echter Admin-API. Debian13 und Rocky9 je 10/10 gemeinsame Modultests auf Core 3.23.2, darunter „Revocation timer and private admin pages“ (Timer aktiv, `/admin` 403 von der Knotenadresse, Timer-Lauf mit LDAP-Bind und Admin-Login).

| Image | Digest |
| --- | --- |
| ghcr.io/platypuschan/vaultwarden-reworked:0.1.0-rc.2 | sha256:98588fe8f664676a70702a781667c2d35baa97d6988e3b0ca2fe0715d4778129 |
| ghcr.io/platypuschan/vaultwarden-reworked-server:0.1.0-rc.2 | sha256:80b2af497a96748cf9c34030ccaa4455d6535d69669e11c1bd2eeceb2a4fc0e3 |

Beide Images unabhängig anonym aus GHCR geprüft. Das Modul referenziert die Runtime per Digest. RC-Digests entsprechen den geprüften Kandidaten (`candidate-83859ade1580`). Die Runtime ist unverändert die mit 0.1.0-rc.1 gebaute (Rezept `runtime-2c01b1a830e44679`). Der GitHub-Release-Text stimmt exakt mit RELEASE_NOTES.md überein.

## Build- und Testprovenienz

Der erste Release-Lauf [40241642756](https://github.com/Platypuschan/ns8-vaultwarden-reworked/actions/runs/40241642756) brach im Protokoll-Job ab: der neue Widerrufstest braucht `ldap3`, das der Job nicht installierte (14 übrige Protokolltests grün, beide QEMU-Suiten 10/10). Es wurde nichts veröffentlicht. PR #4 ergänzt nur diese Testabhängigkeit; der danach vollständig erfolgreiche Lauf führte zur RC-Promotion.

Nicht geprüft: Update einer NS8-Installation von 0.1.0-rc.1 (`update-module.d/70revocation`), physische Mobilgeräte/Biometrie, vollständige Cluster-Wiederherstellung. Offline-Tresore auf den Geräten lassen sich serverseitig weder löschen noch sperren.

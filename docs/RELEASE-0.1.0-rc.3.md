# Vaultwarden Reworked 0.1.0-rc.3

Veröffentlicht am 26.10.2026 als Vorabversion. Behebt die lokale IdP-Verbindung unter pasta; IdP bleibt auf 0.1.0-rc.2. Kein Stable-/Katalogrelease und kein automatischer Rollout auf die Nutzerinstanz.

- [Release](https://github.com/Platypuschan/ns8-vaultwarden-reworked/releases/tag/0.1.0-rc.3)
- Release-/Testcommit: e0b016e9cc4c42620a8d6e0ce9295de107ed081f, [PR #6](https://github.com/Platypuschan/ns8-vaultwarden-reworked/pull/6).
- [Finaler Build, Tests und Veröffentlichung](https://github.com/Platypuschan/ns8-vaultwarden-reworked/actions/runs/40391594553): vollständig erfolgreich. 25 Unit-/Aktionsprüfungen, 15 echte Samba/Keycloak/Vaultwarden-Protokolltests, NS8 Core 3.23.2 auf Debian13 und Rocky9 jeweils 14/14 Modultests, keine Skips.
- Beide NS8-Gäste prüfen das echte Update einer aktivierten rc.2-Instanz unter Erhalt der SSO-Konfiguration und des RSA-Schlüssels, eine frische Kandidateninstallation, Discovery aus der App nach Containerneuerstellung und drei pasta-/TLS-Regressionen mit vertrauenswürdigem Testzertifikat (einschließlich Zertifikatsablehnung).
- [Vorheriger Kandidatenlauf](https://github.com/Platypuschan/ns8-vaultwarden-reworked/actions/runs/40388965311) am b1dcb70 ebenfalls vollständig erfolgreich, vor der zusätzlichen Erhaltsprüfung.

| Image | Digest |
| --- | --- |
| ghcr.io/platypuschan/vaultwarden-reworked:0.1.0-rc.3 | sha256:6d924364e220058ba8d6cd4739e4c1df35aa5008b661ebb471bf9568c2d656d6 |
| ghcr.io/platypuschan/vaultwarden-reworked-server:0.1.0-rc.3 | sha256:80b2af497a96748cf9c34030ccaa4455d6535d69669e11c1bd2eeceb2a4fc0e3 |

Beide Tags unabhängig anonym über die GHCR-API abgerufen: Manifest-Digests und -Inhalte entsprechen exakt candidate-e0b016e9cc4c. Modul referenziert die Runtime per Digest. Runtime unverändert; der GitHub-Release-Text stimmt mit RELEASE_NOTES.md überein, der Tag zeigt auf den getesteten Commit.

Update und Entfernung des spezifischen Test-Drop-ins: [NETWORK-FIX.md](NETWORK-FIX.md). Auf der Nutzerinstanz wurde dieses Paket noch nicht durch Codex installiert. Noch offen: echter Mehrknoten-SSO-Ablauf und vollständige Cluster-Wiederherstellung. Die lokale Hostzuordnung für entfernte IdPs wird per Unit-Test ausgeschlossen. Offline-Tresore bleiben auf den Geräten.

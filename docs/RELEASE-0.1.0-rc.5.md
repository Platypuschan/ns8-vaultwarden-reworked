# Vaultwarden Reworked 0.1.0-rc.5

Veröffentlicht am 27.10.2026, 00:01:48 UTC, als Vorabversion. Die Adminoberfläche öffnet sich im Anwendungsbereich des Cluster-Managers, statt den ganzen Browser-Tab zu ersetzen. Direktlink zur SSO-Anmeldung ohne E-Mail-Schritt dokumentiert. IdP bleibt auf rc.2.

- [Release](https://github.com/Platypuschan/ns8-vaultwarden-reworked/releases/tag/0.1.0-rc.5)
- Release-/Testcommit: 51a496a735c1e0eabf34dcf8d757721ea3d44041, [PR #11](https://github.com/Platypuschan/ns8-vaultwarden-reworked/pull/11). Freigabe durch den Nutzer am 26.10.2026: „wenn ci grün ist, merge und mach rc.5“.
- [Finaler Build, Tests und Veröffentlichung](https://github.com/Platypuschan/ns8-vaultwarden-reworked/actions/runs/40420261781): erfolgreich. 29 Unit-/Aktionsprüfungen, Browserjob, 16 echte Samba/Keycloak/Vaultwarden-Protokolltests und NS8 Core 3.23.2 Debian13/Rocky9 jeweils 15/15 ohne Skip.
- [Kandidatenlauf](https://github.com/Platypuschan/ns8-vaultwarden-reworked/actions/runs/40416938983) am Branch-Stand 27b0ca8 ebenfalls vollständig erfolgreich. Der [erste Kandidatenlauf](https://github.com/Platypuschan/ns8-vaultwarden-reworked/actions/runs/40413725885) scheiterte nur im Updatetest, der die neue Variable `ALLOWED_IFRAME_ANCESTORS` noch nicht kannte; Test korrigiert und auf Update von rc.4 umgestellt. Aus diesem Lauf stammt die Runtime (Rezept runtime-0091487de439428f), anschließend per Digest wiederverwendet.
- Browserjob mit echtem Vaultwarden: Adminseite im Anwendungsframe bei unveränderter Cluster-Manager-Adresse für zwei Owner, Einstellungen speichern inkl. leerem `allowed_iframe_ancestors` und Neustart (Einbetten funktioniert weiter), Reader-Verweigerung, nicht einbettbare Adresse öffnet nach Klick einen neuen Tab, SSO-Direktlink erreicht `/identity/connect/authorize` ohne E-Mail-Eingabe.
- NS8-QEMU: Update einer konfigurierten rc.4-Instanz setzt die erlaubten Cluster-Manager-Adressen, übrige Konfiguration und RSA-Schlüssel unverändert. Für echte NS8-Administratoren enthält `open-admin` die Knotenadressen, und der echte CSP-Header von Vaultwarden erlaubt sie. Ein gespeicherter leerer Wert bleibt nicht in `config.json`.

| Image | Digest |
| --- | --- |
| ghcr.io/platypuschan/vaultwarden-reworked:0.1.0-rc.5 | sha256:951a2015da57435cbcfb870a0ba10445448dc0fc768963bb75cb8bb4c52ab382 |
| ghcr.io/platypuschan/vaultwarden-reworked-server:0.1.0-rc.5 | sha256:6030f655f6840dbcd9b432226a99336ec7766dee81a689a02bed75fac2f0f080 |

Beide Tags anonym über die GHCR-API geprüft, digestidentisch zu candidate-51a496a735c1. Das Modul pinnt die Runtime per Digest. Tag zeigt auf den geprüften Commit.

## Update und Nutzung

Als root auf dem NS8-Host, tatsächliche Modul-ID verwenden:

```bash
api-cli run cluster/update-module --data \
  '{"module_url":"ghcr.io/platypuschan/vaultwarden-reworked:0.1.0-rc.5","instances":["vaultwarden-reworked1"]}'
```

Cluster-Manager neu laden und Anwendungen → Vaultwarden öffnen. Die Adminseite erscheint im Anwendungsbereich. Läuft der Cluster-Manager unter einer anderen Domain oder Adresse als die Knoten-FQDN, erscheint **In neuem Tab öffnen**.

Direktlink für Benutzer: `https://<vaultwarden-host>/#/sso?identifier=00000000-01DC-01DC-01DC-000000000000`. Danach nur IdP-Anmeldung (Name oder E-Mail und AD-Passwort) und Masterpasswort zum Entsperren.

Kein automatischer Rollout auf die Nutzerinstanz. Auf der Nutzerinstanz nicht geprüft. Weiterhin nicht nachgewiesen: vollständige Cluster-Wiederherstellung, echter Mehrknoten-SSO-Ablauf. Kein Stable-/Katalogrelease. Offline-Tresore bleiben auf den Geräten.

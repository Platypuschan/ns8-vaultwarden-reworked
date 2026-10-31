# Vaultwarden Reworked 0.1.0-rc.8

Vorabversion vom 31.10.2026: Bereits angemeldete Geräte behalten ihre Sitzung nach Ende der IdP-Sitzung. IdP bleibt bei 0.1.0-rc.4; keine zusätzliche IdP-Veröffentlichung erforderlich.

## Veröffentlichung und Prüfungen

- [Release](https://github.com/Platypuschan/ns8-vaultwarden-reworked/releases/tag/0.1.0-rc.8): veröffentlicht am 31.10.2026 um 06:44:44 UTC.
- [PR18](https://github.com/Platypuschan/ns8-vaultwarden-reworked/pull/18) gemergt; Release-/Testcommit `6ffd0cc28cef2fc4f1318efa71a72d05e0b65596`. Git-Tag zeigt exakt auf diesen Commit.
- [Finaler Release-Lauf 41176198394](https://github.com/Platypuschan/ns8-vaultwarden-reworked/actions/runs/41176198394): vollständig erfolgreich. 39 Unit-/Aktionsprüfungen, Syntax, 17 echte Samba-AD/Keycloak/Vaultwarden-Protokolltests, Admin-Sicherheits-/Browsertests und NS8 Core 3.23.2 auf Debian13/Rocky9 jeweils **18/18 ohne Skip**.
- NS8: Installation und IdP-Update, Upgrade einer konfigurierten Vaultwarden-Installation über rc.7 auf rc.8, wirksames `SSO_AUTH_ONLY_NOT_SESSION=true` im laufenden Container, übrige SSO-Werte und RSA-Schlüssel erhalten, Neuinstallation, Gruppenpolicy, Widerrufsdienst, Adminrechte, Backup/Neustart, Entfernen.
- Neuer Protokolltest: Gerät anmelden, alle zugehörigen Keycloak-Sitzungen löschen, Geräte-Refresh ohne Browser, Vaultwarden neu starten und erneut Geräte-Refresh. Bestehender Gruppenentzugstest invalidiert das Gerät weiterhin. Gegenprobe mit der vorherigen Sitzungskonfiguration scheitert genau im neuen Test mit `invalid_grant`.
- [Erster Kandidatenlauf 41173742048](https://github.com/Platypuschan/ns8-vaultwarden-reworked/actions/runs/41173742048) am Stand `33f76cf`: Anwendungsprüfungen und Debian18/18 erfolgreich; Rocky scheiterte zweimal vor Modultests wegen HTTP404 für vom NethServer-Mirror angekündigte BaseOS-Metadaten. Deshalb verwendet ausschließlich die disposable Rocky-Test-VM einen gepinnten/checksummierten NS8-Installer mit offiziellen Rocky-Paketrepositories und aktiver Signaturprüfung. Das ausgelieferte Modul ändert keine Host-Paketrepositories. Der finale Rocky-Lauf ist mit diesem dokumentierten CI-Bootstrap vollständig grün.

| Image | Digest |
| --- | --- |
| `ghcr.io/platypuschan/vaultwarden-reworked:0.1.0-rc.8` | `sha256:bba5a69fd430429d9e3f6313b7625e6b797826184ff744e466ec0f5aaddb7caa` |
| `ghcr.io/platypuschan/vaultwarden-reworked-server:0.1.0-rc.8` | `sha256:7c510ee9a9a689aef8d8f64ab846d6b223e5181227dd431c9885d02ca8b1ac87` |

Beide Tags anonym über die GHCR-Registry-API geprüft; Digests stimmen exakt mit `candidate-6ffd0cc28cef` überein. Das Modul pinnt die Runtime auf diesen Digest. IdP bleibt unverändert rc.4.

## Update und Android-Test

Als root auf dem NS8-Host (tatsächliche Modul-ID einsetzen):

```bash
api-cli run cluster/update-module --data '{"module_url":"ghcr.io/platypuschan/vaultwarden-reworked:0.1.0-rc.8","instances":["vaultwarden-reworked1"]}'
```

IdP muss bereits mindestens rc.4 sein. Nach dem Update nötigenfalls einmal erneut über SSO anmelden, Masterpasswort/Biometrie verwenden und als Tresor-Timeout-Aktion **Sperren** wählen. App sperren, schließen und später wieder öffnen: Der Tresor soll lokal entsperrbar bleiben. **Abmelden** beendet dagegen absichtlich die Geräteanmeldung.

Neue Geräte verlangen weiter SSO. Gruppenentzug wirkt über den zweiminütigen AD-Widerrufsdienst. Bei dessen Ausfall bzw. fehlgeschlagenen LDAP-/IdP-Abfragen gibt es keine zusätzliche kurze IdP-Ablaufgrenze für vorhandene Geräte; Widerrufsstatus überwachen. [Entscheidung und Grenzen](decisions/0008-persistent-device-sessions.md).

Kein automatischer Rollout auf die Nutzerinstanz; physische Android-/Biometrie-Oberfläche noch nicht live geprüft. Kein Stable-/Katalogrelease.

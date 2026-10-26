# Vaultwarden Reworked 0.1.0-rc.4

Veröffentlicht am 26.10.2026, 22:03:28 UTC, als Vorabversion. Jeder NS8-Administrator erreicht die Adminoberfläche beim Öffnen von Vaultwarden im Cluster-Manager automatisch. Keine neue Rolle, kein zusätzliches Konto, keine manuelle Token-Eingabe und kein Tunnel erforderlich. IdP bleibt auf rc.2.

- [Release](https://github.com/Platypuschan/ns8-vaultwarden-reworked/releases/tag/0.1.0-rc.4)
- Release-/Testcommit: 6b2c2260d9ae759b6486c160ba220039cdb1dcef, [PR #9](https://github.com/Platypuschan/ns8-vaultwarden-reworked/pull/9).
- [Finaler Build, Tests und Veröffentlichung](https://github.com/Platypuschan/ns8-vaultwarden-reworked/actions/runs/40404641244): erfolgreich. 27 Unit-/Aktionsprüfungen, Browserjob, 16 echte Samba/Keycloak/Vaultwarden-Protokolltests und NS8 Core 3.23.2 Debian13/Rocky9 jeweils 15/15 ohne Skip.
- Der Browserjob verwendet echtes Vaultwarden und einen isolierten NS8-Task-Bridge-Vertrag: automatische Anmeldung zweier Owner-Identitäten, Secure/HttpOnly-Cookie, Benutzerverwaltung, Einstellungen speichern/Neustart, Reader-Verweigerung und Schutz der NS8-Werte. Der verwendete Task-Aufruf wurde zusätzlich mit der originalen NS8-UI-Bibliothek 2.2.0 (Core 3.23.2) abgeglichen.
- Die NS8-QEMU-Suite prüft echte NS8-Authentifizierung/Berechtigungen mit zwei temporären Administratoren: beide erreichen die Adminoberfläche; ein Reader und Modul-Selbstverwaltung werden abgewiesen. Normale Admin-Einstellungen werden gespeichert, der echte systemd-Dienst neu gestartet und der zweite Administrator kann sich weiterhin anmelden. Außerdem echtes rc.3-Update mit Erhalt der bisherigen SSO-Konfiguration und des RSA-Schlüssels, Neuinstallation, pasta/TLS, Widerruf-Timer, Backup/Neustart und Entfernung.
- Rocky wurde nach einer langsamen Runner-Vorbereitung vor dem NS8-Start allein erneut ausgeführt (Versuch 2). Build, Browser, Protokoll und Debian blieben erfolgreich erhalten; Commit und Kandidaten unverändert. Erst danach Release-Promotion.
- [Vorheriger Kandidatenlauf](https://github.com/Platypuschan/ns8-vaultwarden-reworked/actions/runs/40402113124) ebenfalls vollständig erfolgreich, vor den zusätzlichen Burst-/Dokuänderungen am Modul.

| Image | Digest |
| --- | --- |
| ghcr.io/platypuschan/vaultwarden-reworked:0.1.0-rc.4 | sha256:5a67c6ad3dbfe128153ba729353bab44204565036871a753a9460a047915a1ae |
| ghcr.io/platypuschan/vaultwarden-reworked-server:0.1.0-rc.4 | sha256:3ab27a31a8c2e8b7f1d1463bdf7ae0def7a2253cc80e9c9985fa18c292da6e03 |

Beide Tags unabhängig anonym über die GHCR-API geprüft. Manifest-Inhalte und Digests entsprechen exakt candidate-6b2c2260d9ae. Das Modul pinnt die neue Runtime per Digest. Tag und Release-Text entsprechen dem geprüften Commit bzw. RELEASE_NOTES.md.

Die Runtime wurde im Buildjob von 40399528842 aus dem Rezept runtime-7ff5cdb5e8c784f5 erstellt und anschließend per Digest wiederverwendet. Der erste Protokolljob hatte einen Testfehler (CompletedProcess statt stdout beim JSON-Lesen), der korrigiert wurde. Die tatsächlichen Runtime-/Browser-/Protokollprüfungen sind im finalen Lauf erfolgreich.

## Update und Nutzung

Als root auf dem NS8-Host, tatsächliche Modul-ID verwenden:

```bash
api-cli run cluster/update-module --data \
  '{"module_url":"ghcr.io/platypuschan/vaultwarden-reworked:0.1.0-rc.4","instances":["vaultwarden-reworked1"]}'
```

Cluster-Manager neu laden und Anwendungen → Vaultwarden öffnen. Die bestehende NS8-Anmeldung wird für den automatischen Einstieg verwendet. Normale Servereinstellungen sind speicherbar; die von NS8 verwalteten SSO- und internen Zugangswerte bleiben schreibgeschützt, damit Anmeldung und Widerruf-Timer weiter funktionieren.

Kein automatischer Rollout auf die Nutzerinstanz. Noch nicht nachgewiesen: vollständige Cluster-Wiederherstellung, echter Mehrknoten-SSO-Ablauf und dieser Paketstand auf der Nutzerinstanz. Kein Stable-/Katalogrelease. Offline-Tresore bleiben auf den Geräten.

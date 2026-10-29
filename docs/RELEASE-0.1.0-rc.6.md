# Vaultwarden Reworked 0.1.0-rc.6

Veröffentlicht am 29.10.2026, 19:34:28 UTC, als Vorabversion. Sicherheitsupdate: Vaultwarden 1.37.4, Adminzugang per Einmalticket statt NS8-Anmeldetoken, an die AD-Gruppe gebundene IdP-Regel, Widerruf ohne Kontosperren. Benötigt **IdP 0.1.0-rc.4**; den IdP zuerst aktualisieren.

- [Release](https://github.com/Platypuschan/ns8-vaultwarden-reworked/releases/tag/0.1.0-rc.6), passender [IdP 0.1.0-rc.4](https://github.com/Platypuschan/ns8-idp-reworked/releases/tag/0.1.0-rc.4) (Merge-Commit 91f119307b8de3c2bf24d8779ce4375059d8ce93, [Release-Lauf](https://github.com/Platypuschan/ns8-idp-reworked/actions/runs/40930659547): Debian13/Rocky9 je 32 PASS + 1 erwarteter Skip).
- Release-/Testcommit: 2348befa132b38f28cd6d8604592bda4f4f62bcc, Merge von [PR #15](https://github.com/Platypuschan/ns8-vaultwarden-reworked/pull/15). Dieser enthält die Sicherheitsumsetzung P1–P21 aus [PR #14](https://github.com/Platypuschan/ns8-vaultwarden-reworked/pull/14) und die Recheck-Korrekturen R1–R8. Freigabe durch den Nutzer am 29.10.2026: „R0: yes do it / R1: switch to one-time ticket“.
- [Finaler Build, Tests und Veröffentlichung](https://github.com/Platypuschan/ns8-vaultwarden-reworked/actions/runs/40937863264): erfolgreich. 38 Unit-/Aktionsprüfungen, 8 Ticketbrücken-Tests gegen die echte gepatchte Runtime, Browserjob, 16 echte Samba/Keycloak/Vaultwarden-Protokolltests und NS8 Core 3.23.2 Debian13/Rocky9 jeweils 17/17 ohne Skip.
- [Kandidatenlauf](https://github.com/Platypuschan/ns8-vaultwarden-reworked/actions/runs/40932986957) am Branch-Stand cfbe9d2 (gegen den veröffentlichten IdP rc.4) ebenfalls vollständig erfolgreich. Der [erste Kandidatenlauf](https://github.com/Platypuschan/ns8-vaultwarden-reworked/actions/runs/40924330790) scheiterte nur an zwei Testerwartungen (neues Berichtsfeld `failed`, neue Variable `NS8_ADMIN_SESSION_SECONDS` im Updatetest); Tests korrigiert. Aus diesem Lauf stammt die Runtime (Rezept runtime-496c3d2bebf5b47e), anschließend per Digest wiederverwendet.
- Ticketbrücke mit echter Runtime: Einmalverwendung, abgelaufenes Ticket abgewiesen, Sitzung endet ohne Erneuerung und bleibt mit Erneuerung, Erneuerung nur mit passendem Handle und Benutzer, fremde Origin abgewiesen (Ticket bleibt unverbraucht), Logout, interner Worker-Zugang, altes `VW_ADMIN`-Cookie allein ohne Wirkung.
- Browserjob: Adminseite im Anwendungsframe für zwei Owner, Einstellungen speichern und Neustart; Sitzung bleibt über ihre Laufzeit hinaus erhalten, solange die Modulseite offen ist, und endet nach Entzug des NS8-Rechts; Reader-Verweigerung; Tab-Modus mit Erneuerung ohne Cookie; Public-Suffix-Fall (`.co.uk`) über expliziten Tab; SSO-Direktlink ohne E-Mail-Schritt.
- NS8-QEMU: Installation von IdP rc.3 und Vaultwarden rc.4, Update des konfigurierten IdP mit erhaltenen Realm-, Client- und Gruppen-IDs sowie Clientsecret, öffentliche Keycloak-Adminpfade gesperrt, Update von Vaultwarden rc.4 (Konfiguration und RSA-Schlüssel unverändert), Neuinstallation, echte NS8-Owner öffnen die Adminseite per Ticket (Einmalverwendung, Erneuerung), Reader und Modul selbst erhalten kein Ticket, nach Owner-Entzug kein neues Ticket und Sitzungsende innerhalb der Laufzeit, Widerruf-Timer, Backup/Neustart, Entfernen.

| Image | Digest |
| --- | --- |
| ghcr.io/platypuschan/vaultwarden-reworked:0.1.0-rc.6 | sha256:ed448b0391a288fe226acb72b5fd54248912dd9fade164082fb08a6cd1b39782 |
| ghcr.io/platypuschan/vaultwarden-reworked-server:0.1.0-rc.6 | sha256:7c510ee9a9a689aef8d8f64ab846d6b223e5181227dd431c9885d02ca8b1ac87 |
| ghcr.io/platypuschan/idp-reworked:0.1.0-rc.4 | sha256:2e32ad12b81f5098175784c5ff5b2ce81fc4df2d520da52b6ea80a7f3c464f23 |
| ghcr.io/platypuschan/idp-reworked-keycloak:0.1.0-rc.4 | sha256:e72729a39a8d743d56ecac83aab72af1ca2708aac20120e7d0bfad34ccf88e27 |

Alle Tags anonym geprüft (`skopeo --no-creds`), digestidentisch zu den getesteten Kandidaten (candidate-2348befa132b bzw. candidate-91f119307b8d). Das Modul pinnt die Runtime per Digest. Die Tags zeigen auf die geprüften Commits.

## Update und Nutzung

Als root auf dem NS8-Host, tatsächliche Modul-IDs verwenden. **Zuerst den IdP, dann Vaultwarden:**

```bash
api-cli run cluster/update-module --data \
  '{"module_url":"ghcr.io/platypuschan/idp-reworked:0.1.0-rc.4","instances":["idp-reworked1"]}'
api-cli run cluster/update-module --data \
  '{"module_url":"ghcr.io/platypuschan/vaultwarden-reworked:0.1.0-rc.6","instances":["vaultwarden-reworked1"]}'
```

Wird Vaultwarden zuerst aktualisiert, bricht dessen Update mit dem Hinweis „Update the IdP module first“ ab, und der Widerruf-Timer beendet alle Vaultwarden-Sitzungen, bis der IdP aktualisiert ist (Warnung auf der Adminseite). Danach Vaultwarden erneut aktualisieren.

Cluster-Manager neu laden und Anwendungen → Vaultwarden öffnen. Die Adminseite erscheint im Anwendungsbereich. Die Modulseite verlängert die Adminsitzung alle 30 Sekunden; wird sie geschlossen oder werden die NS8-Rechte entzogen, endet die Sitzung spätestens nach zwei Minuten. Im Tab-Modus (**In neuem Tab öffnen**) die Modulseite geöffnet lassen. Der beim Update von früheren Versionen offengelegte interne Adminschlüssel wird ersetzt.

Kein automatischer Rollout auf die Nutzerinstanz. Auf der Nutzerinstanz nicht geprüft. Weiterhin nicht nachgewiesen: vollständige Cluster-Wiederherstellung, echter Mehrknoten-SSO-Ablauf, Brute-Force-Schutz (in Planung). Kein Stable-/Katalogrelease. Offline-Tresore bleiben auf den Geräten.

Sechste Vorabversion von Vaultwarden Reworked für NethServer 8. Sicherheitsupdate.

**Zuerst den IdP auf 0.1.0-rc.4 aktualisieren, dann Vaultwarden.** Mit einem älteren IdP meldet Vaultwarden alle Benutzer ab und zeigt einen Hinweis, bis der IdP aktualisiert ist.

- Vaultwarden 1.37.4 (bisher 1.37.2) mit den Sicherheitskorrekturen von 1.37.3 und 1.37.4.
- Adminzugang: NS8 stellt beim Öffnen ein einmaliges, 60 Sekunden gültiges Ticket aus. Vaultwarden erhält weder das NS8-Anmeldetoken noch einen dauerhaften Adminschlüssel. Die Sitzung wird verlängert, solange die Modulseite im Cluster-Manager geöffnet ist. Nach Entzug der NS8-Rechte endet sie spätestens nach zwei Minuten. Beim Öffnen in einem neuen Tab muss die Modulseite geöffnet bleiben.
- Der beim Update von früheren Versionen offengelegte interne Adminschlüssel wird ersetzt.
- Gruppenregel: Vaultwarden bindet die IdP-Regel an seine eingestellte AD-Gruppe. Fehlt die Regel oder wird sie geändert, werden alle Sitzungen beendet, statt den Zugang zu öffnen.
- Widerruf: Benutzer außerhalb der Gruppe werden abgemeldet, ohne Kontosperren zu verändern. Ein einzelner Fehler hält die übrigen Abmeldungen nicht mehr auf. Der Zustand des Widerrufs (letzter Erfolg, Fehler) ist im Modulstatus sichtbar und wird beim Öffnen der Adminoberfläche als Warnung angezeigt.
- Verständliche Meldung, wenn `configure-module` vor `prepare-sso` aufgerufen wird.

Keine Stable- oder Katalogfreigabe; Vorabversion für Testinstallationen. Geprüft mit Unit-, Browser-, Protokoll- und NS8-QEMU-Tests (Debian 13, Rocky 9), einschließlich gemeinsamem Update von IdP rc.3 und Vaultwarden rc.4. Offline-Tresore lassen sich weiterhin nicht serverseitig löschen. Brute-Force-Schutz (in Planung), vollständige Wiederherstellung und Mehrknoten-SSO sind nicht nachgewiesen.

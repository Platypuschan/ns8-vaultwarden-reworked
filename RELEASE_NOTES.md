Zweite Vorabversion des angepassten Vaultwarden-Moduls für NethServer 8.

- Widerruf bestehender Sitzungen: Ein Timer deaktiviert alle zwei Minuten die Vaultwarden-Konten von Benutzern, die nicht mehr direkt in der freigegebenen AD-Gruppe sind, und meldet ihre Geräte ab. Bei erneuter Aufnahme in die Gruppe wird das Konto wieder aktiviert; von Administratoren gesperrte Konten bleiben gesperrt.
- Zufälliger interner Admin-Token nur für diesen Abgleich; Traefik sperrt `/admin` von außen.
- Die Gruppenregel wird in der Oberfläche von `idp-reworked` auf der Seite „Zugriff“ eingestellt.
- Installationen von 0.1.0-rc.1 erhalten Admin-Token, Admin-Route und Timer beim Update.

Getestet mit `idp-reworked:0.1.0-rc.2`; Voraussetzung NS8 Core 3.23.2 oder neuer und direkte Mitgliedschaft in der freigegebenen AD-Gruppe. Vaultwarden selbst wird per API konfiguriert; keine Stable-/Katalogfreigabe. Offline-Tresore auf den Geräten lassen sich serverseitig weder löschen noch sperren. Physische Mobilgeräte und vollständige Cluster-Wiederherstellung sind nicht abgedeckt.

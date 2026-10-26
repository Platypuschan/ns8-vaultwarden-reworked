Vierte Vorabversion von Vaultwarden Reworked für NethServer 8.

Nicht veröffentlicht, nach rc.4:

- Die Adminoberfläche öffnet sich im Anwendungsbereich des Cluster-Managers statt im ganzen Browser-Tab; der Cluster-Manager bleibt offen. Ist Einbetten nicht möglich (andere Domain/Adresse des Cluster-Managers), öffnet eine Schaltfläche einen neuen Tab. Update setzt die erlaubten Cluster-Manager-Adressen automatisch.
- Direktlink zur SSO-Anmeldung ohne E-Mail-Eingabe dokumentiert.

- Jeder NS8-Administrator kann beim Öffnen von Vaultwarden im Cluster-Manager direkt die Adminoberfläche erreichen. Die vorhandene NS8-Anmeldung wird verwendet; kein SSH-Tunnel und kein manuelles Auslesen oder Eingeben eines Admin-Tokens.
- Die Prototyp-Platzhalterseite wird durch den automatischen Admin-Einstieg ersetzt. Administratoren können Benutzer verwalten und normale Servereinstellungen speichern.
- Gespeicherte Admin-Einstellungen bleiben nach einem Neustart erhalten. Die durch NS8 verwalteten SSO- und internen Zugangswerte werden in der Adminoberfläche schreibgeschützt dargestellt und bleiben wirksam.
- Das Update von rc.3 richtet den Adminzugang automatisch ein. Benutzer ohne administrative NS8-Berechtigung erhalten über die Modulaktion keinen Zugang; die Vaultwarden-Adminoberfläche bleibt durch ihre Admin-Sitzung geschützt.
- Enthält die pasta-Korrektur aus rc.3. IdP bleibt auf 0.1.0-rc.2.

Die Veröffentlichung erfolgt nach erfolgreichen Unit-, Browser-, Protokoll- und NS8-QEMU-Prüfungen. Keine Stable-/Katalogfreigabe und kein automatischer Rollout auf die Nutzerinstanz. Offline-Tresore lassen sich weiterhin nicht serverseitig löschen; vollständige Cluster-Wiederherstellung und Mehrknoten-SSO sind nicht nachgewiesen.

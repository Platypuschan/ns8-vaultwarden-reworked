Siebte Vorabversion von Vaultwarden Reworked für NethServer 8. Oberflächenkorrektur, benötigt weiterhin IdP 0.1.0-rc.4.

- Die Adminoberfläche füllt die ganze Anwendungsfläche im Cluster-Manager. Überschrift, Statuszeile und die Schaltfläche **In neuem Tab öffnen** entfallen, sobald die Seite eingebettet ist. Warnungen (gestörter Zugriffswiderruf, nicht verlängerbare Adminsitzung) erscheinen als NethServer-Benachrichtigung.
- Die Schaltfläche **In neuem Tab öffnen** gibt es nur noch, wenn der Cluster-Manager die Seite nicht einbetten darf. Liegen Cluster-Manager und Vaultwarden auf zwei verschiedenen Websites, funktioniert die eingebettete Adminseite nicht; dafür gibt es keinen Ersatz mehr.
- Keine Meldung „Fertig“ mehr alle zwei Minuten: Die regelmäßige Prüfung der IdP-Gruppenregel durch den Widerruf-Timer läuft ohne Benachrichtigung. Fehlgeschlagene Prüfungen meldet NS8 weiterhin.

Keine Stable- oder Katalogfreigabe; Vorabversion für Testinstallationen. Sonst unverändert gegenüber 0.1.0-rc.6.

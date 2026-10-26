Dritte Vorabversion des angepassten Vaultwarden-Moduls für NethServer 8.

- Behebt die lokale IdP-Verbindung unter pasta: Ein IdP auf demselben Knoten wird automatisch über Podmans host-gateway erreicht. Die Zuordnung wird bei jedem Dienststart erneuert; entfernte IdPs behalten ihre normale DNS-Auflösung.
- HTTPS-Hostname, OIDC-Issuer und Zertifikatsprüfung bleiben erhalten. Bei automatischem HTTPS prüft die Konfiguration die Discovery aus dem laufenden Vaultwarden-Container, bevor sie Erfolg meldet.
- Zusätzliche Regressionstests für pasta, TLS-Vertrauen, Containerneustart/-neuerstellung sowie Neuinstallation und Update von 0.1.0-rc.2.
- Präzisierte Android-Anleitung: korrekte selbst gehostete Serveradresse und automatische SSO-Organisationskennung.

Weiterhin kompatibel mit idp-reworked:0.1.0-rc.2; kein IdP-Update notwendig. Die Vaultwarden-Runtime ist unverändert. Ein vorhandener manueller Drop-in 90-test-idp-host.conf kann nach erfolgreichem Paketupdate gemäß docs/NETWORK-FIX.md entfernt werden.

Voraussetzung: NS8 Core 3.23.2 oder neuer und direkte Mitgliedschaft in der freigegebenen AD-Gruppe. Keine Stable-/Katalogfreigabe und kein automatischer Produktivrollout. Offline-Tresore lassen sich serverseitig nicht löschen. Vollständige Cluster-Wiederherstellung und Mehrknoten-SSO sind nicht nachgewiesen. Die Release-Veröffentlichung erfolgt erst nach erfolgreichen Protokoll- und NS8-QEMU-Prüfungen.

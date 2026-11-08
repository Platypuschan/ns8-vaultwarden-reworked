Erste stabile Version (0.1.0) von Vaultwarden Reworked für NethServer 8, mit neuer Verwaltungsoberfläche im NS8-Design. Benötigt IdP 0.1.0-rc.4 oder neuer (der IdP ist noch eine Vorabversion).

- Das Modul zeigt links ein Menü: **Einstellungen**, **Benutzer**, **Organisationen**, **Diagnose** und **Erweiterte Admin-Seite** (die Original-Adminseite von Vaultwarden), Deutsch und Englisch.
- Einstellungen: General, Advanced, Global Duo, SMTP und Email 2FA. Vom Modul verwaltete Werte (SSO, Domain, Admin-Token ...) werden nicht angezeigt. SMTP wahlweise deaktiviert, über den Cluster-Smarthost (Absender und Rest frei) oder individuell; bestehende Installationen bleiben auf „individuell“.
- Benutzer: 2FA entfernen, Sitzungen beenden, deaktivieren/aktivieren, SSO-Verknüpfung löschen, löschen, Rolle in Organisationen ändern, Clients neu synchronisieren. Organisationen: Liste und Löschen. Diagnose: Anzeige.
- Enthält den Argon2-Fix für den internen ADMIN_TOKEN (keine gelbe Warnbox mehr).
- Neue Runtime (Vaultwarden-Patch mit JSON-Ansichten für die Modulseiten); Update startet Vaultwarden neu.

Nicht enthalten: Datenbank-Backup-Schaltfläche, Support-Konfigurations-Download, Yubikey-Gruppe, Einladungen. Feldbezeichnungen der Einstellungen sind englisch (von Vaultwarden). Die Seiten wurden auf einer Testinstanz (node2) benutzt; der SMTP-Modus „Smarthost“ mit Mailversand ist ungetestet.

Keine Katalogfreigabe. Nicht live geprüft: vollständige Cluster-Wiederherstellung, Android-/Biometrie-Abnahme, Smarthost-Modus mit Mailversand.

Achte Vorabversion von Vaultwarden Reworked für NethServer 8. Behebt wiederholte SSO-Anmeldungen beim Öffnen bereits angemeldeter Apps. Benötigt weiterhin IdP 0.1.0-rc.4; kein IdP-Update gegenüber rc.7 erforderlich.

- Bereits angemeldete Geräte behalten ihre Vaultwarden-Sitzung unabhängig vom Ende der IdP-Sitzung. Der Tresor kann mit Masterpasswort oder Biometrie entsperrt werden, ohne erneut den Browser-SSO-Ablauf zu durchlaufen.
- Neue Geräte und eine ausdrücklich abgemeldete App verlangen weiterhin SSO. Unter Android muss die Tresor-Timeout-Aktion **Sperren** sein. **Abmelden** beendet die Anmeldung absichtlich.
- Das Modul setzt `SSO_AUTH_ONLY_NOT_SESSION=true` bei Installation, Konfiguration und Update automatisch. Bereits abgelaufene oder gelöschte Geräteanmeldungen benötigen nach dem Update einmalig erneut SSO.
- AD-Gruppenentzug meldet bestehende Geräte weiterhin über den zweiminütigen Widerrufsdienst ab. Dieser Dienst ist jetzt für bestehende Gerätesitzungen maßgeblich: Bei ausgefallenem Dienst oder fehlgeschlagenen LDAP-/IdP-Abfragen ist kein zeitlich begrenzter Widerruf zugesichert. Warnungen zum Widerrufsstatus beachten.

Für den Android-Test: nötigenfalls einmal SSO durchführen, Masterpasswort/Biometrie einrichten, Timeout-Aktion **Sperren** wählen, App sperren und später erneut öffnen. Es sollte nur das lokale Entsperren nötig sein. Die tatsächliche Android-/Biometrie-Oberfläche wurde noch nicht live geprüft.

Keine Stable- oder Katalogfreigabe; Vorabversion für Testinstallationen.

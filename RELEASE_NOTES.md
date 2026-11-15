Version 0.1.6 von Vaultwarden Reworked für NethServer 8. Benötigt IdP 0.1.0-rc.4 oder neuer (der IdP ist noch eine Vorabversion). Update von 0.1.5.

- **Zugangsdaten des internen Verwaltungs-Workers bleiben bei Updates erhalten.** Bisher wurden sie bei jedem Update neu erzeugt. Jetzt gilt `worker-credential.json` (privat, 0600) als einzige Quelle; der Hash wird mit Argon2 echt geprüft, geschrieben wird atomar, und eine unterbrochene Aktualisierung wird beim nächsten Start ohne neuen Token fortgesetzt. Ein inkohärenter Altbestand wird nicht stillschweigend neu erzeugt: Start und Worker verweigern, bis er bewusst repariert wird (Anleitung: `docs/WORKER-CREDENTIALS.md`). Alte und neue Backups bleiben wiederherstellbar.
- **Neue Runtime:** der gepatchte Vaultwarden-Server ist mit Rust 1.100.0 neu gebaut (Rust 1.99.1 vorher); das Update startet Vaultwarden neu.
- Oberfläche: Node.js 24.22.3 und sass 1.108.2 für den Build der Modulseiten; keine sichtbaren Änderungen.

Geprüft: Modultests, Image-Build, Protokolltests, Admin-Browser und QEMU (Debian 13 und Rocky 9; Update, zweites Update, falscher Hash, Startverweigerung, Backup/Restore), dazu eine Live-Abnahme des Credential-Updates von 0.1.5 auf einem Testknoten (idempotent, beschädigte Projektion und beschädigter Datensatz).

Nicht geprüft: Browser-SSO und Sitzungswiderruf nach dem Update, Wiederherstellung auf einem echten Knoten, die neue Rust-Runtime auf einem Knoten außerhalb der CI. Keine Katalogfreigabe.

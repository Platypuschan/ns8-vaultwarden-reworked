# Vorabversion 0.1.0-rc.1 vorbereiten

Arbeitsbranch: `codex/reworked-prerelease`. Änderungen bleiben bis zur Freigabe lokal. Getestete Anwendungsstände: Keycloak 26.7.4, Vaultwarden 1.37.2 mit API-Key-Patch; keine pauschalen Abhängigkeitsupgrades.

Nach ausdrücklicher Nutzerfreigabe:

1. Den vorbereiteten Branch in das eigene Repository pushen. Kein fremdes Repository ändern oder Bot-Review anfordern.
2. `Prepare prerelease` auf genau diesem Commit manuell starten. Der Workflow ist nur manuell auslösbar; VERSION erlaubt ausschließlich RC-Versionen.
3. Der Workflow baut Kandidaten (`candidate-<commit>`), veröffentlicht zunächst diese Testimages und referenziert die Runtime im Modul per Digest.
4. NS8-QEMU muss auf Debian 13 und Rocky 9 erfolgreich sein. Vaultwarden prüft zusätzlich mit dem unabhängigen IdP-Quellstand aus IDP_REF und dem veröffentlichten IdP aus IDP_IMAGE das echte SSO-Protokoll.
5. Erst nach grünen Prüfungen werden die geprüften Digests auf `0.1.0-rc.1` kopiert und ein GitHub-Prerelease mit RELEASE_NOTES.md erstellt. Vorhandene Versionstags werden nicht überschrieben. Kein `latest`, keine Katalogaufnahme und kein Produktivrollout.

Reihenfolge: zuerst IdP, anschließend Vaultwarden. Neue GHCR-Pakete gegebenenfalls in GitHub auf Public stellen, damit NS8 ohne Registry-Zugangsdaten installieren kann. Bei privaten Paketen muss zuerst diese Sichtbarkeit korrigiert werden; eine anonyme Testinstallation kann sonst nicht erfolgreich sein. Das ist eine separate Paketeinstellung, keine Repository-Sichtbarkeit.

IdP-QEMU führt die bestehende Realm-/Federation-/Entfernungs-Suite als Neuinstallation aus. Vaultwarden-QEMU verwendet die installierte IdP-RC und prüft beide eigenständigen Pakete gemeinsam. Kein künstliches Upgrade vom fremden Originalpaket.

Die Release-Notizen sind keine Behauptung bereits abgeschlossener RC-Tests. Historische Testberichte und neue lokale Prüfungen werden getrennt dokumentiert.

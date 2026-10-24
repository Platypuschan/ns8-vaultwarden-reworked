# Testumgebung und Nachweise

Stand: 24.10.2026. Keine produktive Instanz wurde verwendet.

## Wiederverwendete NS8-Testumgebung

`test-module.sh` und `test-module-install.sh` stammen aus
[ns8-ntfy-reworked, caa9c265](https://github.com/Platypuschan/ns8-ntfy-reworked/tree/caa9c265fc9f18d16d34b52be544fa0d8de13e95).
Der Robot-/SSH-Ansatz einschließlich Suite-Setup und API-Resource folgt außerdem
[ns8-idp, 433fa069](https://github.com/NethServer/ns8-idp/tree/433fa069c2eab4c073303769ac84c40b37a2676b/tests).
Die QEMU-Infrastruktur wird unverändert über
`NethServer/ns8-github-actions/.github/workflows/test-on-qemu.yml@v1` verwendet.

Es wird nur die Neuinstallation geprüft: für dieses bislang nicht installierte
Modul existiert keine stabile Vorgängerversion. Ein erfundenes Upgrade-Szenario
wäre kein aussagekräftiger Test.

## Lokal tatsächlich ausgeführt

Am Implementierungsstand `a7280a0f5f8ed17a09cf0ecd42bf29194e8e5a3c`:

- 5 Python-Tests zu SSO-only, Eingabe-/Env-Injection, Issuer-Verwechslung,
  fehlender/falscher Gruppenpolicy und privaten atomaren Secretdateien: grün.
- Python-, JSON- und Shellsyntaxprüfung: grün.
- Java-Provider und darauf aufgebautes Keycloak-Image: erfolgreich gebaut.
- 9 vollständige Protokoll-/Laufzeittests mit echtem Samba-AD, Keycloak 26.7.4
  und Vaultwarden 1.37.2: grün (49,845 Sekunden).

Die neun Tests prüfen:

1. Mitglied erlaubt, Nichtmitglied abgewiesen.
2. Anderer Client desselben Realms bleibt zugänglich.
3. Mobiler SSO-Ablauf mit PKCE, `bitwarden://sso-callback`, Code-Einlösung und
   Vaultwarden-Access-Token; direkter Passwort-Grant verweigert.
4. Gruppenentzug sperrt neue Anmeldung mit bestehendem SSO-Cookie und auf einem
   neuen mobilen Client; Wiederaufnahme erlaubt wieder Zugang.
5. Fehlende/leere Gruppenpolicy verweigert Zugang.
6. Wiederholte Policykonfiguration sowie Keycloak-/Vaultwarden-Neustart erhalten
   die Zugriffstrennung und die vorhandene Vaultwarden-Datenbank.
7. Nicht erreichbares LDAP verweigert Zugang, auch mit Cookie.
8. Vor dem Gruppenentzug ausgestellter Code und Refresh-Token liefern nach dem
   Entzug keine neuen Tokens.
9. Unsicher umgestellter LDAP-Benutzercache führt zur Verweigerung.

Die Container laufen in einem separaten, zufällig benannten Podman-Netz;
HTTP-Ports werden ausschließlich an Loopback gebunden. Testpasswörter werden
zufällig erzeugt. Container, Testvolume und Netzwerk werden auch bei Fehlern
entfernt. Bereinigte Dienstlogs liegen unter `tests/outputs/integration/`.
Samba dient hier ausschließlich als AD-/LDAP-Authentifizierungsfixture:
SYSVOL-Windows-ACL-Provisionierung wird wegen der rootless LXC-Umgebung
übersprungen. Es werden keine SMB-Freigaben geprüft.

Keycloak läuft im lokalen Protokolltest im Development-Modus mit einer
wegwerfbaren H2-Datenbank. Der separate NS8-QEMU-Test verwendet das echte
NS8-Modul mit PostgreSQL und Traefik. Der HTTP-Testclient behandelt nur auf
Loopback Secure-Cookies wie ein Browser im vertrauenswürdigen lokalen Kontext;
die Produktionskonfiguration verwendet HTTPS und deaktiviert keine Zertifikatprüfung.

Reproduzieren (Entwicklungsrechner mit Podman und Python `requests`):

```bash
podman build --layers -t localhost/ns8-idp-group-prototype \
  -f prototype/idp/Containerfile prototype/idp
podman build --layers -t localhost/ns8-vaultwarden-test-samba \
  -f tests/integration/Samba.Containerfile tests/integration
python3 -m unittest discover -s tests -p 'test_*.py' -v
python3 tests/check_syntax.py
python3 tests/integration/run.py
```

## NS8-QEMU / CI

Lauf zum Stand `9af96e39715835359cd2562bd22f7b009b02cce1`:
[NS8-Prototyp-Pipeline](https://github.com/Platypuschan/ns8-vaultwarden/actions/runs/40035171577).
Image-Build erfolgreich. Beide ersten NS8-Szenarien scheiterten im Testparser:
`add-module` liefert eine Python-Dict-Repräsentation, keine JSON-Zeichenkette.
Dieser Fehler wurde korrigiert; die abhängigen Folgefehler sind kein Nachweis
für eine funktionierende oder defekte Anwendungskonfiguration.

Zusätzlicher positiver Kontrolltest am originalen Vaultwarden-1.37.2-Image:
ein in der Testdatenbank hinterlegter gültiger persönlicher API-Key lieferte
nach AD-Gruppenentzug weiterhin einen neuen Geräte-Access-Token. Tatsächlich
ausgeführt, 25,996 Sekunden, erfolgreich reproduziert. Die einzelne
`client_credentials`-Sperre im SSO-only-Modus ist deshalb Bestandteil des
Runtime-Prototyps. Der neue Test 10 prüft die Verweigerung mit genau einem
gültigen Schlüssel, nicht bloß die Verweigerung eines ungültigen Schlüssels.

Neuer Prüfstand `f781b68b872416cf46d20ffac42b96e5504579ee`:
[NS8-QEMU](https://github.com/Platypuschan/ns8-vaultwarden/actions/runs/40089169752),
[Validierung und Protokolltests](https://github.com/Platypuschan/ns8-vaultwarden/actions/runs/40089169458).
Gepatchter Runtime-Build lokal erfolgreich (Rust 1.97.1, SQLite, 6 Minuten
55 Sekunden). Danach 5 lokale Konfigurationstests und alle 10 lokalen
Protokolltests grün (50,716 Sekunden). Die veröffentlichte CI-Validierung zu
diesem Stand ist ebenfalls vollständig grün, einschließlich aller 10
Protokolltests mit dem gepatchten Runtime. NS8-QEMU-Ergebnisse noch offen.

Core wird gezielt mit `ghcr.io/nethserver/core:3.23.2` installiert. Die Suite
installiert die beiden Prototypmodule, richtet ein internes Samba-AD ein,
prüft verweigerte Aktivierung ohne Gruppenregel, anschließende Aktivierung,
HTTPS-Route, Secretdateirechte, Policyerhalt bei erneuter Clientregistrierung,
konsistenten Datensnapshot und Entfernung der Module.

## Noch nicht behauptet

- Kein physischer Android-/iOS-Test, keine Biometrie-/Autofill-Oberflächenprüfung.
- Kein Test der produktiven DNS-/Let's-Encrypt-Erreichbarkeit von example.com.
- Keine sofortige Fernlöschung von Offline-Tresoren oder bereits ausgegebenen
  Vaultwarden-Access-Tokens.
- Keine vollständige NS8-Cluster-Disaster-Recovery oder Migration vorhandener
  nicht-SSO-Tresorkonten.
- Keine zugesicherte transitive Mitgliedschaft über verschachtelte AD-Gruppen.

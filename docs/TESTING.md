# Aktueller Reworked-Prüfumfang

Der weiterhin manuell baubare historische IdP-Overlay wurde separat kohärent auf Keycloak/SPI 26.8.2 aktualisiert: [Rezept, erhaltene NS8-Provider und aktuelle historische Prüfanleitung](HISTORICAL-IDP-2682.md). Dies ändert weder die unabhängige produktive IdP-Runtime noch die nachstehenden ursprünglichen Nachweise.

Die nachfolgenden Abschnitte sind historische Prototyp-Nachweise. Die eigenständigen RC-Pakete sind inzwischen gemeinsam in NS8 geprüft; siehe [Release-Bericht](RELEASE-0.1.0-rc.1.md). Die aktuelle lokale Protokollsuite benötigt IDP_SOURCE_ROOT (Checkout des unabhängigen IdP), IDP_RUNTIME_IMAGE und VW_RUNTIME_IMAGE. Die alte Prototyp-Migrationsprüfung wurde entfernt.

```sh
IDP_SOURCE_ROOT=/pfad/ns8-idp-reworked IDP_RUNTIME_IMAGE=localhost/idp-reworked-keycloak:0.1.0-rc.1 VW_RUNTIME_IMAGE=localhost/vaultwarden-reworked-server:0.1.0-rc.1 python3 tests/integration/run.py
```

# Testumgebung und Prüfnachweise

## Stand des Branches claude/idp-upstream-integration (24.10.2026)

Umbau nach [ADR 0002](decisions/0002-required-action-group-gate.md), Commit
`0dd6733`. Lokal, in CI und in NS8-QEMU geprüft; nicht live getestet. Die
Abschnitte darunter beschreiben den vorherigen Stand `prototype-89a52bc0f978`.

CI (Commit `0dd6733`):

- [Prototype validation 40127209220](https://github.com/Platypuschan/ns8-vaultwarden/actions/runs/40127209220):
  7 Unit-Tests, Syntax und 16 Protokolltests grün (65 s).
- [NS8 prototype on QEMU 40127193380](https://github.com/Platypuschan/ns8-vaultwarden/actions/runs/40127193380):
  Robot-Suite 9/9 auf Debian 13 und Rocky 9, Core 3.23.2. Geprüft:
  `alter-realm-client` mit `access_group`, `list-realms` und
  `get-client-access` mit leeren `issues`, Ablehnung von `alter-realm-client`
  durch die Anwendung, gleichzeitige Reconciliation, Backup/Neustart, Entfernen.

Tag `prototype-0dd673332309`:

| Image | Digest |
|---|---|
| `idp-keycloak` | `sha256:eb76b6d0a4b6aa5c7f9c8a2ef20a67101feecfb53f4f4f325c7f9bda68f22d3f` |
| `idp-vaultwarden-prototype` | `sha256:14c67cce8dac0b87c973b1306dab57f4b09e37d4ecfa6c72922695fd5f786a54` |
| `vaultwarden-server` | `sha256:1c2ec53c946772d0d06e43678ae3e1a143fb8f55f2a6d57d664e5b5fba206921` |
| `vaultwarden` | `sha256:11ca0ea3d53fa63d0430f6eb3e9d8ad3b96d47fceb38d7a4e8d15766580fa088` |

Lokal:

| Prüfung | Ergebnis |
|---|---|
| Unit-Tests (Konfiguration, Registrierung mit `access_token_lifespan`) | 7 grün |
| Python-, JSON-, Shellsyntax | grün |
| Protokolltests Samba-AD + Keycloak 26.7.4 + gepatchter Vaultwarden | 16 grün (62 s) |
| Gegenprobe ohne Cache-Evict (Tests 04, 09) | rot wie erwartet: Wiederaufnahme in die Gruppe wird wegen des Benutzercaches nicht erkannt |
| Gegenprobe ohne Required Action (Tests 01, 04, 11) | rot wie erwartet: Nichtmitglieder erhalten per Passwort, SSO-Cookie, neuem Gerät und externem IdP einen Autorisierungscode |

Neue bzw. geänderte Protokolltests:

- 01: Realm-Browserflow unverändert, kein Flow-Override am Client, LDAP-Cache bleibt `DEFAULT`.
- 09: Gruppenentzug und Wiederaufnahme wirken bei vorgewärmtem Cache sofort.
- 11: schreibbare Federation und externer OIDC-IdP (zweiter Keycloak-Realm statt
  Entra ID), eingerichtet mit den unveränderten Upstream-Funktionen aus `idpfed.py`
  (Mapper, Flows, Passwortsperre, Login-Modi). Erstanmeldung legt das Konto im AD
  an und wird abgewiesen, gleiche SSO-Sitzung bei anderem Client erlaubt,
  Gruppenaufnahme erlaubt, Modus `federated` leitet direkt zum IdP und prüft
  die Gruppe, Entzug sperrt wieder.
- 12: `access_token_lifespan` optional: 600 s für Vaultwarden (auch im Token
  `expires_in`), Realm-Standard für andere Clients, Registrierung ohne Parameter
  behält den Wert, `null` setzt zurück.
- 13: Regel entfernen (Attribute und Tokenprüfung weg) und neu setzen; unbekannte
  Gruppe wird abgewiesen, der Client bleibt dabei unverändert.
- 14: Migration einer Regel des ersten Prototyps (eigener Flow, alte Attribute);
  Flows werden entfernt, `browser` bleibt erhalten.
- 15: Reconciliation stellt fehlende Tokenprüfung und deaktivierte Required Action wieder her.
- 16: Client gelöscht und mit gleicher ID neu registriert: ohne Regel nicht
  durchgesetzt, Regel setzbar, Zugriff wieder getrennt.

Lokale Umgebung: rootless Podman in LXC; das Samba-Testimage wurde dort mit
`apt-get -o APT::Sandbox::User=root` gebaut, weil die Gruppen-ID 65534 im
Namensraum fehlt. Im Repository ist das Containerfile unverändert.

## Vorheriger Stand

Stand: 24.10.2026. Alle Tests liefen isoliert; keine produktive Instanz wurde
installiert oder verändert. Der geprüfte Modulcode ist
[`89a52bc0f9785514666c4aed16bbcb0187307a49`](https://github.com/Platypuschan/ns8-vaultwarden/commit/89a52bc0f9785514666c4aed16bbcb0187307a49).
Nachfolgende Änderungen an Anleitung und verschärfter Cookie-Testprüfung
ändern die vier getesteten Prototyp-Images nicht.

## Ergebnis

| Prüfung | Ergebnis | Beleg |
|---|---|---|
| Konfiguration, Eingabe-/Env-Injection, Issuer, Geheimnisdateirechte, idempotente Domänenbindung | 7 Tests grün | [CI-Validierung](https://github.com/Platypuschan/ns8-vaultwarden/actions/runs/40091272695) |
| Echter Samba-AD + Keycloak + gepatchter Vaultwarden, einschließlich mobilem OIDC-Protokoll | 10 Tests grün | [CI-Validierung](https://github.com/Platypuschan/ns8-vaultwarden/actions/runs/40091272695) |
| NS8 Core 3.23.2 / Debian 13 | 9 Modultests grün | [QEMU-Matrix](https://github.com/Platypuschan/ns8-vaultwarden/actions/runs/40091270240) |
| NS8 Core 3.23.2 / Rocky 9 | 9 Modultests grün | [QEMU-Matrix](https://github.com/Platypuschan/ns8-vaultwarden/actions/runs/40091270240) |
| Java-Provider, gepatchter Rust-Runtime, vier Prototyp-Images | erfolgreich gebaut | [Image-Build und QEMU](https://github.com/Platypuschan/ns8-vaultwarden/actions/runs/40091270240) |
| Python-, JSON-, Shellsyntax; Robot-Dryrun | grün | lokal und CI |

Zusätzlich lokal ausgeführt: alle zehn Protokolltests mit dem gepatchten
Runtime (50,716 Sekunden), nach Einbau der expliziten Versionskennung erneut
alle zehn (50,536 Sekunden). Der Cookie-Test wurde danach verschärft: Bei
vorhandener SSO-Sitzung darf der Testtreiber keine erneute Passwortanmeldung
als Ausweichweg verwenden. Dieser Test und der LDAP-Ausfalltest sind gezielt
lokal grün (35,332 Sekunden). Die verschärfte Prüfung läuft außerdem in den
[aktuellen PR-Checks](https://github.com/Platypuschan/ns8-vaultwarden/pull/1/checks).

## Getestete Images

Gemeinsamer Tag: **`prototype-89a52bc0f978`**. Kein Stable-/Katalogrelease.

| Modul | Digest |
|---|---|
| `ghcr.io/platypuschan/vaultwarden` | `sha256:924a4e4a859be739197e4ba57d8867767a7a4cc4aaa9d26c3dad314e5a1050af` |
| `ghcr.io/platypuschan/idp-vaultwarden-prototype` | `sha256:f41766b4a52c49f8aa78e32141957e72a02749cf90ca0c4ccf7dcf56c7566e0f` |

Die Modulimages verweisen auf `vaultwarden-server` bzw. `idp-keycloak` desselben
Tags. Beide Module wurden anschließend unabhängig vom CI-Runner anonym aus
GHCR geladen und die Abhängigkeiten geprüft. Der App-Digest stimmt mit den
Versionsartefakten beider QEMU-Gäste überein. Core-Image:
`ghcr.io/nethserver/core:3.23.2`, Digest
`sha256:d620e58ae38b0f49c7ea10fdb12bb56880912cadb171c514d2c4c783fddad580`.

## Übernommene NS8-Testumgebung

`test-module.sh` und `test-module-install.sh` stammen aus
[ns8-ntfy-reworked, caa9c265](https://github.com/Platypuschan/ns8-ntfy-reworked/tree/caa9c265fc9f18d16d34b52be544fa0d8de13e95).
Suite-Setup und API-Resource folgen außerdem
[ns8-idp, 433fa069](https://github.com/NethServer/ns8-idp/tree/433fa069c2eab4c073303769ac84c40b37a2676b/tests).
Die QEMU-Infrastruktur wird über
`NethServer/ns8-github-actions/.github/workflows/test-on-qemu.yml@v1` verwendet.

Die neun Tests pro NS8-Gast prüfen:

1. Installation des IdP-Prototyps und des Vaultwarden-Moduls.
2. Provisionierung eines internen Samba-AD mit Mitglied/Nichtmitglied.
3. OIDC-Vorbereitung und verweigerte Aktivierung ohne Gruppenregel.
4. Administrative Gruppenregel, aktive Policy und exakter Gruppenpfad.
5. Aktivierung, HTTPS-Route, private Secretdatei und Erhalt der Policy bei
   erneuter Clientregistrierung.
6. Gleichzeitig laufende IdP-Reconciliation und Modulkonfiguration.
7. Die Anwendung darf ihre eigene Gruppenregel nicht ändern.
8. Konsistenter Datensnapshot, enthaltene `db.sqlite3`, anschließender
   Dienststart mit wiederverwendetem Datenvolume und Snapshot-Bereinigung.
9. Entfernung der Anwendung, des IdP und der Testdomäne.

Es wird die Neuinstallation geprüft: für dieses bislang nicht installierte
Modul existiert keine stabile Vorgängerversion. Ein künstliches Upgrade ist
kein Ersatz für einen echten Vorgängerstand.

## OIDC- und Gruppenprüfungen

Die zehn Protokolltests verwenden echtes Samba-AD, Keycloak 26.7.4 und
Vaultwarden 1.37.2 mit dem gezielten API-Key-Patch:

1. Mitglied erlaubt, Nichtmitglied abgewiesen.
2. Anderer Client desselben Realms bleibt zugänglich.
3. Mobiler SSO-Ablauf mit PKCE, `bitwarden://sso-callback`, Code-Einlösung und
   Vaultwarden-Access-Token; direkter Passwort-Grant verweigert.
4. Gruppenentzug sperrt neue Anmeldung mit bestehendem SSO-Cookie und auf einem
   neuen mobilen Client; Wiederaufnahme erlaubt wieder Zugang.
5. Fehlende/leere Gruppenpolicy verweigert Zugang.
6. Wiederholte Policykonfiguration und Keycloak-/Vaultwarden-Neustart erhalten
   die Zugriffstrennung und die vorhandene Datenbank.
7. Nicht erreichbares LDAP liefert keinen Zugang. Keycloak darf dabei die
   Cookie-Anmeldung verwerfen und eine neue Login-Maske anzeigen; auch deren
   Ausfüllen darf keinen Code/Token erzeugen.
8. Vor dem Gruppenentzug ausgestellter Code und Refresh-Token liefern nach dem
   Entzug keine neuen Tokens.
9. Unsicher umgestellter LDAP-Benutzercache führt zur Verweigerung.
10. Ein gültiger persönlicher API-Key liefert nach Gruppenentzug keinen neuen
    Gerätezugang; die Antwort verlangt ausdrücklich SSO.

Der API-Key-Test hat einen positiven Kontrolllauf: Beim unveränderten
Upstream-Image 1.37.2 wurde der Umgehungsweg mit einem gültigen Testschlüssel
nach Gruppenentzug tatsächlich reproduziert (25,996 Sekunden). Es wurde somit
nicht bloß die Verweigerung eines ungültigen Schlüssels getestet.

## Lokale Testisolation und Reproduktion

Die Container laufen in einem separaten, zufällig benannten Podman-Netz;
HTTP-Ports werden ausschließlich an Loopback gebunden. Testpasswörter werden
zufällig erzeugt. Container, Testvolume und Netzwerk werden auch bei Fehlern
entfernt. Bereinigte Dienstlogs liegen unter `tests/outputs/integration/`.
Samba dient hier ausschließlich als AD-/LDAP-Authentifizierungsfixture:
SYSVOL-Windows-ACL-Provisionierung wird wegen der rootless LXC-Umgebung
übersprungen. Es werden keine SMB-Freigaben geprüft.

Keycloak läuft lokal im Development-Modus mit einer wegwerfbaren H2-Datenbank;
NS8-QEMU verwendet das echte Modul mit PostgreSQL und Traefik. Der lokale
HTTP-Testclient behandelt nur auf Loopback Secure-Cookies wie ein Browser im
vertrauenswürdigen lokalen Kontext. Produktionscode verwendet HTTPS und
schaltet keine Zertifikatprüfung aus.

Entwicklungsrechner mit Podman und Python `requests`, im Repository:

```bash
podman build --layers -t localhost/ns8-idp-group-prototype \
  -f prototype/idp/Containerfile prototype/idp
podman build --layers -t localhost/ns8-vaultwarden-test-samba \
  -f tests/integration/Samba.Containerfile tests/integration
podman build --layers -t localhost/vaultwarden-sso-only \
  -f prototype/vaultwarden/Containerfile prototype/vaultwarden
python3 -m unittest discover -s tests -p 'test_*.py' -v
python3 tests/check_syntax.py
python3 tests/integration/run.py
```

## Im Test gefundene und behobene Fehler

- API-Key-Gerätelogin umging Upstream-`SSO_ONLY`: gezielter Runtime-Patch.
- Parallele IdP-Ereignisverarbeitung/Registrierung erzeugte mit PostgreSQL
  Schreibkonflikte: gemeinsame Realm-Sperre und keine unnötigen Neubindungen.
- Dienstneustart scheiterte an einem vorhandenen Volume: wiederholbares Anlegen
  mit `--ignore`, ohne vorhandene Daten zu löschen.
- NS8-Testparser erwartete JSON bei `add-module`: tatsächliche Python-Dict-
  Repräsentation wird korrekt gelesen.

Architektur und Quellen: [Entscheidung 0001](decisions/0001-client-group-gate.md).

## Grenzen

- Kein physischer Android-/iOS-Test, keine Biometrie-/Autofill-Oberflächenprüfung.
- Kein Test der produktiven DNS-/Let's-Encrypt-Erreichbarkeit von example.com.
- Keine sofortige Fernlöschung von Offline-Tresoren oder bereits ausgegebenen
  Vaultwarden-Access-Tokens.
- Keine vollständige NS8-Cluster-Disaster-Recovery oder Migration vorhandener
  nicht-SSO-Tresorkonten.
- Keine zugesicherte transitive Mitgliedschaft über verschachtelte AD-Gruppen.

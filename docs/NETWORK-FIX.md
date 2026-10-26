# Lokaler IdP-Zugriff mit pasta

Korrektur ab **0.1.0-rc.3**. Die 0.1.0-rc.2-Images enthalten diese Änderung nicht.
IdP bleibt auf 0.1.0-rc.2; ein IdP-Update ist dafür nicht erforderlich.

## Fehler und Korrektur

Bei einem IdP auf demselben NS8-Knoten kann `pasta` den Containerzugriff auf
die eigene öffentliche IP verhindern. Der Host erreicht die Discovery,
Vaultwarden meldet aber `Failed to discover OpenID provider: Request failed`.
Auf der Testinstanz blieb der Fehler auch mit deaktivierter Netcup-Firewall.

Der korrigierte Dienst berechnet vor jedem Start aus den NS8-Knotenmetadaten
die nötige Hostzuordnung. Nur für einen lokalen IdP unter `pasta` wird
`--add-host=<idp-host>:host-gateway` an Podman übergeben. Podman bestimmt die
interne Adresse selbst. Bei entferntem IdP wird keine lokale Zuordnung gesetzt.
HTTPS und der öffentliche OIDC-Issuer bleiben unverändert.

Die automatisch erzeugte `vaultwarden-network.env` ist kein Benutzerparameter
und wird bei jedem Dienststart überschrieben. Sie muss nicht gesichert werden.
Ein Paketupdate startet den aktivierten Dienst über das vorhandene
`update-module.d/80restart` neu; dadurch wird die Zuordnung auch beim Update
erzeugt. Ein Restore erfordert wie bisher erneute SSO-Vorbereitung und Freigabe.

## Update von rc.2

Als root auf dem NS8-Host (tatsächliche Modul-ID verwenden):

```bash
api-cli run cluster/update-module --data \
  '{"module_url":"ghcr.io/platypuschan/vaultwarden-reworked:0.1.0-rc.3","instances":["vaultwarden-reworked1"]}'
```

Erst nach erfolgreichem Update den bisherigen Testworkaround entfernen.

## Alten Testworkaround entfernen

Erst nach Installation eines Pakets, das die Korrektur enthält: als root auf
dem NS8-Host die tatsächliche Modul-ID verwenden. Die folgenden Befehle
entfernen nur den im Test angelegten Drop-in `90-test-idp-host.conf`.
Andere lokale Overrides vorher mit `systemctl --user cat vaultwarden.service`
im Modulkontext prüfen und erhalten.

```bash
runagent -m vaultwarden-reworked1 sh -eu -c '
config_dir="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user/vaultwarden.service.d"
rm -f "$config_dir/90-test-idp-host.conf"
systemctl --user daemon-reload
systemctl --user restart vaultwarden.service
'
```

Danach mit dem tatsächlichen IdP-Host und Realm prüfen:

```bash
runagent -m vaultwarden-reworked1 podman exec vaultwarden-app \
  curl --fail --silent --show-error --connect-timeout 5 --max-time 15 \
  https://sso.example.com/realms/ad.example.com/.well-known/openid-configuration
```

Die Antwort muss den unveränderten HTTPS-Issuer enthalten. Anschließend Web-
und Android-SSO testen, den Dienst erneut starten und den Test wiederholen.
Keine Zertifikatsprüfung abschalten und keinen Issuer auf eine interne IP ändern.

## Regressionstests

Im Repository mit vorhandener Podman-/pasta-Installation (Podman >= 5.3),
Python, OpenSSL und der Runtime ausführen:

```bash
python3 -m unittest discover -s tests -p 'test_*.py' -v
VW_RUNTIME_IMAGE=localhost/vaultwarden-reworked-server:0.1.0-rc.1 \
  python3 tests/network/run.py
```

Der Runtime-Code ist für diese Korrektur unverändert. Die Suite startet einen
isolierten HTTPS-Testserver mit eigenem Testzertifikat auf einem zufälligen
Port. Sie reproduziert den Fehler ohne Zuordnung und prüft die Korrektur nach
Neustart und Neuerstellung sowie die Ablehnung eines unvertrauten Zertifikats.
Die NS8-QEMU-Suite enthält zusätzlich Tests am installierten Dienst und startet
diese TLS-Suite auf Knoten mit `pasta`. Andere Backends überspringen die beiden
gezielten pasta-Tests; lokale/entfernte Knoten werden zusätzlich per Unit-Test
abgedeckt. Dies ersetzt keinen vollständigen Mehrknoten-SSO-Test.

Architektur und Quellen: [ADR 0004](decisions/0004-local-idp-pasta.md).

## Lokal geprüfter Stand, 26.10.2026

- 25 Unit-/Aktionsprüfungen erfolgreich, einschließlich fehlgeschlagener
  Discovery ohne irreführende Erfolgsausgabe und entferntem IdP ohne Alias.
- Drei reale pasta-/TLS-Tests erfolgreich: Fehler ohne Mapping, gültiges HTTPS
  nach Restart/Neuerstellung, unvertrautes Zertifikat verweigert.
- Mit lokalen systemd-Benutzerdiensten geprüft: EnvironmentFile wird nach
  ExecStartPre erneut geladen; leere Netzwerkoptionen erzeugen keine leeren
  Argumente, die lokale Hostzuordnung wird als ein Argument übergeben.
- Modulimage lokal gebaut und exportierten Inhalt geprüft: Helper ausführbar,
  Dienstdatei enthalten, Runtime per Digest gepinnt, keine Python-Testcaches.
- Python-/JSON-/Shell-Syntax und Robot-Dryrun aller zwölf NS8-Tests erfolgreich.

Noch nicht geprüft: neuer kompletter NS8-QEMU-Lauf, Installation des korrigierten
Pakets auf der Nutzerinstanz, echter Mehrknoten-SSO-Ablauf. Der frühere erfolgreiche
Web-/Android-Test nutzte den manuellen Workaround, nicht dieses neue Paket.
Keine Veröffentlichung und kein Deployment durch diese lokale Prüfung.

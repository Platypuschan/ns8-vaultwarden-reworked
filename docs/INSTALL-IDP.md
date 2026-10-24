# ns8-idp und Vaultwarden mit Samba-AD-Gruppenfilter

Stand: 24.10.2026. Diese Anleitung beschreibt den **Prototyp dieses Branches**.
Der unveränderte Upstream-IdP bietet die hier verwendeten Aktionen
`set-client-access` und `get-client-access` nicht. Nur SSO einzuschalten oder
AD-Gruppen zu importieren beschränkt den Zugang noch nicht.

## Zielkonfiguration

| Eigenschaft | Wert |
|---|---|
| NS8-Core | 3.23.2 |
| Knoten | 1 |
| vorhandener interner Samba-AD | `ad.example.com` |
| IdP | `sso.example.com` |
| Vaultwarden | `vaultwarden.example.com` |
| erlaubte Gruppe | `services_vaultwarden` (direkte Mitgliedschaft) |
| E-Mail-Adresse | eindeutiges AD-Attribut `mail` |
| zusätzliche externe IdPs | keine |

Die folgenden Befehle laufen **als root auf einem NS8-Host**. Sie wurden nicht
auf deiner produktiven Instanz ausgeführt. Die Modul-IDs sind Beispiele;
immer die tatsächlich von `add-module` zurückgegebenen IDs verwenden.

## 1. DNS und Zertifikat vorbereiten

`@` und `*` mit der öffentlichen NS8-IP decken normalerweise beide Hostnamen
ab. Ein spezifischer DNS-Eintrag kann den Wildcard-Eintrag überschreiben.
Prüfen, dass A/gegebenenfalls AAAA korrekt sind und der öffentliche Zugang zu
NS8-Traefik funktioniert. Es ist kein zusätzlicher Reverse Proxy erforderlich.
Die Hostnamen dürfen noch keiner anderen NS8-Anwendung zugeordnet sein.

Für `lets_encrypt:true` muss NS8 das Zertifikat erfolgreich anfordern können.
Von einem Rechner außerhalb des LAN prüfen, dass die nötigen HTTP-/HTTPS-
Zugänge zum NS8-Knoten führen. Ein falscher AAAA-Eintrag muss korrigiert werden.
Im LAN müssen Geräte und Anwendungscontainer dieselben HTTPS-Namen erreichen
können (passendes internes DNS oder funktionierendes NAT-Loopback).

Die interne AD-Domäne wird nicht als öffentliches LDAP/AD freigegeben. Die
Verbindung von Keycloak zu Samba läuft über den bestehenden NS8-LDAP-Proxy.

## 2. Getestete Prototyp-Images festlegen

Die QEMU-Pipeline dieses Repositorys baut vier zusammengehörige Images mit
`prototype-<12-stellige Commit-SHA>`. Den erfolgreich geprüften Lauf aus
[TESTING.md](TESTING.md) auswählen; **kein unbestimmtes `latest` verwenden**.
Das Paket ist kein Katalog-/Stable-Release.

```bash
# Beispiel ersetzen durch den in TESTING.md nachgewiesenen Prototyp-Tag.
VW_PROTOTYPE_TAG='prototype-9af96e397158'
VW_IDP_IMAGE="ghcr.io/platypuschan/idp-vaultwarden-prototype:${VW_PROTOTYPE_TAG}"
VW_APP_IMAGE="ghcr.io/platypuschan/vaultwarden:${VW_PROTOTYPE_TAG}"
```

Das Vaultwarden-Modulpaket verweist auf `vaultwarden-server` desselben Tags.
Dieser Runtime-Prototyp enthält einen gezielten Upstream-Patch: auch persönliche
API-Keys dürfen bei SSO-only keinen neuen Geräte-Login erzeugen. Das originale
`vaultwarden/server:1.37.2` allein würde diesen Weg weiterhin erlauben. API-Key-
Automationen/Organisations-API-Key-Login sind in diesem Modus daher gesperrt.

Das IdP-Modulpaket verweist auf das zum selben Stand gehörende
`ghcr.io/platypuschan/idp-keycloak`-Image. Dieses enthält den zusätzlichen
Gruppenprüfer und behält die ursprünglichen NS8-Provider bei.

## 3. IdP auf Knoten 1 installieren und HTTPS konfigurieren

```bash
add-module "$VW_IDP_IMAGE" 1
```

Im Beispiel lautet die zurückgegebene ID `idp-vaultwarden-prototype1`:

```bash
api-cli run module/idp-vaultwarden-prototype1/configure-module --data \
  '{"host":"sso.example.com","lets_encrypt":true}'

api-cli run module/idp-vaultwarden-prototype1/get-configuration
```

Danach müssen der HTTPS-Hostname und das Zertifikat stimmen:

```bash
curl --fail --silent --show-error \
  https://sso.example.com/realms/master/.well-known/openid-configuration
```

Keine LDAP-Bind-Zugangsdaten, kein AD-Administratorpasswort und kein externes
IdP-Secret werden für das gewöhnliche lokale AD-SSO eingegeben. Die
read-only Federation wird beim Registrieren der Anwendung eingerichtet.

Für eine schon vorhandene Upstream-IdP-Instanz ist dies keine Anleitung zum
blinden Ersetzen des Images. Der Prototyp wurde für eine separate Testinstanz
entwickelt; bestehende Realms und Anwendungen vorher inventarisieren/sichern.

## 4. Vaultwarden installieren und SSO vorbereiten

```bash
add-module "$VW_APP_IMAGE" 1
```

Zurückgegebene ID im Beispiel: `vaultwarden1`.

```bash
api-cli run module/vaultwarden1/prepare-sso --data \
  '{"host":"vaultwarden.example.com","domain":"ad.example.com","idp_module":"idp-vaultwarden-prototype1","required_group":"services_vaultwarden","lets_encrypt":true}'
```

Diese Aktion bindet das Modul an die vorhandene NS8-Domäne und registriert den
OIDC-Client. Sie gibt **kein Client-Secret** aus und startet Vaultwarden noch
nicht. Damit entsteht nicht versehentlich ein Dienst ohne angewendeten Filter.
`prepare-sso` ist nur vor der ersten Aktivierung vorgesehen.

| OIDC-Eigenschaft | Wert |
|---|---|
| Realm | `ad.example.com` |
| Client-ID | tatsächliche Vaultwarden-Modul-ID, hier `vaultwarden1` |
| Issuer | `https://sso.example.com/realms/ad.example.com` |
| Callback | `https://vaultwarden.example.com/identity/connect/oidc-signin` |
| Discovery | Issuer + `/.well-known/openid-configuration` |

Die Callback-Adresse bleibt auch für Android dieselbe: Vaultwarden übernimmt
anschließend den Rücksprung in die App (`bitwarden://sso-callback`). Nicht
diese App-URI als alleinigen Keycloak-Callback eintragen.

## 5. Gruppenregel administrativ setzen

Die AD-Gruppe muss vorhanden sein. Vorgesehene Benutzer direkt aufnehmen und
deren `mail`-Attribut prüfen. Der Pfad bezeichnet die von Keycloak importierte
AD-Gruppe, keine Vaultwarden-Organisation und keinen OIDC-Scope.

```bash
api-cli run module/idp-vaultwarden-prototype1/set-client-access --data \
  '{"domain":"ad.example.com","client_id":"vaultwarden1","group_path":"/services_vaultwarden"}'

api-cli run module/idp-vaultwarden-prototype1/get-client-access --data \
  '{"domain":"ad.example.com","client_id":"vaultwarden1"}'
```

Erwartet werden `enforced:true`, `enabled:true` und
`group_path:"/services_vaultwarden"`. Die Aktion synchronisiert Gruppenobjekte,
legt den separaten Anmeldeflow an und installiert die Tokenprüfung.
Sie ändert nicht den Standard-Browserflow des Realms. Für aktuelle
Mitgliedschaften wird der LDAP-Benutzercache auf `NO_CACHE` gestellt; das kann
mehr LDAP-Anfragen auch für andere Anwendungen dieses Realms verursachen.

Schlägt das Setzen teilweise fehl, bleibt der Client absichtlich deaktiviert.
Ursache beheben und Policy erneut prüfen; nicht einfach ohne gültige Policy
aktivieren. Nach erfolgreicher Reparatur lässt sich der Client administrativ
mit der vorhandenen Upstream-Aktion wieder aktivieren:

```bash
api-cli run module/idp-vaultwarden-prototype1/alter-realm-client --data \
  '{"domain":"ad.example.com","client_id":"vaultwarden1","enabled":true}'
```

Keine Änderung an `ns8-agent`, dessen Secret oder den AD-Servicekonten nötig.
Die Anwendung hat keine Berechtigung, `set-client-access` selbst aufzurufen.

## 6. Vaultwarden aktivieren

```bash
api-cli run module/vaultwarden1/configure-module --data \
  '{"host":"vaultwarden.example.com","domain":"ad.example.com","idp_module":"idp-vaultwarden-prototype1","required_group":"services_vaultwarden","lets_encrypt":true}'

api-cli run module/vaultwarden1/get-configuration

curl --fail --silent --show-error https://vaultwarden.example.com/alive
```

Die Aktivierung scheitert, wenn die Gruppenregel fehlt, deaktiviert ist oder
nicht zur konfigurierten Gruppe passt. Der Dienst läuft im **Benutzer-systemd-
Kontext des Moduls**, nicht als Systemdienst `vaultwarden.service` des Hosts:

```bash
runagent -m vaultwarden1 systemctl --user status vaultwarden.service
runagent -m vaultwarden1 podman ps
```

Die dauerhafte Konfiguration liegt in `settings.json` und `vaultwarden.env`
im Modul-State. `vaultwarden.env` enthält das Client-Secret und hat Modus 0600.
Nicht ausgeben oder ins Repository kopieren. `get-configuration` liefert nur
die nicht geheimen Einstellungen. Vaultwarden-Daten liegen im modulinternen
Podman-Volume `vaultwarden-data`.

Wichtige verwaltete Werte:

```ini
SSO_ENABLED=true
SSO_ONLY=true
SSO_SCOPES=profile email
SSO_PKCE=true
SSO_AUTH_ONLY_NOT_SESSION=false
SIGNUPS_ALLOWED=false
SSO_SIGNUPS_ALLOWED=true
SSO_SIGNUPS_MATCH_EMAIL=false
SSO_ALLOW_UNKNOWN_EMAIL_VERIFICATION=false
INVITATIONS_ALLOWED=false
EMAIL_CHANGE_ALLOWED=false
```

`openid` ergänzt Vaultwarden automatisch. Normale Refresh-Tokens erhält der
Keycloak-Client ohne den zusätzlichen Keycloak-Scope `offline_access`.
Der gleichnamige Bitwarden-Client-Scope ist davon unabhängig.

Die E-Mail-Adressen werden aus der read-only, vertrauenswürdigen AD-Federation
übernommen; der `email_verified`-Claim muss wahr sein. Fehlende Verifikation
wird nicht pauschal in Vaultwarden freigeschaltet. Benutzer dürfen die
zugeordneten `mail`-Werte nicht selbst beliebig ändern können.

Für diesen Client eine Access-Token-Laufzeit von mindestens 10 Minuten
verwenden (Vaultwarden-Upstream-Empfehlung für Keycloak). Die Beispielintegration
setzt 600 Sekunden. Die Policy setzt dies auch pro Client automatisch. Die
SSO-/Client-Sitzungslaufzeiten des Realms bestimmen die reguläre erneute
Anmeldung. Den Standardflow nachträglich geänderte MFA-Schritte zusätzlich in
den kopierten Clientflow übernehmen; der Prototyp repariert solche Änderungen
nicht automatisch.

## 7. Android einrichten und Zugriff prüfen

In der aktuellen offiziellen Bitwarden-App die selbst gehostete Serveradresse
`https://vaultwarden.example.com` einstellen und SSO wählen. Einmalig über
`sso.example.com` mit dem AD-Konto authentifizieren, anschließend ein eigenes
Masterpasswort für den Tresor festlegen bzw. den vorhandenen Tresor damit
entsperren. Die konkrete Oberfläche und Browser-Rückleitung vor einem Rollout
mit den verwendeten App-Versionen testen.

Danach auf Android Biometrie einschalten und die Timeout-Aktion **Sperren**
wählen. Solange das Konto angemeldet bleibt, braucht das lokale Entsperren
normalerweise kein neues SSO. Abmelden oder eine abgelaufene Serversitzung
können eine erneute Anmeldung verlangen.

Vor Freigabe prüfen:

1. Mitglied: Web und Android-SSO erfolgreich.
2. Nichtmitglied mit gültigem AD-Passwort: kein Zugang.
3. Mitglied entfernen und auf einem zweiten Gerät anmelden: verweigert.
4. Dasselbe mit einer noch vorhandenen Keycloak-Browsersitzung: verweigert.
5. Nach erneutem Hinzufügen zur Gruppe: neue Anmeldung wieder möglich.
6. Ein anderer Anwendungsclient desselben Realms bleibt unabhängig zugänglich.

Der lokale Protokolltest deckt den mobilen Callback und Token-Austausch ab,
keinen physischen Android-/Biometrietest. Bereits heruntergeladene Tresore und
noch gültige signierte Vaultwarden-Access-Tokens können nicht durch eine
bloße AD-Gruppenänderung sofort gelöscht bzw. überall sofort gesperrt werden.
Neue OIDC-Autorisierungen, Code-Einlösungen und Token-Erneuerungen werden mit
der aktuellen Mitgliedschaft geprüft.

## Backup und Restore im Prototyp

`module-dump-state` stoppt den Benutzer-Dienst kurz, exportiert das vollständige
Datenvolume als konsistenten Snapshot und startet den Dienst auch bei einem
Exportfehler wieder. NS8 sichert den Snapshot und die privaten Einstellungen.
`module-cleanup-state` entfernt den temporären Snapshot nach dem Backup.

Beim Restore bleibt der Dienst deaktiviert: die neue Modul-ID muss mit
`prepare-sso`, administrativer Gruppenregel und `configure-module` erneut
registriert werden. Kein Start mit unkontrolliert übernommenen Credentials.
Vollständigen Cluster-Disaster-Recovery vor produktivem Einsatz separat prüfen.
Eine vorhandene `/data/config.json` kann Umgebungswerte übersteuern; der
Prototyp verweigert dann den Start, statt diese Datei still zu löschen.

## Primärquellen

- [NS8-idp Install/Configure/Clients](https://github.com/NethServer/ns8-idp/tree/433fa069c2eab4c073303769ac84c40b37a2676b)
- [Vaultwarden OIDC](https://github.com/dani-garcia/vaultwarden/wiki/Enabling-SSO-support-using-OpenId-Connect)
- [Bitwarden: Anmelden und Entsperren](https://bitwarden.com/en-gb/help/understand-log-in-vs-unlock/)
- [Architektur und Grenzen dieses Prototyps](decisions/0001-client-group-gate.md)

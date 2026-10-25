# IdP Reworked und Vaultwarden Reworked mit Samba-AD-Gruppenfilter

Stand: 25.10.2026. Veröffentlichte Vorabversion **0.1.0-rc.1**. Beide eigenständigen Pakete wurden auf NS8 Core 3.23.2 unter Debian 13 und Rocky 9 gemeinsam geprüft, jeweils 9/9 Tests. [Release-Prüfnachweise und Digests](RELEASE-0.1.0-rc.1.md). Die historischen Prototyp-Prüfungen bleiben separat dokumentiert.
Der unveränderte Upstream-IdP bietet weder den Parameter `access_group` von
`alter-realm-client` noch die Aktion `get-client-access`. Nur SSO einzuschalten
oder AD-Gruppen zu importieren beschränkt den Zugang noch nicht.

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

## 2. Zusammengehörige Vorabversionen festlegen

Beide Modulversionen fest pinnen. Die Runtimes werden in den Modulpaketen per Digest referenziert.

```bash
VW_VERSION='0.1.0-rc.1'
VW_IDP_IMAGE="ghcr.io/platypuschan/idp-reworked:${VW_VERSION}"
VW_APP_IMAGE="ghcr.io/platypuschan/vaultwarden-reworked:${VW_VERSION}"
```

Die Vaultwarden-Runtime enthält den SSO-only-Patch gegen persönliche API-Key-Gerätelogins. Die IdP-Runtime enthält die ursprünglichen NS8-Provider und den Client-Gruppenprüfer. Kein `latest`, kein Stable-/Katalogrelease. Vor einer Installation müssen beide Modul- und Runtime-Pakete anonym abrufbar sein.

## 3. IdP auf Knoten 1 installieren und HTTPS konfigurieren

```bash
add-module "$VW_IDP_IMAGE" 1
```

Im Beispiel lautet die zurückgegebene ID `idp-reworked1`:

```bash
api-cli run module/idp-reworked1/configure-module --data \
  '{"host":"sso.example.com","lets_encrypt":true}'

api-cli run module/idp-reworked1/get-configuration
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

Zurückgegebene ID im Beispiel: `vaultwarden-reworked1`.

```bash
api-cli run module/vaultwarden-reworked1/prepare-sso --data \
  '{"host":"vaultwarden.example.com","domain":"ad.example.com","idp_module":"idp-reworked1","required_group":"services_vaultwarden","lets_encrypt":true}'
```

Diese Aktion bindet das Modul an die vorhandene NS8-Domäne und registriert den
OIDC-Client. Sie gibt **kein Client-Secret** aus und startet Vaultwarden noch
nicht. Damit entsteht nicht versehentlich ein Dienst ohne angewendeten Filter.
`prepare-sso` ist nur vor der ersten Aktivierung vorgesehen.

| OIDC-Eigenschaft | Wert |
|---|---|
| Realm | `ad.example.com` |
| Client-ID | tatsächliche Vaultwarden-Modul-ID, hier `vaultwarden-reworked1` |
| Issuer | `https://sso.example.com/realms/ad.example.com` |
| Callback | `https://vaultwarden.example.com/identity/connect/oidc-signin` |
| Discovery | Issuer + `/.well-known/openid-configuration` |

Die Callback-Adresse bleibt auch für Android dieselbe: Vaultwarden übernimmt
anschließend den Rücksprung in die App (`bitwarden://sso-callback`). Nicht
diese App-URI als alleinigen Keycloak-Callback eintragen.

## 5. Gruppenregel administrativ setzen

Die AD-Gruppe muss vorhanden sein. Falls nötig in NS8 unter „Domänen und
Benutzer“ die Domäne auswählen und die Gruppe anlegen. Vorgesehene Benutzer direkt aufnehmen und
deren `mail`-Attribut prüfen. Der Pfad bezeichnet die von Keycloak importierte
AD-Gruppe, keine Vaultwarden-Organisation und keinen OIDC-Scope.

```bash
api-cli run module/idp-reworked1/alter-realm-client --data \
  '{"domain":"ad.example.com","client_id":"vaultwarden-reworked1","access_group":"services_vaultwarden"}'

api-cli run module/idp-reworked1/get-client-access --data \
  '{"domain":"ad.example.com","client_id":"vaultwarden-reworked1"}'
```

Erwartet werden `enforced:true`, `enabled:true`, `issues:[]` und
`group_path:"/services_vaultwarden"`. `list-realms` zeigt die Gruppe zusätzlich
als `access_group` des Clients. Die Aktion importiert die Gruppenobjekte,
aktiviert im Realm die Required Action `ns8-client-access` und hängt die
Tokenprüfung an den Client.

Was sich gegenüber dem ersten Prototyp geändert hat:

- Kein eigener Anmeldeflow pro Client. Keycloak wertet die Required Action nach
  jeder Anmeldung aus: Passwort, vorhandene SSO-Sitzung und Anmeldung über einen
  federierten IdP (z. B. Entra ID). Login-Modus `federated`, Passwortsperre
  federierter Konten bleiben erhalten. Künftige MFA-Szenarien benötigen eigene Kompatibilitätstests.
- Der LDAP-Benutzercache bleibt eingeschaltet. Die Prüfung entfernt nur den
  anmeldenden Benutzer aus dem Cache und liest seine Gruppen live aus LDAP.
- Auch eine schreibbare Federation (Realm mit federiertem IdP) wird
  unterstützt; Voraussetzung ist nur der read-only Gruppenmapper von ns8-idp.
- Clients ohne Gruppenregel sind unverändert.

Regel wieder entfernen (die Tokenprüfung wird mit entfernt):

```bash
api-cli run module/idp-reworked1/alter-realm-client --data \
  '{"domain":"ad.example.com","client_id":"vaultwarden-reworked1","access_group":null}'
```

Wird die AD-Gruppe umbenannt oder gelöscht, kann sich niemand mehr anmelden;
die strukturelle Statusabfrage kann bei noch importierter Gruppe dennoch `enforced:true` melden; echte Anmeldungen werden trotzdem verweigert. Regel mit dem neuen Namen
erneut setzen. Nach dem Entfernen des Vaultwarden-Moduls löscht der IdP den
Client samt Regel. Eine Neuinstallation mit gleicher Modul-ID braucht die Regel
erneut, Vaultwarden startet vorher nicht.

Schlägt das Setzen teilweise fehl, bleibt der Client absichtlich deaktiviert.
Ursache beheben und Regel erneut setzen; nicht einfach ohne gültige Regel
aktivieren. Nach erfolgreicher Reparatur lässt sich der Client administrativ
wieder aktivieren:

```bash
api-cli run module/idp-reworked1/alter-realm-client --data \
  '{"domain":"ad.example.com","client_id":"vaultwarden-reworked1","enabled":true}'
```

Der IdP stellt beim Start und bei Domänenereignissen fehlende Teile einer Regel
wieder her (Tokenprüfung, aktivierte Required Action) ohne bestehende Clients wieder zu aktivieren. Eine Migration alter Prototyp-Flows ist im eigenständigen IdP-Modul nicht enthalten.

Keine Änderung an `ns8-agent`, dessen Secret oder den AD-Servicekonten nötig.
Die Anwendung hat keine Berechtigung, `alter-realm-client` aufzurufen; sie kann
nur ihre eigene Regel mit `get-client-access` lesen.

## 6. Vaultwarden aktivieren

```bash
api-cli run module/vaultwarden-reworked1/configure-module --data \
  '{"host":"vaultwarden.example.com","domain":"ad.example.com","idp_module":"idp-reworked1","required_group":"services_vaultwarden","lets_encrypt":true}'

api-cli run module/vaultwarden-reworked1/get-configuration

curl --fail --silent --show-error https://vaultwarden.example.com/alive
```

Die Aktivierung scheitert, wenn die Gruppenregel fehlt, deaktiviert ist oder
nicht zur konfigurierten Gruppe passt. Der Dienst läuft im **Benutzer-systemd-
Kontext des Moduls**, nicht als Systemdienst `vaultwarden.service` des Hosts:

```bash
runagent -m vaultwarden-reworked1 systemctl --user status vaultwarden.service
runagent -m vaultwarden-reworked1 podman ps
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
verwenden (Vaultwarden-Upstream-Empfehlung für Keycloak). Das Vaultwarden-Modul
fordert bei der Registrierung über den optionalen `register-client`-Parameter
`access_token_lifespan` 600 Sekunden an; andere Clients behalten den
Realm-Standard. Nach einem Gruppenentzug laufen bestehende Vaultwarden-Sitzungen
höchstens bis zum Ablauf dieses Tokens weiter, die Erneuerung wird abgelehnt.
Die SSO-/Client-Sitzungslaufzeiten des Realms bestimmen die reguläre erneute
Anmeldung.

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

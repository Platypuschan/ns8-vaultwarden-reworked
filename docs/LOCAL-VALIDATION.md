# Lokale Vorbereitung, 25.10.2026

Basis: 4862c79 (neuester angepasster Vaultwarden-Prototyp). IdP-Quellstand ist per IDP_REF gepinnt, IdP-Modulpaket per IDP_IMAGE auf 0.1.0-rc.1. Die bisherigen IdP-Overlaydateien sind nur historischer Bestand und werden nicht als Runtime oder IdP-Modul gebaut.

- Vaultwarden-Modulpaket mit neuer NS8-Autorisierung idp-reworked@any:clientadm und passender VAULTWARDEN_REWORKED_SERVER_IMAGE-Variable lokal gebaut; Metadaten geprüft.
- 7 Konfigurations-/Bindungstests grün; Python-/JSON-/Shellsyntax grün.
- Gemeinsame lokale Samba-AD/Keycloak/gepatchter-Vaultwarden-Suite: 15 Tests grün (62.345 s). Die bisherige Migrationstestmethode für alte Prototyp-Flows entfällt, weil der unabhängige IdP keine solche Migration enthält.
- Vollständiger neuer IdP-Runtime verwendet; Vaultwarden-Binary aus vorhandenem unverändertem gepatchtem Runtime wiederverwendet. Das neue Rust-Rezept ändert nur das Repository-Label; keine Behauptung eines frischen Rust-Neubaus.
- Robot-Dryrun der neun NS8-Testfälle erfolgreich. Das ist keine ausgeführte NS8-Installation.
- Die neuen Workflows sind mit actionlint 1.7.12 geprüft.

Noch offen: Paketveröffentlichung und echte gemeinsame NS8-QEMU-Installation mit neuem Paketnamen auf Debian 13/Rocky 9, anschließend RC-Promotion. Kein Stable-/Katalogrelease und keine produktive Instanz geändert. Neue GHCR-Pakete müssen anonym lesbar sein.

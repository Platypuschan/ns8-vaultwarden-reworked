Erste Vorabversion des angepassten Vaultwarden-Moduls für NethServer 8.

- SSO über `idp-reworked` und den vorhandenen internen Samba-AD.
- Aktivierung nur bei eingerichteter administrativer Gruppenregel für den Client.
- SSO-only einschließlich Sperre des persönlichen API-Key-Gerätelogins.
- Eigene Pakete `vaultwarden-reworked` und `vaultwarden-reworked-server`.
- Private Konfiguration, persistentes Datenvolume und konsistenter Backup-Snapshot.

Voraussetzung: `idp-reworked:0.1.0-rc.1`, NS8 Core 3.23.2 oder neuer und direkte Mitgliedschaft in der freigegebenen AD-Gruppe. Konfiguration per API; keine Stable-/Katalogfreigabe. Offline-Tresore werden durch Gruppenentzug nicht gelöscht. Physische Mobilgeräte und vollständige Cluster-Wiederherstellung sind nicht abgedeckt.

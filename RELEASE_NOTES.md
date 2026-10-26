Fünfte Vorabversion von Vaultwarden Reworked für NethServer 8.

- Die Adminoberfläche öffnet sich im Anwendungsbereich des Cluster-Managers, statt den ganzen Browser-Tab zu ersetzen. Der Cluster-Manager bleibt geöffnet.
- Vaultwarden erlaubt dafür den HTTPS-Adressen der Clusterknoten das Einbetten. Der Wert wird von NS8 verwaltet, ist in der Adminoberfläche schreibgeschützt und wird beim Update von rc.4 automatisch gesetzt.
- Wird der Cluster-Manager über eine andere Adresse oder Domain aufgerufen als die Knoten-FQDN (der Admin-Cookie verlangt dieselbe Domain), erscheint die Schaltfläche **In neuem Tab öffnen**. Der Cluster-Manager wird nie ersetzt.
- Dokumentiert: Direktlink `https://<vaultwarden-host>/#/sso?identifier=00000000-01DC-01DC-01DC-000000000000` führt ohne E-Mail-Eingabe und SSO-Schaltfläche direkt zur IdP-Anmeldung. Das Masterpasswort zum Entsperren bleibt erforderlich.
- IdP bleibt auf 0.1.0-rc.2.

Die Veröffentlichung erfolgt nach erfolgreichen Unit-, Browser-, Protokoll- und NS8-QEMU-Prüfungen, einschließlich Update von rc.4. Keine Stable-/Katalogfreigabe und kein automatischer Rollout auf die Nutzerinstanz. Offline-Tresore lassen sich weiterhin nicht serverseitig löschen; vollständige Cluster-Wiederherstellung und Mehrknoten-SSO sind nicht nachgewiesen.

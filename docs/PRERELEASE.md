# Vorabversion 0.1.0-rc.3

Branch codex/pasta-network. VERSION ist 0.1.0-rc.3, IdP bleibt unverändert 0.1.0-rc.2 (IDP_REF 53c89822fd68). Die Runtime ist unverändert und wird anhand runtime-cache.json per Digest wiederverwendet.

Der Auftrag vom 26.10.2026 umfasst Integration, Tests und Bereitstellung des korrigierten Pakets.

1. PR veröffentlichen und den Workflow Prepare prerelease auf dem Branch mit publish=false ausführen. Kandidaten werden gebaut; es entsteht kein Release.
2. Protokolltests sowie NS8-QEMU auf Debian13/Rocky9 müssen erfolgreich sein. Die Suite installiert zunächst rc.2, konfiguriert sie und aktualisiert auf den Kandidaten. Zusätzlich wird eine frische Kandidateninstanz installiert. Auf pasta laufen Discovery-/Neuerstellungs- und TLS-Gatewaytests; bei anderen Backends werden die beiden gezielten pasta-Tests übersprungen.
3. Nach grünen Prüfungen PR nach main übernehmen. Prepare prerelease auf main mit publish=true ausführen. Erst nach erneut erfolgreichen Tests werden die geprüften Digests als rc.3 veröffentlicht. Vorhandene Tags werden niemals überschrieben.
4. Release-Digests und Nachweise dokumentieren. README/Installation auf den veröffentlichten Stand setzen.

Ein automatischer Rollout auf die Nutzerinstanz ist nicht enthalten. Das Update wird über cluster/update-module durchgeführt; Details inklusive Entfernung des spezifischen Test-Drop-ins siehe NETWORK-FIX.md. Der IdP bleibt auf rc.2.

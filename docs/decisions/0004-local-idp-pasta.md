# 0004: Route a co-located IdP through Podman's host gateway

Date: 2026-10-26. Status: implemented, pending release.

## Observed failure

On the user's NS8 test node, rootless Podman used pasta. The IdP's public
hostname resolved to the node's own public address. Requests from the host
worked, but the app container immediately refused the connection. Disabling
the provider firewall did not help. HTTPS through host.containers.internal
worked with the original hostname, SNI and certificate validation.

Pasta copies the host interface address into the container; the container's
own address shadows that of the host. Podman provides host-gateway for this
case. A manual /etc/hosts entry disappears on restart and is not a package fix.

## Decision

Before every service start, read the IdP's current node from NS8 Redis
cluster/module_node and compare it to NODE_ID. These cluster keys are already
readable by module agents; no additional role or secret is needed.

Only for a co-located IdP and the pasta backend, pass
--add-host=<issuer-hostname>:host-gateway to podman run. Do not hard-code the
current gateway IP. A remote IdP and other network backends keep their normal
DNS resolution. Unknown node metadata prevents startup rather than reusing
a stale alias. The generated environment file is overwritten on every start,
including after restore, update and container recreation.

The public DNS, OIDC issuer, Host header, SNI and certificate verification stay
unchanged. There is no new HTTP endpoint and no host network mode. The alias
is deliberately tied to a local IdP served by the node's Traefik; external
frontends for a co-located IdP are outside the supported test topology.

When automatic HTTPS is enabled, configure-module checks discovery from the
actual app container, retrying certificate issuance for a bounded period and
validating the returned issuer. Failure is reported instead of configured:true.
For manually managed certificates, oidc_verified:false explicitly indicates
that this automated check was not run. The service and timer may already be
running after a failed check; configuration can be retried after fixing HTTPS.

The previous manual 90-test-idp-host.conf override is not deleted automatically:
operators remove that specific workaround after installing the corrected
package. Other local systemd overrides are preserved.

## Verification

Unit tests cover local/remote nodes, unknown metadata, relocation and discovery
failures. tests/network/run.py uses pasta and trusted test HTTPS, reproduces the
failure without the mapping, and checks restart, recreation and TLS rejection.
The NS8 suite additionally checks discovery from the installed container after
service restart on pasta. It uses -k only for its self-signed QEMU fixture.

Sources:
- https://docs.podman.io/en/latest/markdown/podman-create.1.html (--add-host)
- https://passt.top/builds/latest/web/passt.1.html (--map-guest-addr)
- NS8 core f79ead64ba67d7be5ec9ae31c50d70fe32d6da6d:
  core/imageroot/var/lib/nethserver/cluster/actions/add-module/50update
  (read ACLs and module-node metadata). The same ACL and module-node hash
  were also verified against tag 3.23.2.

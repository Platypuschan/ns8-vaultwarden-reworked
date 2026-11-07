FROM scratch
COPY imageroot /imageroot
COPY ui /ui
ENTRYPOINT ["/"]
ARG VAULTWARDEN_IMAGE=ghcr.io/platypuschan/vaultwarden-reworked-server@sha256:7c510ee9a9a689aef8d8f64ab846d6b223e5181227dd431c9885d02ca8b1ac87
LABEL org.opencontainers.image.source="https://github.com/Platypuschan/ns8-vaultwarden-reworked" \
      org.nethserver.authorizations="traefik@node:routeadm cluster:accountconsumer idp-reworked@any:clientadm" \
      org.nethserver.tcp-ports-demand="1" \
      org.nethserver.rootfull="0" \
      org.nethserver.min-core="3.23.2" \
      org.nethserver.images="${VAULTWARDEN_IMAGE}"

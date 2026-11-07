FROM scratch
COPY imageroot /imageroot
COPY ui /ui
ENTRYPOINT ["/"]
ARG VAULTWARDEN_IMAGE=ghcr.io/platypuschan/vaultwarden-reworked-server@sha256:0d0332fa274b3d12f30c82611735a72cd2bb30a17c9bc1dd0b90d96d3cafadf0
LABEL org.opencontainers.image.source="https://github.com/Platypuschan/ns8-vaultwarden-reworked" \
      org.nethserver.authorizations="traefik@node:routeadm cluster:accountconsumer idp-reworked@any:clientadm" \
      org.nethserver.tcp-ports-demand="1" \
      org.nethserver.rootfull="0" \
      org.nethserver.min-core="3.23.2" \
      org.nethserver.images="${VAULTWARDEN_IMAGE}"

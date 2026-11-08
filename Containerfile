FROM scratch
COPY imageroot /imageroot
COPY ui /ui
ENTRYPOINT ["/"]
ARG VAULTWARDEN_IMAGE=ghcr.io/platypuschan/vaultwarden-reworked-server@sha256:2988ba83c8c7599faaf9d15876bc2358b43465bbbbac869e791dd82d5cf18b8b
LABEL org.opencontainers.image.source="https://github.com/Platypuschan/ns8-vaultwarden-reworked" \
      org.nethserver.authorizations="traefik@node:routeadm cluster:accountconsumer idp-reworked@any:clientadm" \
      org.nethserver.tcp-ports-demand="1" \
      org.nethserver.rootfull="0" \
      org.nethserver.min-core="3.23.2" \
      org.nethserver.images="${VAULTWARDEN_IMAGE}"

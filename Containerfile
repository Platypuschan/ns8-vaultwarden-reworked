FROM scratch
COPY imageroot /imageroot
COPY ui /ui
ENTRYPOINT ["/"]
LABEL org.opencontainers.image.source="https://github.com/Platypuschan/ns8-vaultwarden" \
      org.nethserver.authorizations="traefik@node:routeadm cluster:accountconsumer idp@any:clientadm idp-vaultwarden-prototype@any:clientadm" \
      org.nethserver.tcp-ports-demand="1" \
      org.nethserver.rootfull="0" \
      org.nethserver.min-core="3.23.2" \
      org.nethserver.images="docker.io/vaultwarden/server:1.37.2"

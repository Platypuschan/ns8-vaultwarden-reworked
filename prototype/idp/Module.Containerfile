FROM ghcr.io/nethserver/idp@sha256:8fedb77f0071ec01e939f68045f2abff9bc26555c1101f3863a12386df715662
COPY prototype/idp/overlay /imageroot
COPY prototype/idp/idpaccess.py /imageroot/pypkg/idpaccess.py
ARG KEYCLOAK_IMAGE=ghcr.io/platypuschan/idp-keycloak:codex-vaultwarden-sso
LABEL org.opencontainers.image.source="https://github.com/Platypuschan/ns8-vaultwarden" \
      org.nethserver.images="${KEYCLOAK_IMAGE} docker.io/library/postgres:18.6-trixie"

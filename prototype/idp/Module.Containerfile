FROM ghcr.io/nethserver/idp@sha256:d7594ca362de5e162ab93f9c0e30fd39e41f94d00c7fef0c4926dcf8ce9232bd
COPY prototype/idp/overlay /imageroot
COPY prototype/idp/idpaccess.py /imageroot/pypkg/idpaccess.py
ARG KEYCLOAK_IMAGE=ghcr.io/platypuschan/idp-keycloak:codex-vaultwarden-sso
LABEL org.opencontainers.image.source="https://github.com/Platypuschan/ns8-vaultwarden" \
      org.nethserver.images="${KEYCLOAK_IMAGE} docker.io/library/postgres:18.6-trixie"

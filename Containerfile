# Build the module page (Vue 2 / Carbon, like the other NS8 modules)
FROM docker.io/library/node:24.22.3 AS ui
WORKDIR /usr/src/ui
COPY ui/package.json ui/yarn.lock ui/.yarnrc.yml ./
RUN corepack enable && yarn install --immutable
COPY ui/ ./
RUN yarn build

# Ship a small, Python-version-independent verifier for the PHC emitted by
# Vaultwarden. Bullseye's glibc baseline also works on Rocky 9 and Debian 13.
FROM docker.io/library/debian:bullseye-slim@sha256:e5b6442dd2e9684cf5e87d8338b5968f3b348636fc0be6d7850a381e3731a2bd AS credential-verifier
RUN apt-get update && apt-get install -y --no-install-recommends libargon2-1 \
    && mkdir /out && cp /usr/lib/*/libargon2.so.1 /out/ \
    && cp /usr/share/doc/libargon2-1/copyright /out/COPYRIGHT

FROM scratch
COPY imageroot /imageroot
COPY --from=credential-verifier /out/ /imageroot/lib/
COPY --from=ui /usr/src/ui/dist /ui
ENTRYPOINT ["/"]
ARG VAULTWARDEN_IMAGE=ghcr.io/platypuschan/vaultwarden-reworked-server@sha256:0020ceec042689499880786e6224ab2b030d33864e2e063c4a73f6a9448ad91e
LABEL org.opencontainers.image.source="https://github.com/Platypuschan/ns8-vaultwarden-reworked" \
      org.nethserver.authorizations="traefik@node:routeadm cluster:accountconsumer idp-reworked@any:clientadm" \
      org.nethserver.tcp-ports-demand="1" \
      org.nethserver.rootfull="0" \
      org.nethserver.min-core="3.23.2" \
      org.nethserver.images="${VAULTWARDEN_IMAGE}"

# Build the module page (Vue 2 / Carbon, like the other NS8 modules)
FROM docker.io/library/node:24.20.0 AS ui
WORKDIR /usr/src/ui
COPY ui/package.json ui/yarn.lock ./
RUN corepack enable && yarn install --immutable
COPY ui/ ./
RUN yarn build

FROM scratch
COPY imageroot /imageroot
COPY --from=ui /usr/src/ui/dist /ui
ENTRYPOINT ["/"]
ARG VAULTWARDEN_IMAGE=ghcr.io/platypuschan/vaultwarden-reworked-server@sha256:8b045f46220776a4041e0b003f29b12c72593ad84829882ac7c3365a7e0f756e
LABEL org.opencontainers.image.source="https://github.com/Platypuschan/ns8-vaultwarden-reworked" \
      org.nethserver.authorizations="traefik@node:routeadm cluster:accountconsumer idp-reworked@any:clientadm" \
      org.nethserver.tcp-ports-demand="1" \
      org.nethserver.rootfull="0" \
      org.nethserver.min-core="3.23.2" \
      org.nethserver.images="${VAULTWARDEN_IMAGE}"

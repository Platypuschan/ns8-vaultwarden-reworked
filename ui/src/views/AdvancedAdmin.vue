<!--
  SPDX-License-Identifier: GPL-3.0-or-later
-->
<template>
  <cv-grid fullWidth>
    <cv-row>
      <cv-column class="page-title">
        <h2>{{ $t("admin.title") }}</h2>
      </cv-column>
    </cv-row>
    <cv-row v-if="error">
      <cv-column>
        <NsInlineNotification
          kind="error"
          :title="$t('admin.title')"
          :description="error"
          :showCloseButton="false"
        />
      </cv-column>
    </cv-row>
    <cv-row v-if="warning">
      <cv-column>
        <NsInlineNotification
          kind="warning"
          :title="$t('admin.title')"
          :description="warning"
          :showCloseButton="false"
        />
      </cv-column>
    </cv-row>
    <cv-row>
      <cv-column>
        <p class="mg-bottom">{{ $t("admin.help") }}</p>
        <cv-skeleton-text
          v-if="loading && !embedded"
          :paragraph="true"
          :line-count="4"
        />
        <div v-if="!embedded && !loading" class="mg-bottom">
          <NsButton kind="primary" @click="openInTab">{{
            $t("admin.open_tab")
          }}</NsButton>
          <p v-if="tabOpen" class="mg-top">{{ $t("admin.tab_open") }}</p>
        </div>
        <iframe
          v-show="embedded"
          ref="frame"
          name="vaultwarden-admin-frame"
          :title="$t('admin.title')"
          class="admin-frame"
        ></iframe>
      </cv-column>
    </cv-row>
  </cv-grid>
</template>

<script>
import { mapState } from "vuex";
import { TaskService, UtilService } from "@nethserver/ns8-ui-lib";
import panelTask from "../mixins/panelTask";

const TAB_NAME = "vaultwarden-admin";

export default {
  name: "AdvancedAdmin",
  mixins: [TaskService, UtilService, panelTask],
  data() {
    return {
      loading: false,
      embedded: false,
      tabOpen: false,
      error: "",
      warning: "",
      renewal: null,
      // Renews the admin session. It never leaves this page; Vaultwarden
      // keeps only its hash.
      handle: this.newHandle(),
    };
  },
  computed: {
    ...mapState(["instanceName", "core"]),
  },
  created() {
    this.open(null);
  },
  beforeDestroy() {
    clearInterval(this.renewal);
  },
  methods: {
    newHandle() {
      const bytes = crypto.getRandomValues(new Uint8Array(32));
      return btoa(String.fromCharCode(...bytes))
        .replace(/\+/g, "-")
        .replace(/\//g, "_")
        .replace(/=+$/, "");
    },
    destination(result) {
      const url = new URL(result.url);
      if (
        url.protocol !== "https:" ||
        url.pathname !== "/admin/" ||
        url.username ||
        url.password ||
        typeof result.ticket !== "string"
      ) {
        throw new Error(this.$t("admin.invalid_answer"));
      }
      return url;
    },
    openInTab() {
      // A tab is only allowed directly after a click
      this.open(window.open("", TAB_NAME));
    },
    async open(tab) {
      this.loading = true;
      this.error = "";
      try {
        const result = await this.runPanelTask("open-admin");
        const revocation = result.revocation || {};
        this.warning =
          revocation.reason === "idp_update_required"
            ? this.$t("diagnostics.idp_update_required")
            : revocation.state === "warning"
            ? this.$t("diagnostics.revocation_warning")
            : "";
        const url = this.destination(result);
        const embed =
          !tab &&
          (result.frame_ancestors || []).includes(
            window.parent.location.origin
          );
        if (!embed && !tab) {
          this.embedded = false;
          this.loading = false;
          return;
        }
        this.submit(
          url,
          result.ticket,
          embed ? this.$refs.frame.name : TAB_NAME
        );
        this.embedded = embed;
        this.tabOpen = !embed;
        this.startRenewal(result.session_seconds || 120);
      } catch (e) {
        if (tab) {
          tab.close();
        }
        this.error = e.message;
      }
      this.loading = false;
    },
    submit(url, ticket, target) {
      const form = document.createElement("form");
      form.method = "POST";
      form.action = url.href;
      form.target = target;
      form.hidden = true;
      const input = document.createElement("input");
      input.type = "hidden";
      input.name = "token";
      input.value = ticket + ":" + this.handle;
      form.appendChild(input);
      document.body.appendChild(form);
      form.submit();
      form.remove();
    },
    startRenewal(seconds) {
      if (this.renewal) {
        return;
      }
      const renew = async () => {
        try {
          const result = await this.runPanelTask("open-admin");
          const url = this.destination(result);
          // The answer is opaque, and its resource policy may block it: only
          // a refused ticket ends the renewal.
          fetch(new URL("ns8/renew", url), {
            method: "POST",
            mode: "no-cors",
            credentials: "omit",
            body: new URLSearchParams({
              token: result.ticket + ":" + this.handle,
            }),
          }).catch(() => {});
        } catch (e) {
          clearInterval(this.renewal);
          this.renewal = null;
          this.warning = this.$t("admin.renewal_failed") + " " + e.message;
        }
      };
      this.renewal = setInterval(renew, Math.max(5, seconds / 4) * 1000);
    },
  },
};
</script>

<style scoped lang="scss">
@import "../styles/carbon-utils";

.mg-bottom {
  margin-bottom: $spacing-05;
}

.mg-top {
  margin-top: $spacing-05;
}

.admin-frame {
  width: 100%;
  height: calc(100vh - 14rem);
  min-height: 30rem;
  border: 0;
  background: #fff;
}
</style>

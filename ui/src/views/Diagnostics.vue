<!--
  SPDX-License-Identifier: GPL-3.0-or-later
-->
<template>
  <cv-grid fullWidth>
    <cv-row>
      <cv-column class="page-title">
        <h2>{{ $t("diagnostics.title") }}</h2>
      </cv-column>
    </cv-row>
    <cv-row v-if="error">
      <cv-column>
        <NsInlineNotification
          kind="error"
          :title="$t('diagnostics.title')"
          :description="error"
          :showCloseButton="false"
        />
      </cv-column>
    </cv-row>
    <cv-row v-if="revocationProblem">
      <cv-column>
        <NsInlineNotification
          kind="warning"
          :title="$t('diagnostics.revocation')"
          :description="revocationProblem"
          :showCloseButton="false"
        />
      </cv-column>
    </cv-row>
    <cv-row>
      <cv-column>
        <cv-tile light>
          <div class="mg-bottom">
            <NsButton kind="secondary" :disabled="loading" @click="load">{{
              $t("common.reload")
            }}</NsButton>
          </div>
          <cv-skeleton-text v-if="loading" :paragraph="true" :line-count="10" />
          <template v-else>
            <div v-for="section in sections" :key="section.title" class="section">
              <h4 class="mg-bottom">{{ section.title }}</h4>
              <table class="bx--data-table bx--data-table--compact">
                <tbody>
                  <tr v-for="row in section.rows" :key="row.label">
                    <th class="label">{{ row.label }}</th>
                    <td>
                      <cv-tag
                        v-if="row.kind"
                        :kind="row.kind"
                        :label="row.value"
                      />
                      <span v-else class="break">{{ row.value }}</span>
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
          </template>
        </cv-tile>
      </cv-column>
    </cv-row>
  </cv-grid>
</template>

<script>
import { mapState } from "vuex";
import { TaskService, UtilService } from "@nethserver/ns8-ui-lib";
import panelTask from "../mixins/panelTask";

export default {
  name: "Diagnostics",
  mixins: [TaskService, UtilService, panelTask],
  data() {
    return {
      data: null,
      revocation: {},
      loading: false,
      error: "",
    };
  },
  computed: {
    ...mapState(["instanceName", "core"]),
    revocationProblem() {
      const state = this.revocation || {};
      if (state.reason === "idp_update_required") {
        return this.$t("diagnostics.idp_update_required");
      }
      return state.state === "warning"
        ? this.$t("diagnostics.revocation_warning")
        : "";
    },
    sections() {
      const d = this.data;
      if (!d) {
        return [];
      }
      const yes = (value) => this.$t(value ? "common.yes" : "common.no");
      const ok = (value) => (value ? "green" : "red");
      const text = (value) => (value === "" || value == null ? "-" : String(value));
      const versionKind = (latest, current) =>
        latest === "-" ? "" : latest === current ? "green" : "blue";
      return [
        {
          title: this.$t("diagnostics.versions"),
          rows: [
            { label: this.$t("diagnostics.server_version"), value: text(d.current_release) },
            { label: this.$t("diagnostics.latest_release"), value: text(d.latest_release) },
            { label: this.$t("diagnostics.latest_commit"), value: text(d.latest_commit) },
            { label: this.$t("diagnostics.web_vault"), value: yes(d.web_vault_enabled), kind: ok(d.web_vault_enabled) },
            { label: this.$t("diagnostics.web_vault_version"), value: text(d.active_web_release), kind: versionKind(d.latest_web_release, d.active_web_release) },
            { label: this.$t("diagnostics.latest_web_vault"), value: text(d.latest_web_release) },
          ],
        },
        {
          title: this.$t("diagnostics.environment"),
          rows: [
            { label: this.$t("diagnostics.container"), value: yes(d.running_within_container) },
            { label: this.$t("diagnostics.base_image"), value: text(d.container_base_image) },
            { label: this.$t("diagnostics.arch"), value: text(d.host_arch + " / " + d.host_os) },
            { label: this.$t("diagnostics.database"), value: text(d.db_type + " " + d.db_version) },
            { label: this.$t("diagnostics.timezone"), value: text(d.tz_env) },
            { label: this.$t("diagnostics.config_file"), value: text(d.config_file_status) },
            { label: this.$t("diagnostics.overrides"), value: text(d.overrides) },
            { label: this.$t("diagnostics.template_overrides"), value: text(d.template_overrides) },
            { label: this.$t("diagnostics.invalid_env"), value: text(d.invalid_env_vars) },
            { label: this.$t("diagnostics.invalid_flags"), value: text((d.invalid_feature_flags || []).join(", ")) },
          ],
        },
        {
          title: this.$t("diagnostics.network"),
          rows: [
            { label: this.$t("diagnostics.internet"), value: yes(d.has_http_access), kind: ok(d.has_http_access) },
            { label: this.$t("diagnostics.dns"), value: text(d.dns_resolved) },
            { label: this.$t("diagnostics.proxy"), value: yes(d.uses_proxy) },
            { label: this.$t("diagnostics.websocket"), value: yes(d.enable_websocket), kind: ok(d.enable_websocket) },
            { label: this.$t("diagnostics.ip_header"), value: d.ip_header_exists ? yes(d.ip_header_match) : this.$t("diagnostics.ip_header_missing"), kind: d.ip_header_exists ? ok(d.ip_header_match) : "red" },
            { label: this.$t("diagnostics.ip_header_received"), value: text(d.ip_header_name) },
            { label: this.$t("diagnostics.ip_header_configured"), value: text(d.ip_header_config) },
          ],
        },
        {
          title: this.$t("diagnostics.time"),
          rows: [
            { label: this.$t("diagnostics.server_time"), value: text(d.server_time) },
            { label: this.$t("diagnostics.server_time_local"), value: text(d.server_time_local) },
            { label: this.$t("diagnostics.ntp_time"), value: text(d.ntp_time) },
          ],
        },
      ];
    },
  },
  created() {
    this.load();
  },
  methods: {
    async load() {
      this.loading = true;
      this.error = "";
      try {
        const [result, config] = await Promise.all([
          this.runPanelTask("query-panel-data", { section: "diagnostics" }),
          this.runPanelTask("get-configuration"),
        ]);
        this.data = result.data;
        this.revocation = config.revocation || {};
      } catch (e) {
        this.error = e.message;
      }
      this.loading = false;
    },
  },
};
</script>

<style scoped lang="scss">
@import "../styles/carbon-utils";

.mg-bottom {
  margin-bottom: $spacing-05;
}

.section {
  margin-bottom: $spacing-07;
}

.label {
  width: 18rem;
}

.break {
  word-break: break-word;
}
</style>

<!--
  SPDX-License-Identifier: GPL-3.0-or-later
-->
<template>
  <cv-grid fullWidth>
    <cv-row>
      <cv-column class="page-title">
        <h2>{{ $t("organizations.title") }}</h2>
      </cv-column>
    </cv-row>
    <cv-row v-if="error">
      <cv-column>
        <NsInlineNotification
          kind="error"
          :title="$t('organizations.title')"
          :description="error"
          @close="error = ''"
        />
      </cv-column>
    </cv-row>
    <cv-row v-if="done">
      <cv-column>
        <NsInlineNotification
          kind="success"
          :title="$t('organizations.title')"
          :description="done"
          @close="done = ''"
        />
      </cv-column>
    </cv-row>
    <cv-row>
      <cv-column>
        <cv-tile light>
          <div class="mg-bottom">
            <NsButton kind="secondary" :disabled="busy" @click="load">{{
              $t("common.reload")
            }}</NsButton>
          </div>
          <cv-skeleton-text v-if="loading" :paragraph="true" :line-count="6" />
          <div v-else class="table-wrapper">
            <table class="bx--data-table bx--data-table--compact">
              <thead>
                <tr>
                  <th>{{ $t("organizations.organization") }}</th>
                  <th>{{ $t("organizations.users") }}</th>
                  <th>{{ $t("organizations.entries") }}</th>
                  <th>{{ $t("organizations.attachments") }}</th>
                  <th>{{ $t("organizations.misc") }}</th>
                  <th>{{ $t("common.actions") }}</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="org in organizations" :key="org.id">
                  <td>
                    <strong>{{ org.name }}</strong>
                    <span v-if="org.billingEmail">
                      ({{ org.billingEmail }})</span
                    ><br />
                    <cv-tag kind="green" :label="org.id" />
                  </td>
                  <td>{{ org.user_count }}</td>
                  <td>{{ org.cipher_count }}</td>
                  <td>
                    {{ org.attachment_count }}
                    <span v-if="org.attachment_count">
                      ({{ org.attachment_size }})</span
                    >
                  </td>
                  <td>
                    {{ $t("organizations.collections") }}:
                    {{ org.collection_count }}<br />
                    {{ $t("organizations.groups") }}: {{ org.group_count
                    }}<br />
                    {{ $t("organizations.events") }}: {{ org.event_count }}
                  </td>
                  <td>
                    <NsButton
                      kind="danger--ghost"
                      size="small"
                      :disabled="busy"
                      @click="ask(org)"
                      >{{ $t("organizations.delete") }}</NsButton
                    >
                  </td>
                </tr>
                <tr v-if="!organizations.length">
                  <td colspan="6">{{ $t("organizations.none") }}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </cv-tile>
      </cv-column>
    </cv-row>
    <NsModal
      size="default"
      :visible="confirm.open"
      @modal-hidden="confirm.open = false"
      @primary-click="remove"
    >
      <template slot="title">{{ $t("organizations.delete") }}</template>
      <template slot="content">
        <p>{{ $t("organizations.confirm_delete", { name: confirm.name }) }}</p>
      </template>
      <template slot="secondary-button">{{ $t("common.cancel") }}</template>
      <template slot="primary-button">{{
        $t("organizations.delete")
      }}</template>
    </NsModal>
  </cv-grid>
</template>

<script>
import { mapState } from "vuex";
import { TaskService, UtilService } from "@nethserver/ns8-ui-lib";
import panelTask from "../mixins/panelTask";
import pageBinding from "../mixins/pageBinding";

export default {
  name: "Organizations",
  mixins: [TaskService, UtilService, panelTask, pageBinding("organizations")],
  data() {
    return {
      organizations: [],
      loading: false,
      working: false,
      error: "",
      done: "",
      confirm: { open: false, id: "", name: "" },
    };
  },
  computed: {
    ...mapState(["instanceName", "core"]),
    busy() {
      return this.loading || this.working;
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
        const result = await this.runPanelTask("query-panel-data", {
          section: "organizations",
        });
        this.organizations = result.data;
      } catch (e) {
        this.error = e.message;
      }
      this.loading = false;
    },
    ask(org) {
      this.confirm = { open: true, id: org.id, name: org.name };
    },
    async remove() {
      this.confirm.open = false;
      this.working = true;
      this.error = "";
      this.done = "";
      try {
        await this.runPanelTask("manage-organization", {
          org_id: this.confirm.id,
        });
        this.done = this.$t("organizations.deleted", {
          name: this.confirm.name,
        });
        await this.load();
      } catch (e) {
        this.error = e.message;
      }
      this.working = false;
    },
  },
};
</script>

<style scoped lang="scss">
@import "../styles/carbon-utils";

.mg-bottom {
  margin-bottom: $spacing-05;
}

.table-wrapper {
  overflow-x: auto;
}
</style>

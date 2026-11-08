<!--
  SPDX-License-Identifier: GPL-3.0-or-later
-->
<template>
  <cv-grid fullWidth>
    <cv-row>
      <cv-column class="page-title">
        <h2>{{ $t("users.title") }}</h2>
      </cv-column>
    </cv-row>
    <cv-row v-if="error">
      <cv-column>
        <NsInlineNotification
          kind="error"
          :title="$t('users.title')"
          :description="error"
          @close="error = ''"
        />
      </cv-column>
    </cv-row>
    <cv-row v-if="done">
      <cv-column>
        <NsInlineNotification
          kind="success"
          :title="$t('users.title')"
          :description="done"
          @close="done = ''"
        />
      </cv-column>
    </cv-row>
    <cv-row>
      <cv-column>
        <cv-tile light>
          <p class="mg-bottom">{{ $t("users.help") }}</p>
          <div class="toolbar mg-bottom">
            <NsButton kind="secondary" :disabled="busy" @click="load">{{
              $t("common.reload")
            }}</NsButton>
            <NsButton
              kind="danger-tertiary"
              :disabled="busy"
              @click="ask('resync-all')"
              >{{ $t("users.resync") }}</NsButton
            >
          </div>
          <cv-skeleton-text v-if="loading" :paragraph="true" :line-count="6" />
          <div v-else class="table-wrapper">
            <table class="bx--data-table bx--data-table--compact">
              <thead>
                <tr>
                  <th>{{ $t("users.user") }}</th>
                  <th>{{ $t("users.sso") }}</th>
                  <th>{{ $t("users.created") }}</th>
                  <th>{{ $t("users.last_active") }}</th>
                  <th>{{ $t("users.entries") }}</th>
                  <th>{{ $t("users.attachments") }}</th>
                  <th>{{ $t("users.organizations") }}</th>
                  <th>{{ $t("common.actions") }}</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="user in users" :key="user.id">
                  <td>
                    <strong>{{ user.name || user.email }}</strong
                    ><br />{{ user.email }}<br />
                    <cv-tag
                      v-if="!user.user_enabled"
                      kind="red"
                      :label="$t('users.disabled')"
                    />
                    <cv-tag
                      v-if="user._status === 1"
                      kind="blue"
                      :label="$t('users.invited')"
                    />
                    <cv-tag
                      v-if="user.twoFactorEnabled"
                      kind="green"
                      label="2FA"
                    />
                  </td>
                  <td class="break">{{ user.sso_identifier }}</td>
                  <td class="nowrap">{{ user.created_at }}</td>
                  <td class="nowrap">{{ user.last_active }}</td>
                  <td>{{ user.cipher_count }}</td>
                  <td>
                    {{ user.attachment_count }}
                    <span v-if="user.attachment_count">
                      ({{ user.attachment_size }})</span
                    >
                  </td>
                  <td>
                    <NsButton
                      v-for="org in user.organizations"
                      :key="org.id"
                      kind="ghost"
                      size="small"
                      :disabled="busy"
                      @click="openRole(user, org)"
                      >{{ org.name }} ({{ roleName(org.type) }})</NsButton
                    >
                  </td>
                  <td class="actions">
                    <NsButton
                      v-if="user.twoFactorEnabled"
                      kind="ghost"
                      size="small"
                      :disabled="busy"
                      @click="ask('remove-2fa', user)"
                      >{{ $t("users.remove_2fa") }}</NsButton
                    >
                    <NsButton
                      kind="ghost"
                      size="small"
                      :disabled="busy"
                      @click="ask('deauth', user)"
                      >{{ $t("users.deauth") }}</NsButton
                    >
                    <NsButton
                      v-if="user.user_enabled"
                      kind="ghost"
                      size="small"
                      :disabled="busy"
                      @click="ask('disable', user)"
                      >{{ $t("users.disable") }}</NsButton
                    >
                    <NsButton
                      v-else
                      kind="ghost"
                      size="small"
                      :disabled="busy"
                      @click="ask('enable', user)"
                      >{{ $t("users.enable") }}</NsButton
                    >
                    <NsButton
                      v-if="user.sso_identifier"
                      kind="danger--ghost"
                      size="small"
                      :disabled="busy"
                      @click="ask('delete-sso', user)"
                      >{{ $t("users.delete_sso") }}</NsButton
                    >
                    <NsButton
                      kind="danger--ghost"
                      size="small"
                      :disabled="busy"
                      @click="ask('delete', user)"
                      >{{ $t("users.delete") }}</NsButton
                    >
                  </td>
                </tr>
                <tr v-if="!users.length">
                  <td colspan="8">{{ $t("users.none") }}</td>
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
      @primary-click="runConfirmed"
    >
      <template slot="title">{{ confirm.title }}</template>
      <template slot="content">
        <p>{{ confirm.text }}</p>
      </template>
      <template slot="secondary-button">{{ $t("common.cancel") }}</template>
      <template slot="primary-button">{{ $t("common.confirm") }}</template>
    </NsModal>
    <NsModal
      size="default"
      :visible="role.open"
      @modal-hidden="role.open = false"
      @primary-click="saveRole"
    >
      <template slot="title">{{ $t("users.change_role") }}</template>
      <template slot="content">
        <p class="mg-bottom">
          {{ $t("users.change_role_for", { user: role.email, org: role.org }) }}
        </p>
        <cv-select :label="$t('users.role')" v-model="role.value">
          <cv-select-option value="user">{{
            $t("users.role_user")
          }}</cv-select-option>
          <cv-select-option value="manager">{{
            $t("users.role_manager")
          }}</cv-select-option>
          <cv-select-option value="admin">{{
            $t("users.role_admin")
          }}</cv-select-option>
          <cv-select-option value="owner">{{
            $t("users.role_owner")
          }}</cv-select-option>
        </cv-select>
      </template>
      <template slot="secondary-button">{{ $t("common.cancel") }}</template>
      <template slot="primary-button">{{ $t("users.change_role") }}</template>
    </NsModal>
  </cv-grid>
</template>

<script>
import { mapState } from "vuex";
import { TaskService, UtilService } from "@nethserver/ns8-ui-lib";
import panelTask from "../mixins/panelTask";
import pageBinding from "../mixins/pageBinding";

const ROLE_NAMES = { 0: "owner", 1: "admin", 2: "user", 3: "manager" };

export default {
  name: "Users",
  mixins: [TaskService, UtilService, panelTask, pageBinding("users")],
  data() {
    return {
      users: [],
      loading: false,
      working: false,
      error: "",
      done: "",
      confirm: { open: false, title: "", text: "", operation: "", user: null },
      role: {
        open: false,
        email: "",
        org: "",
        value: "user",
        user: "",
        id: "",
      },
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
    roleName(type) {
      return this.$t("users.role_" + (ROLE_NAMES[type] || "user"));
    },
    async load() {
      this.loading = true;
      this.error = "";
      try {
        const result = await this.runPanelTask("query-panel-data", {
          section: "users",
        });
        this.users = result.data;
      } catch (e) {
        this.error = e.message;
      }
      this.loading = false;
    },
    ask(operation, user = null) {
      const name = user ? user.email : "";
      this.confirm = {
        open: true,
        operation,
        user,
        title: this.$t("users." + operation.replace("-", "_")),
        text: this.$t("users.confirm_" + operation.replace("-", "_"), {
          user: name,
        }),
      };
    },
    async runConfirmed() {
      const { operation, user } = this.confirm;
      this.confirm.open = false;
      await this.manage({ operation, user_id: user ? user.id : undefined });
    },
    openRole(user, org) {
      this.role = {
        open: true,
        email: user.email,
        org: org.name,
        user: user.id,
        id: org.id,
        value: ROLE_NAMES[org.type] || "user",
      };
    },
    async saveRole() {
      this.role.open = false;
      await this.manage({
        operation: "set-org-role",
        user_id: this.role.user,
        org_id: this.role.id,
        role: this.role.value,
      });
    },
    async manage(data) {
      this.working = true;
      this.error = "";
      this.done = "";
      try {
        await this.runPanelTask("manage-user", data);
        this.done = this.$t("users.done");
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

.toolbar {
  display: flex;
  gap: $spacing-05;
}

.table-wrapper {
  overflow-x: auto;
}

.break {
  word-break: break-all;
  max-width: 14rem;
}

.actions,
.nowrap {
  white-space: nowrap;
}
</style>

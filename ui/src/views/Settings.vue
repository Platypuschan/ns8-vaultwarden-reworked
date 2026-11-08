<!--
  SPDX-License-Identifier: GPL-3.0-or-later
-->
<template>
  <cv-grid fullWidth>
    <cv-row>
      <cv-column class="page-title">
        <h2>{{ $t("settings.title") }}</h2>
      </cv-column>
    </cv-row>
    <cv-row v-if="error.load">
      <cv-column>
        <NsInlineNotification
          kind="error"
          :title="$t('action.query-panel-data')"
          :description="error.load"
          :showCloseButton="false"
        />
      </cv-column>
    </cv-row>
    <cv-row v-if="notice.text">
      <cv-column>
        <NsInlineNotification
          :kind="notice.kind"
          :title="notice.title"
          :description="notice.text"
          @close="notice.text = ''"
        />
      </cv-column>
    </cv-row>
    <cv-row>
      <cv-column>
        <cv-skeleton-text v-if="loading.load" :paragraph="true" :line-count="8" />
        <cv-tile v-else light>
          <p class="intro">{{ $t("settings.intro") }}</p>
          <cv-accordion class="groups">
            <cv-accordion-item
              v-for="group in groups"
              :key="group.group"
              :open="group.group === 'settings'"
            >
              <template slot="title">{{ groupTitle(group) }}</template>
              <template slot="content">
                <template v-if="group.group === 'smtp'">
                  <cv-select
                    :label="$t('settings.smtp_mode')"
                    v-model="smtpMode"
                    :disabled="busy"
                    class="mode"
                  >
                    <cv-select-option value="disabled">{{
                      $t("settings.smtp_mode_disabled")
                    }}</cv-select-option>
                    <cv-select-option
                      value="smarthost"
                      :disabled="!smarthostAvailable"
                      >{{ $t("settings.smtp_mode_smarthost") }}</cv-select-option
                    >
                    <cv-select-option value="custom">{{
                      $t("settings.smtp_mode_custom")
                    }}</cv-select-option>
                  </cv-select>
                  <p class="help">{{ $t("settings.smtp_mode_" + smtpMode + "_help") }}</p>
                  <p v-if="!smarthostAvailable" class="help">
                    {{ $t("settings.no_smarthost") }}
                  </p>
                  <NsButton
                    kind="secondary"
                    :disabled="busy || smtpMode === appliedSmtpMode"
                    :loading="loading.mode"
                    @click="applySmtpMode"
                    class="spaced"
                    >{{ $t("settings.apply_smtp_mode") }}</NsButton
                  >
                </template>
                <SettingField
                  v-for="element in group.elements"
                  :key="element.name"
                  :element="element"
                  :disabled="busy"
                  v-model="values[element.name]"
                />
                <div
                  v-if="group.group === 'smtp' && appliedSmtpMode !== 'disabled'"
                  class="smtp-test"
                >
                  <cv-text-input
                    :label="$t('settings.test_smtp')"
                    v-model.trim="testEmail"
                    :invalid-message="error.testEmail"
                    :disabled="busy"
                    placeholder="name@example.org"
                  />
                  <NsButton
                    kind="tertiary"
                    :disabled="busy || !testEmail"
                    :loading="loading.test"
                    @click="sendTestMail"
                    class="spaced"
                    >{{ $t("settings.send_test_mail") }}</NsButton
                  >
                </div>
              </template>
            </cv-accordion-item>
          </cv-accordion>
          <NsInlineNotification
            v-if="error.save"
            kind="error"
            :title="$t('action.set-panel-settings')"
            :description="error.save"
            :showCloseButton="false"
          />
          <div class="buttons">
            <NsButton
              kind="primary"
              :icon="Save20"
              :loading="loading.save"
              :disabled="busy || !changed"
              @click="save"
              >{{ $t("settings.save") }}</NsButton
            >
            <NsButton
              kind="danger-tertiary"
              :disabled="busy"
              @click="resetOpen = true"
              >{{ $t("settings.reset") }}</NsButton
            >
          </div>
        </cv-tile>
      </cv-column>
    </cv-row>
    <NsModal
      size="default"
      :visible="resetOpen"
      @modal-hidden="resetOpen = false"
      @primary-click="resetSettings"
    >
      <template slot="title">{{ $t("settings.reset") }}</template>
      <template slot="content">
        <p>{{ $t("settings.reset_confirm") }}</p>
      </template>
      <template slot="secondary-button">{{ $t("common.cancel") }}</template>
      <template slot="primary-button">{{ $t("settings.reset") }}</template>
    </NsModal>
  </cv-grid>
</template>

<script>
import Save20 from "@carbon/icons-vue/es/save/20";
import { mapState } from "vuex";
import { TaskService, UtilService } from "@nethserver/ns8-ui-lib";
import panelTask from "../mixins/panelTask";
import SettingField from "../components/SettingField";

export default {
  name: "Settings",
  components: { SettingField },
  mixins: [TaskService, UtilService, panelTask],
  data() {
    return {
      Save20,
      groups: [],
      values: {},
      original: {},
      smtpMode: "custom",
      appliedSmtpMode: "custom",
      smarthostAvailable: false,
      testEmail: "",
      resetOpen: false,
      notice: { kind: "success", title: "", text: "" },
      loading: { load: false, save: false, mode: false, test: false },
      error: { load: "", save: "", testEmail: "" },
    };
  },
  computed: {
    ...mapState(["instanceName", "core"]),
    busy() {
      return (
        this.loading.load ||
        this.loading.save ||
        this.loading.mode ||
        this.loading.test
      );
    },
    changed() {
      return Object.keys(this.values).some(
        (name) => this.values[name] !== this.original[name]
      );
    },
  },
  created() {
    this.load();
  },
  methods: {
    groupTitle(group) {
      const key = "settings.group_" + group.group;
      return this.$te(key) ? this.$t(key) : group.title;
    },
    say(kind, text) {
      this.notice = { kind, title: this.$t("settings.title"), text };
    },
    async load() {
      this.loading.load = true;
      this.error.load = "";
      try {
        const [data, config] = await Promise.all([
          this.runPanelTask("query-panel-data", { section: "settings" }),
          this.runPanelTask("get-configuration"),
        ]);
        this.groups = data.data;
        const values = {};
        data.data.forEach((group) =>
          group.elements.forEach((element) => {
            values[element.name] = element.value;
          })
        );
        this.values = { ...values };
        this.original = { ...values };
        this.smtpMode = config.smtp_mode || "custom";
        this.appliedSmtpMode = this.smtpMode;
        this.smarthostAvailable = config.smarthost_available === true;
      } catch (e) {
        this.error.load = e.message;
      }
      this.loading.load = false;
    },
    async save() {
      this.error.save = "";
      this.loading.save = true;
      const changes = {};
      Object.keys(this.values).forEach((name) => {
        if (this.values[name] !== this.original[name]) {
          changes[name] = this.values[name];
        }
      });
      try {
        await this.runPanelTask("set-panel-settings", { values: changes });
        this.say("success", this.$t("settings.saved"));
        await this.load();
      } catch (e) {
        this.error.save = e.message;
      }
      this.loading.save = false;
    },
    async resetSettings() {
      this.resetOpen = false;
      this.loading.save = true;
      try {
        await this.runPanelTask("reset-panel-settings");
        this.say("success", this.$t("settings.was_reset"));
        await this.load();
      } catch (e) {
        this.error.save = e.message;
      }
      this.loading.save = false;
    },
    async applySmtpMode() {
      this.loading.mode = true;
      try {
        await this.runPanelTask("set-smtp-mode", { mode: this.smtpMode });
        this.say("success", this.$t("settings.smtp_mode_applied"));
        await this.load();
      } catch (e) {
        this.say("error", e.message);
      }
      this.loading.mode = false;
    },
    async sendTestMail() {
      this.error.testEmail = "";
      this.loading.test = true;
      try {
        await this.runPanelTask("test-smtp", { email: this.testEmail });
        this.say("success", this.$t("settings.test_mail_sent"));
      } catch (e) {
        this.error.testEmail = e.message;
      }
      this.loading.test = false;
    },
  },
};
</script>

<style scoped lang="scss">
@import "../styles/carbon-utils";

.intro,
.help {
  margin-bottom: $spacing-05;
  max-width: 38rem;
}

.groups {
  margin-bottom: $spacing-06;
}

.mode {
  max-width: 38rem;
  margin-bottom: $spacing-03;
}

.spaced {
  margin-bottom: $spacing-06;
}

.buttons {
  display: flex;
  gap: $spacing-05;
  margin-top: $spacing-05;
}
</style>

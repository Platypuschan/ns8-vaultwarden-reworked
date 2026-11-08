<!--
  SPDX-License-Identifier: GPL-3.0-or-later
-->
<template>
  <div class="setting-field">
    <cv-toggle
      v-if="element.type === 'checkbox'"
      :value="element.name"
      :label="title"
      v-model="toggle"
      :disabled="disabled"
    >
      <template slot="text-left">{{ $t("settings.disabled") }}</template>
      <template slot="text-right">{{ $t("settings.enabled") }}</template>
    </cv-toggle>
    <cv-text-input
      v-else
      :label="title"
      :type="inputType"
      :placeholder="placeholder"
      :helper-text="element.doc.description"
      :value="text"
      @input="$emit('input', convert($event))"
      :disabled="disabled"
      :password-hide-label="$t('settings.hide')"
      :password-show-label="$t('settings.show')"
    />
  </div>
</template>

<script>
export default {
  name: "SettingField",
  props: {
    element: { type: Object, required: true },
    value: { default: null },
    disabled: { type: Boolean, default: false },
  },
  computed: {
    title() {
      return this.element.doc.name || this.element.name;
    },
    inputType() {
      return this.element.type === "password"
        ? "password"
        : this.element.type === "number"
        ? "number"
        : "text";
    },
    placeholder() {
      const fallback = this.element.default;
      return fallback === null || fallback === "" || fallback === undefined
        ? ""
        : this.$t("settings.default_value", { value: String(fallback) });
    },
    text() {
      return this.value === null || this.value === undefined
        ? ""
        : String(this.value);
    },
    toggle: {
      get() {
        return this.value === true;
      },
      set(value) {
        this.$emit("input", value === true);
      },
    },
  },
  methods: {
    convert(text) {
      if (this.element.type === "number") {
        return text === "" ? null : Number(text);
      }
      return text === "" ? null : text;
    },
  },
};
</script>

<style scoped lang="scss">
@import "../styles/carbon-utils";

.setting-field {
  margin-bottom: $spacing-06;
  max-width: 38rem;
}
</style>

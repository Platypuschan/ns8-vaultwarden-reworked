//
// SPDX-License-Identifier: GPL-3.0-or-later
//
// Runs a module action and resolves with its parsed output. Every page of the
// module uses this instead of repeating the NS8 task event handling.
import to from "await-to-js";

function parseOutput(output) {
  if (typeof output !== "string") {
    return output;
  }
  try {
    return JSON.parse(output);
  } catch (e) {
    return {};
  }
}

export default {
  methods: {
    runPanelTask(action, data = {}) {
      return new Promise((resolve, reject) => {
        const eventId = this.getUuid();
        const root = this.core.$root;
        const events = {
          [`${action}-completed-${eventId}`]: (taskContext, taskResult) =>
            settle(() => resolve(parseOutput(taskResult.output))),
          [`${action}-aborted-${eventId}`]: (taskResult, taskContext) => {
            console.error(`${taskContext.action} aborted`, taskResult);
            settle(() => reject(new Error(this.$t("error.generic_error"))));
          },
          [`${action}-validation-failed-${eventId}`]: (validationErrors) => {
            const first = (validationErrors || [])[0] || {};
            settle(() =>
              reject(new Error(first.message || this.$t("error.generic_error")))
            );
          },
        };
        const settle = (finish) => {
          Object.entries(events).forEach(([name, handler]) =>
            root.$off(name, handler)
          );
          finish();
        };
        Object.entries(events).forEach(([name, handler]) =>
          root.$once(name, handler)
        );
        to(
          this.createModuleTaskForApp(this.instanceName, {
            action,
            data,
            extra: {
              title: this.$t("action." + action),
              isNotificationHidden: true,
              eventId,
            },
          })
        ).then(([err]) => {
          if (err) {
            console.error(`error creating task ${action}`, err);
            settle(() => reject(new Error(this.getErrorMessage(err))));
          }
        });
      });
    },
  },
};

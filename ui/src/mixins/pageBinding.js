//
// SPDX-License-Identifier: GPL-3.0-or-later
//
// Keeps the page in sync with the cluster manager URL (?page=...): without
// it a link to another page changes the address bar but not this frame.
import { QueryParamService } from "@nethserver/ns8-ui-lib";

export default function pageBinding(page) {
  return {
    mixins: [QueryParamService],
    data() {
      return { q: { page }, urlCheckInterval: null };
    },
    beforeRouteEnter(to, from, next) {
      next((vm) => {
        vm.watchQueryData(vm);
        vm.urlCheckInterval = vm.initUrlBindingForApp(vm, vm.q.page);
      });
    },
    beforeRouteLeave(to, from, next) {
      clearInterval(this.urlCheckInterval);
      next();
    },
  };
}

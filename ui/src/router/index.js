//
// SPDX-License-Identifier: GPL-3.0-or-later
//
import Vue from "vue";
import VueRouter from "vue-router";

Vue.use(VueRouter);

const routes = [
  {
    path: "/",
    name: "Settings",
    component: () => import("../views/Settings.vue"),
    alias: ["/status", "/settings"],
  },
  {
    path: "/users",
    name: "Users",
    component: () => import("../views/Users.vue"),
  },
  {
    path: "/organizations",
    name: "Organizations",
    component: () => import("../views/Organizations.vue"),
  },
  {
    path: "/diagnostics",
    name: "Diagnostics",
    component: () => import("../views/Diagnostics.vue"),
  },
  {
    path: "/admin",
    name: "AdvancedAdmin",
    component: () => import("../views/AdvancedAdmin.vue"),
  },
];

const router = new VueRouter({
  base: import.meta.env.BASE_URL,
  routes,
});

export default router;

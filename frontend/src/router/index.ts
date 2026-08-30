import { createRouter, createWebHistory } from "vue-router";
import Session from "../views/Session.vue";
import Settings from "../views/Settings.vue";
import Upload from "../views/Upload.vue";

export const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: "/", component: Upload },
    { path: "/settings", component: Settings },
    { path: "/review/:sessionId", component: Session, props: true },
  ],
});

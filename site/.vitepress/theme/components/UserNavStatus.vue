<script setup lang="ts">
import { watch, onMounted } from "vue";
import { useAuth } from "../composables/useAuth";

const { user, authReady, logOut } = useAuth();

// Toggled on <html> rather than kept local to this component, so plain
// CSS (see custom.css) can hide the static "Get an API key"/"Sign up"
// nav and sidebar links while signed in - those come from
// themeConfig.sidebar/nav in config.ts, which is static build-time
// config with no way to make individual entries conditional on runtime
// auth state.
//
// Registered inside onMounted, not as an immediate watcher: VitePress
// renders every page server-side at build time (Node has no `document`),
// and this component - unlike AuthPanel/Dashboard - isn't wrapped in
// <ClientOnly> in markdown, since it needs to exist on every page via
// the Layout's nav slots, not just the two account pages.
onMounted(() => {
  watch(
    [user, authReady],
    ([u, ready]) => {
      document.documentElement.classList.toggle("md-signed-in", !!(ready && u));
    },
    { immediate: true },
  );
});
</script>

<template>
  <div class="user-nav-status" v-if="authReady && user">
    <a href="/account/dashboard" class="user-email" :title="user.email">
      {{ user.email }}
    </a>
    <button class="signout-btn" @click="logOut">Sign out</button>
  </div>
</template>

<style scoped>
.user-nav-status {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-left: 12px;
  padding-left: 12px;
  border-left: 1px solid var(--matchday-c-card-border);
}

.user-email {
  max-width: 160px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 13px;
  color: var(--vp-c-text-2);
}

.user-email:hover {
  color: var(--vp-c-brand-1);
}

.signout-btn {
  font-size: 13px;
  font-weight: 600;
  color: var(--matchday-c-delete);
  background: transparent;
  border: none;
  cursor: pointer;
  padding: 0;
  white-space: nowrap;
}

/* This component is mounted twice - once in the desktop top nav bar
   (cramped, so a compact inline strip), once in the mobile hamburger
   menu screen (roomy full-width, so it reads more like a menu row than
   a squeezed-in afterthought). VitePress adds .can-go-back-header or
   similar on narrow layouts, but the reliable signal here is simpler:
   the top nav bar itself is hidden below 768px by VitePress's own CSS,
   so this rule only ever applies to the mobile-menu-screen instance. */
@media (max-width: 767px) {
  .user-nav-status {
    margin-left: 0;
    padding: 16px 0 0;
    border-left: none;
    border-top: 1px solid var(--matchday-c-card-border);
    justify-content: space-between;
  }

  .user-email {
    max-width: none;
  }
}
</style>

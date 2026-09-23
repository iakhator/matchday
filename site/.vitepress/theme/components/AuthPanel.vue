<script setup lang="ts">
import { ref, watch } from "vue";
import { useRouter } from "vitepress";
import { useAuth } from "../composables/useAuth";

const { user, authReady, configError, signIn, signUp } = useAuth();
const router = useRouter();

const mode = ref<"signin" | "signup">("signin");
const email = ref("");
const password = ref("");
const error = ref<string | null>(null);
const submitting = ref(false);

// Already signed in (e.g. came back to this page with a live session) -
// no reason to show a login form, just move on.
watch(
  [user, authReady],
  ([u, ready]) => {
    if (ready && u) router.go("/account/dashboard");
  },
  { immediate: true },
);

async function submit() {
  error.value = null;
  submitting.value = true;
  const fn = mode.value === "signin" ? signIn : signUp;
  const result = await fn(email.value, password.value);
  submitting.value = false;
  if (result) {
    error.value = result;
  } else {
    router.go("/account/dashboard");
  }
}
</script>

<template>
  <div class="auth-panel" v-if="configError">
    <p class="error">
      Sign-in isn't configured on this deployment yet
      ({{ configError }}).
    </p>
  </div>
  <div class="auth-panel" v-else-if="authReady && !user">
    <div class="auth-card">
      <div class="tabs">
        <button
          class="tab"
          :class="{ active: mode === 'signin' }"
          @click="mode = 'signin'"
        >
          Sign in
        </button>
        <button
          class="tab"
          :class="{ active: mode === 'signup' }"
          @click="mode = 'signup'"
        >
          Create account
        </button>
      </div>

      <form @submit.prevent="submit">
        <label class="field">
          <span>Email</span>
          <input v-model="email" type="email" required autocomplete="email" />
        </label>
        <label class="field">
          <span>Password</span>
          <input
            v-model="password"
            type="password"
            required
            minlength="6"
            :autocomplete="mode === 'signin' ? 'current-password' : 'new-password'"
          />
        </label>

        <p class="error" v-if="error">{{ error }}</p>

        <button class="submit" type="submit" :disabled="submitting">
          {{
            submitting
              ? "Working..."
              : mode === "signin"
                ? "Sign in"
                : "Create account"
          }}
        </button>
      </form>
    </div>
  </div>
  <div class="auth-panel" v-else-if="!authReady">
    <p class="loading">Loading...</p>
  </div>
</template>

<style scoped>
.auth-panel {
  display: flex;
  justify-content: center;
  padding: 24px 0;
}

.auth-card {
  width: 100%;
  max-width: 360px;
  border-radius: 12px;
  border: 1px solid var(--matchday-c-card-border);
  background: var(--matchday-c-card-bg);
  padding: 20px;
}

.tabs {
  display: flex;
  gap: 4px;
  margin-bottom: 18px;
  border-radius: 8px;
  background: var(--vp-c-bg-alt);
  padding: 4px;
}

.tab {
  flex: 1;
  padding: 8px 10px;
  border-radius: 6px;
  font-size: 14px;
  font-weight: 600;
  color: var(--vp-c-text-2);
  background: transparent;
  border: none;
  cursor: pointer;
}

.tab.active {
  background: var(--vp-c-bg);
  color: var(--vp-c-brand-1);
}

.field {
  display: block;
  margin-bottom: 14px;
  font-size: 13px;
  color: var(--vp-c-text-2);
}

.field span {
  display: block;
  margin-bottom: 6px;
}

.field input {
  width: 100%;
  box-sizing: border-box;
  padding: 8px 10px;
  border-radius: 6px;
  border: 1px solid var(--matchday-c-card-border);
  background: var(--vp-c-bg);
  color: var(--vp-c-text-1);
  font-size: 14px;
}

.field input:focus {
  outline: 2px solid var(--vp-c-brand-1);
  outline-offset: -1px;
}

.error {
  font-size: 13px;
  color: var(--matchday-c-delete);
  margin: 0 0 12px;
}

.submit {
  width: 100%;
  padding: 10px;
  border-radius: 8px;
  border: none;
  background: var(--vp-c-brand-1);
  color: #06281c;
  font-weight: 700;
  font-size: 14px;
  cursor: pointer;
}

.submit:disabled {
  opacity: 0.6;
  cursor: default;
}

.loading {
  color: var(--vp-c-text-3);
}
</style>

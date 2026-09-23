<script setup lang="ts">
import { ref, watch } from "vue";
import { useRouter } from "vitepress";
import { useAuth } from "../composables/useAuth";

const { user, authReady, configError, signIn, signUp, signInWithGoogle } = useAuth();
const router = useRouter();

const mode = ref<"signin" | "signup">("signin");
const email = ref("");
const password = ref("");
const error = ref<string | null>(null);
const submitting = ref(false);
const googleSubmitting = ref(false);

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

async function submitGoogle() {
  error.value = null;
  googleSubmitting.value = true;
  const result = await signInWithGoogle();
  googleSubmitting.value = false;
  // No explicit navigation on success - the watch() above redirects as
  // soon as `user` updates, same as the email/password path ends up doing.
  if (result) error.value = result;
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
      <button
        class="google-btn"
        type="button"
        :disabled="googleSubmitting"
        @click="submitGoogle"
      >
        <svg viewBox="0 0 24 24" width="18" height="18">
          <path
            fill="#4285F4"
            d="M23.52 12.27c0-.85-.08-1.67-.22-2.45H12v4.64h6.47a5.54 5.54 0 0 1-2.4 3.63v3h3.87c2.27-2.09 3.58-5.17 3.58-8.82Z"
          />
          <path
            fill="#34A853"
            d="M12 24c3.24 0 5.95-1.07 7.94-2.91l-3.87-3a7.4 7.4 0 0 1-11-3.9H1.08v3.09A12 12 0 0 0 12 24Z"
          />
          <path
            fill="#FBBC05"
            d="M5.07 14.19a7.2 7.2 0 0 1 0-4.38V6.72H1.08a12 12 0 0 0 0 10.56l3.99-3.09Z"
          />
          <path
            fill="#EA4335"
            d="M12 4.75c1.76 0 3.35.61 4.6 1.8l3.43-3.43C17.94 1.19 15.24 0 12 0A12 12 0 0 0 1.08 6.72l3.99 3.09A7.15 7.15 0 0 1 12 4.75Z"
          />
        </svg>
        {{ googleSubmitting ? "Working..." : "Continue with Google" }}
      </button>

      <div class="divider"><span>or</span></div>

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

.google-btn {
  width: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 10px;
  padding: 9px;
  border-radius: 8px;
  border: 1px solid var(--matchday-c-card-border);
  background: var(--vp-c-bg);
  color: var(--vp-c-text-1);
  font-weight: 600;
  font-size: 14px;
  cursor: pointer;
}

.google-btn:hover {
  background: var(--vp-c-bg-alt);
}

.google-btn:disabled {
  opacity: 0.6;
  cursor: default;
}

.divider {
  display: flex;
  align-items: center;
  text-align: center;
  color: var(--vp-c-text-3);
  font-size: 12px;
  margin: 16px 0;
}

.divider::before,
.divider::after {
  content: "";
  flex: 1;
  border-bottom: 1px solid var(--matchday-c-card-border);
}

.divider span {
  padding: 0 10px;
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

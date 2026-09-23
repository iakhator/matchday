<script setup lang="ts">
import { ref, watch, onMounted } from "vue";
import { useRouter } from "vitepress";
import { useAuth } from "../composables/useAuth";
import {
  listKeys,
  createKey,
  revokeKey,
  type ApiKeySummary,
} from "../gatewayApi";

const { user, authReady, configError, idToken, logOut } = useAuth();
const router = useRouter();

const keys = ref<ApiKeySummary[]>([]);
const loading = ref(true);
const error = ref<string | null>(null);
const newKeyName = ref("");
const creating = ref(false);
// Set exactly once, right after creation - never re-populated from the
// list endpoint, which never returns a secret at all.
const justCreatedSecret = ref<string | null>(null);
const copied = ref(false);

watch(
  [user, authReady],
  ([u, ready]) => {
    if (ready && !u) router.go("/account/signup");
  },
  { immediate: true },
);

async function refresh() {
  const token = await idToken();
  if (!token) return;
  loading.value = true;
  error.value = null;
  try {
    keys.value = await listKeys(token);
  } catch (err) {
    error.value = (err as Error).message;
  } finally {
    loading.value = false;
  }
}

onMounted(() => {
  if (user.value) refresh();
});
watch(user, (u) => {
  if (u) refresh();
});

async function onCreate() {
  const token = await idToken();
  if (!token || !newKeyName.value.trim()) return;
  creating.value = true;
  error.value = null;
  justCreatedSecret.value = null;
  try {
    const created = await createKey(token, newKeyName.value.trim());
    justCreatedSecret.value = created.secret;
    newKeyName.value = "";
    await refresh();
  } catch (err) {
    error.value = (err as Error).message;
  } finally {
    creating.value = false;
  }
}

async function onRevoke(id: string) {
  const token = await idToken();
  if (!token) return;
  error.value = null;
  try {
    await revokeKey(token, id);
    await refresh();
  } catch (err) {
    error.value = (err as Error).message;
  }
}

async function copySecret() {
  if (!justCreatedSecret.value) return;
  await navigator.clipboard.writeText(justCreatedSecret.value);
  copied.value = true;
  setTimeout(() => (copied.value = false), 2000);
}

function fmt(d: string | null) {
  return d ? new Date(d).toLocaleString() : "-";
}
</script>

<template>
  <div class="dashboard" v-if="configError">
    <p class="error">
      Sign-in isn't configured on this deployment yet ({{ configError }}).
    </p>
  </div>
  <div class="dashboard" v-else-if="authReady && user">
    <div class="dash-header">
      <div>
        <div class="dash-email">{{ user.email }}</div>
      </div>
      <button class="link-btn" @click="logOut">Sign out</button>
    </div>

    <div class="new-key-card">
      <form class="new-key-form" @submit.prevent="onCreate">
        <input
          v-model="newKeyName"
          type="text"
          placeholder="Key name, e.g. my-app"
          required
          maxlength="100"
        />
        <button type="submit" :disabled="creating">
          {{ creating ? "Generating..." : "New key" }}
        </button>
      </form>

      <div class="secret-reveal" v-if="justCreatedSecret">
        <p class="secret-warning">
          Copy this now - it won't be shown again.
        </p>
        <div class="secret-row">
          <code>{{ justCreatedSecret }}</code>
          <button class="link-btn" @click="copySecret">
            {{ copied ? "Copied" : "Copy" }}
          </button>
        </div>
      </div>
    </div>

    <p class="error" v-if="error">{{ error }}</p>

    <p class="loading" v-if="loading">Loading your keys...</p>

    <div class="key-list" v-else-if="keys.length">
      <div class="key-row" v-for="k in keys" :key="k.id">
        <div class="key-info">
          <div class="key-name">
            {{ k.name }}
            <span class="key-revoked" v-if="k.revoked_at">revoked</span>
          </div>
          <div class="key-meta">
            <code>{{ k.key_prefix }}...</code>
            · {{ k.requests_per_minute }} req/min
            · last used {{ fmt(k.last_used_at) }}
          </div>
        </div>
        <button
          class="link-btn danger"
          v-if="!k.revoked_at"
          @click="onRevoke(k.id)"
        >
          Revoke
        </button>
      </div>
    </div>

    <p class="empty" v-else>No keys yet - generate one above.</p>
  </div>
  <div class="dashboard" v-else>
    <p class="loading">Loading...</p>
  </div>
</template>

<style scoped>
.dashboard {
  max-width: 640px;
  margin: 0 auto;
  padding: 24px 0;
}

.dash-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
}

.dash-email {
  font-size: 14px;
  color: var(--vp-c-text-2);
}

.new-key-card {
  border-radius: 12px;
  border: 1px solid var(--matchday-c-card-border);
  background: var(--matchday-c-card-bg);
  padding: 16px;
  margin-bottom: 20px;
}

.new-key-form {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.new-key-form input {
  flex: 1;
  min-width: 160px;
  box-sizing: border-box;
  padding: 9px 12px;
  border-radius: 6px;
  border: 1px solid var(--matchday-c-card-border);
  background: var(--vp-c-bg);
  color: var(--vp-c-text-1);
  font-size: 14px;
}

.new-key-form button {
  padding: 9px 16px;
  border-radius: 6px;
  border: none;
  background: var(--vp-c-brand-1);
  color: #06281c;
  font-weight: 700;
  font-size: 14px;
  cursor: pointer;
  white-space: nowrap;
}

.new-key-form button:disabled {
  opacity: 0.6;
  cursor: default;
}

.secret-reveal {
  margin-top: 14px;
  padding-top: 14px;
  border-top: 1px solid var(--matchday-c-card-border);
}

.secret-warning {
  font-size: 13px;
  font-weight: 600;
  color: var(--matchday-c-tertiary);
  margin: 0 0 8px;
}

.secret-row {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
  background: var(--vp-c-bg);
  border-radius: 6px;
  padding: 8px 10px;
}

.secret-row code {
  flex: 1;
  min-width: 0;
  overflow-wrap: break-word;
  word-break: break-all;
  font-size: 13px;
  background: transparent;
  padding: 0;
}

.key-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.key-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
  padding: 12px 14px;
  border-radius: 8px;
  border: 1px solid var(--matchday-c-card-border);
  background: var(--matchday-c-card-bg);
}

.key-name {
  font-weight: 600;
  font-size: 14px;
}

.key-revoked {
  margin-left: 8px;
  font-size: 11px;
  font-weight: 600;
  text-transform: uppercase;
  color: var(--matchday-c-delete);
}

.key-meta {
  font-size: 12px;
  color: var(--vp-c-text-3);
  margin-top: 2px;
}

.key-meta code {
  background: transparent;
  padding: 0;
  font-size: 12px;
}

.link-btn {
  border: none;
  background: transparent;
  color: var(--vp-c-brand-1);
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  padding: 4px 8px;
  flex-shrink: 0;
}

.link-btn.danger {
  color: var(--matchday-c-delete);
}

.error {
  font-size: 13px;
  color: var(--matchday-c-delete);
}

.loading,
.empty {
  color: var(--vp-c-text-3);
  font-size: 14px;
}
</style>

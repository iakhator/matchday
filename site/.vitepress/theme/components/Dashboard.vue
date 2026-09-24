<script setup lang="ts">
import { ref, computed, watch, onMounted } from "vue";
import { useRouter } from "vitepress";
import { useAuth } from "../composables/useAuth";
import {
  listKeys,
  createKey,
  revokeKey,
  rotateKey,
  type ApiKeySummary,
} from "../gatewayApi";

const { user, authReady, configError, idToken } = useAuth();
const router = useRouter();

const keys = ref<ApiKeySummary[]>([]);
const loading = ref(true);
const error = ref<string | null>(null);
const newKeyName = ref("");
const creating = ref(false);
const rotatingId = ref<string | null>(null);
// Set exactly once, right after creation or rotation - never
// re-populated from the list endpoint, which never returns a secret at
// all.
const justCreatedSecret = ref<string | null>(null);
const copied = ref(false);

// Drives which create UI shows: a one-click "generate your first key"
// button with no typing (liveKeyCount === 0), or the named form for
// adding another once at least one already exists. Both still require an
// explicit click either way - see the commit message for why this isn't
// auto-created on page load instead (a page render having a side effect
// is the wrong shape, even for a "default" key).
//
// Every key the API returns is live - a revoked key's row is deleted, not
// flagged (see ApiKeyRecord's docstring) - so this is just the count.
const liveKeyCount = computed(() => keys.value.length);

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

async function onCreate(name: string) {
  const token = await idToken();
  if (!token || !name.trim()) return;
  creating.value = true;
  error.value = null;
  justCreatedSecret.value = null;
  try {
    const created = await createKey(token, name.trim());
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

async function onRotate(id: string) {
  const token = await idToken();
  if (!token) return;
  rotatingId.value = id;
  error.value = null;
  justCreatedSecret.value = null;
  try {
    const rotated = await rotateKey(token, id);
    justCreatedSecret.value = rotated.secret;
    await refresh();
  } catch (err) {
    error.value = (err as Error).message;
  } finally {
    rotatingId.value = null;
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
    <div class="new-key-card">
      <button
        v-if="!loading && liveKeyCount === 0"
        class="first-key-btn"
        type="button"
        :disabled="creating"
        @click="onCreate('default')"
      >
        {{ creating ? "Generating..." : "Generate your first key" }}
      </button>

      <form v-else class="new-key-form" @submit.prevent="onCreate(newKeyName)">
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
          <div class="key-name">{{ k.name }}</div>
          <div class="key-meta">
            <code>{{ k.key_prefix }}...</code>
            · {{ k.requests_per_minute }} req/min
            · last used {{ fmt(k.last_used_at) }}
          </div>
        </div>
        <div class="key-actions">
          <button
            class="link-btn"
            :disabled="rotatingId === k.id"
            @click="onRotate(k.id)"
          >
            {{ rotatingId === k.id ? "Rotating..." : "Rotate" }}
          </button>
          <button class="link-btn danger" @click="onRevoke(k.id)">Revoke</button>
        </div>
      </div>
    </div>
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

.new-key-card {
  border-radius: 12px;
  border: 1px solid var(--matchday-c-card-border);
  background: var(--matchday-c-card-bg);
  padding: 16px;
  margin-top: 20px;
  margin-bottom: 20px;
}

.first-key-btn {
  width: 100%;
  padding: 12px;
  border-radius: 8px;
  border: none;
  background: var(--vp-c-brand-1);
  color: #06281c;
  font-weight: 700;
  font-size: 15px;
  cursor: pointer;
}

.first-key-btn:disabled {
  opacity: 0.6;
  cursor: default;
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

.key-actions {
  display: flex;
  align-items: center;
  gap: 4px;
  flex-shrink: 0;
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

.link-btn:disabled {
  opacity: 0.6;
  cursor: default;
}

.link-btn.danger {
  color: var(--matchday-c-delete);
}

.error {
  font-size: 13px;
  color: var(--matchday-c-delete);
}

.loading {
  color: var(--vp-c-text-3);
  font-size: 14px;
}
</style>

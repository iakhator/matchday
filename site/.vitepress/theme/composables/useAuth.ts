import { ref, onMounted, onUnmounted, type Ref } from "vue";
import {
  onAuthStateChanged,
  signInWithEmailAndPassword,
  createUserWithEmailAndPassword,
  signOut,
  type User,
} from "firebase/auth";
import { getFirebaseAuth } from "../firebase";

// One module-level state, not one per component instance - the signup
// page and the dashboard page are separate route loads, but both need to
// agree on "is anyone signed in right now" without racing each other's
// onAuthStateChanged listener.
const user: Ref<User | null> = ref(null);
const authReady = ref(false);
const configError: Ref<string | null> = ref(null);
let listenerCount = 0;
let unsubscribe: (() => void) | null = null;

function friendlyError(err: unknown): string {
  const code = (err as { code?: string })?.code ?? "";
  switch (code) {
    case "auth/invalid-credential":
    case "auth/wrong-password":
      return "Incorrect email or password.";
    case "auth/user-not-found":
      return "No account with that email - sign up instead?";
    case "auth/email-already-in-use":
      return "An account with that email already exists - sign in instead?";
    case "auth/weak-password":
      return "Password must be at least 6 characters.";
    case "auth/invalid-email":
      return "That doesn't look like a valid email address.";
    default:
      return (err as Error)?.message || "Something went wrong. Try again.";
  }
}

export function useAuth() {
  onMounted(() => {
    listenerCount++;
    if (!unsubscribe && !configError.value) {
      try {
        unsubscribe = onAuthStateChanged(getFirebaseAuth(), (u) => {
          user.value = u;
          authReady.value = true;
        });
      } catch (err) {
        // Most likely: VITE_FIREBASE_* was never set (see firebase.ts) -
        // the common state for anyone who hasn't configured a Firebase
        // project yet. Surface it instead of leaving the panel stuck on
        // "Loading..." forever with the real reason only in the console.
        configError.value = (err as Error).message;
        authReady.value = true;
      }
    }
  });

  onUnmounted(() => {
    listenerCount--;
    if (listenerCount <= 0 && unsubscribe) {
      unsubscribe();
      unsubscribe = null;
    }
  });

  async function signIn(email: string, password: string): Promise<string | null> {
    try {
      await signInWithEmailAndPassword(getFirebaseAuth(), email, password);
      return null;
    } catch (err) {
      return friendlyError(err);
    }
  }

  async function signUp(email: string, password: string): Promise<string | null> {
    try {
      await createUserWithEmailAndPassword(getFirebaseAuth(), email, password);
      return null;
    } catch (err) {
      return friendlyError(err);
    }
  }

  async function logOut(): Promise<void> {
    await signOut(getFirebaseAuth());
  }

  // Every authenticated call to the gateway's /account/keys endpoints
  // needs a fresh-enough token - Firebase handles the actual refresh
  // internally, this just surfaces the current one.
  async function idToken(): Promise<string | null> {
    return (await user.value?.getIdToken()) ?? null;
  }

  return { user, authReady, configError, signIn, signUp, logOut, idToken };
}

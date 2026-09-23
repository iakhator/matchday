// Client-side Firebase init for the signup/dashboard pages only - the
// rest of the site is static and never touches this. These are the
// *public* web config values (safe to ship client-side by design;
// Firebase's actual security boundary is server-side token verification,
// not secrecy of this config) - see app/core/firebase.py in the backend
// for the service-account side of this same integration.
import { initializeApp, type FirebaseApp } from "firebase/app";
import {
  getAuth,
  browserLocalPersistence,
  setPersistence,
  type Auth,
} from "firebase/auth";

let app: FirebaseApp | undefined;
let auth: Auth | undefined;

// Local (not in-memory) persistence: a docs-site visitor navigating
// between the signup and dashboard pages, or closing the tab and coming
// back, shouldn't have to sign in again every time the way a security-
// sensitive app might deliberately want.
export function getFirebaseAuth(): Auth {
  if (auth) return auth;

  const config = {
    apiKey: import.meta.env.VITE_FIREBASE_API_KEY,
    authDomain: import.meta.env.VITE_FIREBASE_AUTH_DOMAIN,
    projectId: import.meta.env.VITE_FIREBASE_PROJECT_ID,
    appId: import.meta.env.VITE_FIREBASE_APP_ID,
  };

  if (!config.apiKey) {
    throw new Error(
      "Firebase isn't configured for this build - set VITE_FIREBASE_* in " +
        "site/.env. See site/.env.example.",
    );
  }

  app = initializeApp(config);
  auth = getAuth(app);
  setPersistence(auth, browserLocalPersistence);
  return auth;
}

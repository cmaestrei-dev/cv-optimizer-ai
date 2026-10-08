// Sesión. Si la API entrega una llave de Clerk (/api/config): Clerk (Google y correo). Si no: entrada
// de desarrollo (POST /dev/token, solo existe en local). El resto de la app solo ve esta interfaz.
import { esMX } from "@clerk/localizations";
import { ClerkProvider, useAuth as useClerkAuth, useClerk, useUser } from "@clerk/react";
import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from "react";

import { ApiError, configureAuth, post } from "../api/client";

type Auth = {
  mode: "clerk" | "dev";
  status: "loading" | "signed-in" | "signed-out";
  /** Identifica la sesión (para no mezclar datos en caché entre cuentas). */
  sessionKey: string | null;
  name: string | null;
  signIn: (name: string) => Promise<void>; // solo en modo desarrollo
  signOut: () => void;
};

const AuthContext = createContext<Auth | null>(null);

export function useAuth(): Auth {
  const auth = useContext(AuthContext);
  if (!auth) throw new Error("useAuth fuera de AuthProvider");
  return auth;
}

// ── Clerk ──────────────────────────────────────────────────────────────

function ClerkBridge({ children }: { children: ReactNode }) {
  const { isLoaded, isSignedIn, userId, getToken } = useClerkAuth();
  const { user } = useUser();
  const clerk = useClerk();
  const signOut = useCallback(() => void clerk.signOut(), [clerk]);
  // Clerk renueva el token (dura unos segundos) y lo entrega en cada petición.
  configureAuth(() => getToken(), signOut);
  const value = useMemo<Auth>(() => ({
    mode: "clerk",
    status: !isLoaded ? "loading" : isSignedIn ? "signed-in" : "signed-out",
    sessionKey: userId ?? null,
    name: user?.firstName ?? user?.fullName ?? null,
    signIn: async () => {},
    signOut,
  }), [isLoaded, isSignedIn, userId, user, signOut]);
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

/** Colores de "El Taller Nocturno" (DESIGN.md) para las pantallas de Clerk. */
const clerkAppearance = {
  variables: {
    colorPrimary: "#58a6ff",
    colorBackground: "#161b22",
    colorInputBackground: "#0d1117",
    colorText: "#c9d1d9",
    colorInputText: "#c9d1d9",
    colorTextSecondary: "rgba(201, 209, 217, 0.72)",
    fontFamily: "'Plus Jakarta Sans', system-ui, sans-serif",
    borderRadius: "8px",
  },
};

// ── desarrollo ─────────────────────────────────────────────────────────

const KEY = "cvo.session";
type DevSession = { token: string; name: string; expiresAt: number };

function loadDev(): DevSession | null {
  try {
    const raw = sessionStorage.getItem(KEY);
    const session = raw ? (JSON.parse(raw) as DevSession) : null;
    return session && session.expiresAt > Date.now() ? session : null;
  } catch {
    return null;
  }
}

function DevAuthProvider({ children }: { children: ReactNode }) {
  const [session, setSession] = useState<DevSession | null>(loadDev);

  const signOut = useCallback(() => {
    try {
      sessionStorage.removeItem(KEY);
    } catch {
      // almacenamiento no disponible: basta con olvidar la sesión en memoria
    }
    setSession(null);
  }, []);

  configureAuth(() => session?.token ?? null, signOut);

  const signIn = useCallback(async (name: string) => {
    try {
      const out = await post<{ token: string; expires_in: number }>("/dev/token", { name });
      const next = { token: out.token, name, expiresAt: Date.now() + out.expires_in * 1000 };
      try {
        sessionStorage.setItem(KEY, JSON.stringify(next));
      } catch {
        // sin almacenamiento la sesión dura lo que dure la pestaña
      }
      setSession(next);
    } catch (e) {
      if (e instanceof ApiError && e.status === 404) {
        throw new ApiError(404, "El inicio de sesión de esta versión todavía no está activo en este servidor.");
      }
      throw e;
    }
  }, []);

  const value = useMemo<Auth>(() => ({
    mode: "dev",
    status: session ? "signed-in" : "signed-out",
    sessionKey: session?.token ?? null,
    name: session?.name ?? null,
    signIn,
    signOut,
  }), [session, signIn, signOut]);
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function AuthProvider({ clerkKey, children }: { clerkKey: string; children: ReactNode }) {
  if (!clerkKey) return <DevAuthProvider>{children}</DevAuthProvider>;
  return (
    <ClerkProvider publishableKey={clerkKey} localization={esMX} appearance={clerkAppearance} afterSignOutUrl="/">
      <ClerkBridge>{children}</ClerkBridge>
    </ClerkProvider>
  );
}

// Sesión. Hoy: entrada de desarrollo (POST /dev/token, solo en local). En la fase 5d este módulo se
// conecta al proveedor de identidad (Google y correo) sin cambiar el resto de la app.
import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from "react";

import { ApiError, configureAuth, post } from "../api/client";

const KEY = "cvo.session";

type Session = { token: string; name: string; expiresAt: number };
type Auth = {
  session: Session | null;
  signIn: (name: string) => Promise<void>;
  signOut: () => void;
};

function load(): Session | null {
  try {
    const raw = sessionStorage.getItem(KEY);
    const session = raw ? (JSON.parse(raw) as Session) : null;
    return session && session.expiresAt > Date.now() ? session : null;
  } catch {
    return null;
  }
}

const AuthContext = createContext<Auth | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  // Cada sesión tiene su propia caché de datos (main.tsx crea un QueryClient por token).
  const [session, setSession] = useState<Session | null>(load);

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

  const value = useMemo(() => ({ session, signIn, signOut }), [session, signIn, signOut]);
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): Auth {
  const auth = useContext(AuthContext);
  if (!auth) throw new Error("useAuth fuera de AuthProvider");
  return auth;
}

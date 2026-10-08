import { MutationCache, QueryClient, QueryClientProvider, useQuery } from "@tanstack/react-query";
import { StrictMode, useMemo } from "react";
import { createRoot } from "react-dom/client";
import { createBrowserRouter, Navigate, Outlet, RouterProvider } from "react-router";

import { ApiError, get, type S } from "./api/client";
import { AuthProvider, useAuth } from "./auth/auth";
import { Layout } from "./components/Layout";
import { Spinner } from "./components/ui";
import { ApplicationDetail } from "./pages/ApplicationDetail";
import { Applications } from "./pages/Applications";
import { Inbox } from "./pages/Inbox";
import { Login } from "./pages/Login";
import { Market } from "./pages/Market";
import { Profile } from "./pages/Profile";
import "./styles.css";

function makeQueryClient(): QueryClient {
  const client: QueryClient = new QueryClient({
    // Casi toda acción puede usar la IA: el contador del encabezado se refresca al terminar cada una.
    mutationCache: new MutationCache({ onSettled: () => client.invalidateQueries({ queryKey: ["usage"] }) }),
    defaultOptions: {
      queries: {
        // Los errores de la persona (4xx) no se reintentan; los del servidor, una vez.
        retry: (count, error) => !(error instanceof ApiError && error.status < 500) && count < 1,
        refetchOnWindowFocus: false,
      },
    },
  });
  return client;
}

/** Una caché por sesión: lo que llegue tarde de la cuenta anterior no se ve en la nueva. */
function SessionData() {
  const { sessionKey } = useAuth();
  const client = useMemo(() => makeQueryClient(), [sessionKey]); // nueva caché al cambiar de sesión
  return (
    <QueryClientProvider client={client}>
      <RouterProvider router={router} />
    </QueryClientProvider>
  );
}

function RequireSession() {
  const { status } = useAuth();
  if (status === "loading") return <main className="main"><Spinner /></main>;
  return status === "signed-in" ? <Outlet /> : <Login />;
}

function Home() {
  const me = useQuery({ queryKey: ["me"], queryFn: () => get<S["MeOut"]>("/me") });
  if (me.isPending) return <Spinner />;
  return <Navigate to={me.data?.has_experience ? "/bandeja" : "/perfil"} replace />;
}

const router = createBrowserRouter([
  {
    element: <RequireSession />,
    children: [
      {
        element: <Layout />,
        children: [
          { index: true, element: <Home /> },
          { path: "bandeja", element: <Inbox /> },
          { path: "postulaciones", element: <Applications /> },
          { path: "postulaciones/:id", element: <ApplicationDetail /> },
          { path: "perfil", element: <Profile /> },
          { path: "mercado", element: <Market /> },
          { path: "*", element: <Navigate to="/" replace /> },
        ],
      },
    ],
  },
]);

function Unavailable() {
  return (
    <main className="main" style={{ maxWidth: 440, paddingTop: "12vh" }}>
      <h1>CV Optimizer</h1>
      <div className="notice warn">
        <p>No pudimos conectar con el servidor. Puede estar despertando: espera unos segundos.</p>
        <button className="primary" onClick={() => window.location.reload()}>Reintentar</button>
      </div>
    </main>
  );
}

async function start() {
  const root = createRoot(document.getElementById("root")!);
  // La llave pública de Clerk viene de la API: la misma compilación sirve en cualquier entorno.
  let clerkKey: string;
  try {
    clerkKey = (await get<{ clerk_publishable_key: string }>("/config")).clerk_publishable_key;
  } catch {
    // Sin la configuración no se sabe qué entrada mostrar: nunca caer en la de desarrollo por error.
    root.render(<Unavailable />);
    return;
  }
  root.render(
    <StrictMode>
      <AuthProvider clerkKey={clerkKey}>
        <SessionData />
      </AuthProvider>
    </StrictMode>,
  );
}

void start();

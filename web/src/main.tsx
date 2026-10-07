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
  const { session } = useAuth();
  const token = session?.token;
  const client = useMemo(() => makeQueryClient(), [token]); // nueva caché al cambiar de sesión
  return (
    <QueryClientProvider client={client}>
      <RouterProvider router={router} />
    </QueryClientProvider>
  );
}

function RequireSession() {
  const { session } = useAuth();
  return session ? <Outlet /> : <Login />;
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

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <AuthProvider>
      <SessionData />
    </AuthProvider>
  </StrictMode>,
);

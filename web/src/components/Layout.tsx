import { useQuery } from "@tanstack/react-query";
import { NavLink, Outlet } from "react-router";

import { get, type S } from "../api/client";
import { useAuth } from "../auth/auth";
import { BriefcaseIcon, ChartIcon, InboxIcon, UserIcon } from "./icons";

const LINKS = [
  { to: "/bandeja", label: "Bandeja", Icon: InboxIcon },
  { to: "/postulaciones", label: "Postulaciones", Icon: BriefcaseIcon },
  { to: "/perfil", label: "Perfil", Icon: UserIcon },
  { to: "/mercado", label: "Mercado", Icon: ChartIcon },
];

export function Layout() {
  const { signOut } = useAuth();
  const usage = useQuery({ queryKey: ["usage"], queryFn: () => get<S["UsageOut"]>("/usage"), staleTime: 30_000 });
  return (
    <div className="shell">
      <header className="topbar">
        <NavLink to="/bandeja" className="brand">CV <span>Optimizer</span></NavLink>
        <div className="row">
          {usage.data && (
            <small className="faint" title="Llamadas a la IA hoy (el cupo se reinicia a medianoche, hora de Colombia)">
              IA hoy {usage.data.used_today}/{usage.data.daily_limit}
            </small>
          )}
          <button type="button" className="small" onClick={signOut}>Salir</button>
        </div>
      </header>
      <nav className="nav" aria-label="Secciones">
        {LINKS.map(({ to, label, Icon }) => (
          <NavLink key={to} to={to}><Icon />{label}</NavLink>
        ))}
      </nav>
      <main className="main"><Outlet /></main>
    </div>
  );
}

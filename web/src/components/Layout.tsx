import { useQuery } from "@tanstack/react-query";
import { NavLink, Outlet } from "react-router";

import { get, type S } from "../api/client";
import { useAuth } from "../auth/auth";
import { BriefcaseIcon, ChartIcon, InboxIcon, UserIcon } from "./icons";
import { Bar } from "./ui";

const LINKS = [
  { to: "/bandeja", label: "Bandeja", Icon: InboxIcon },
  { to: "/postulaciones", label: "Postulaciones", Icon: BriefcaseIcon },
  { to: "/perfil", label: "Perfil", Icon: UserIcon },
  { to: "/mercado", label: "Mercado", Icon: ChartIcon },
];

export function Brand({ to = "/bandeja" }: { to?: string }) {
  return (
    <NavLink to={to} className="brand" aria-label="CV Optimizer, inicio">
      <span className="brand-mark" aria-hidden="true">CV</span>Optimizer
    </NavLink>
  );
}

export function Layout() {
  const { signOut } = useAuth();
  const usage = useQuery({ queryKey: ["usage"], queryFn: () => get<S["UsageOut"]>("/usage"), staleTime: 30_000 });
  return (
    <div className="shell">
      <header className="band">
        <Brand />
        <nav className="nav" aria-label="Secciones">
          {LINKS.map(({ to, label, Icon }) => (
            <NavLink key={to} to={to}><Icon />{label}</NavLink>
          ))}
        </nav>
        <div className="band-tools">
          {usage.data && (
            <span className="quota" title="Llamadas a la IA hoy (el cupo se reinicia a medianoche, hora de Colombia)">
              IA {usage.data.used_today}/{usage.data.daily_limit}
              <Bar value={usage.data.used_today} max={usage.data.daily_limit} />
            </span>
          )}
          <button type="button" className="small" onClick={signOut}>Salir</button>
        </div>
      </header>
      <main className="main"><Outlet /></main>
    </div>
  );
}

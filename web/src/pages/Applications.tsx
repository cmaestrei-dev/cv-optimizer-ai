import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router";

import { get, post, type S } from "../api/client";
import { EmptyState, ErrorNotice, Spinner } from "../components/ui";
import { date, PLATFORMS } from "../lib/format";

const VIEWS = [
  { key: "activas", label: "Activas" },
  { key: "cerradas", label: "Cerradas" },
  { key: "todas", label: "Todas" },
] as const;

function NewApplication({ onDone }: { onDone: () => void }) {
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const [form, setForm] = useState({ role: "", company: "", platform: PLATFORMS[0]!, url: "" });
  const create = useMutation({
    mutationFn: () => post<S["ApplicationOut"]>("/applications", { ...form, status: "postulada" }),
    onSuccess: (app) => { queryClient.invalidateQueries({ queryKey: ["applications"] }); onDone(); navigate(`/postulaciones/${app.id}`); },
  });
  const submit = (e: FormEvent) => { e.preventDefault(); create.mutate(); };
  return (
    <form className="card stack" onSubmit={submit}>
      <h3>Registrar una postulación hecha por fuera</h3>
      <div className="grid-2">
        <label>Cargo<input type="text" required value={form.role} onChange={(e) => setForm({ ...form, role: e.target.value })} /></label>
        <label>Empresa<input type="text" value={form.company} onChange={(e) => setForm({ ...form, company: e.target.value })} /></label>
        <label>Portal<select value={form.platform} onChange={(e) => setForm({ ...form, platform: e.target.value })}>{PLATFORMS.map((p) => <option key={p}>{p}</option>)}</select></label>
        <label>Enlace (opcional)<input type="text" inputMode="url" value={form.url} onChange={(e) => setForm({ ...form, url: e.target.value })} /></label>
      </div>
      <ErrorNotice error={create.error} />
      <div className="row"><button className="primary small" disabled={create.isPending}>Registrar</button><button type="button" className="small" onClick={onDone}>Cancelar</button></div>
    </form>
  );
}

export function Applications() {
  const [view, setView] = useState<(typeof VIEWS)[number]["key"]>("activas");
  const [adding, setAdding] = useState(false);
  const summary = useQuery({ queryKey: ["applications", "summary"], queryFn: () => get<S["SummaryOut"]>("/applications/summary") });
  const list = useQuery({ queryKey: ["applications", view], queryFn: () => get<S["ApplicationSummaryOut"][]>(`/applications?view=${view}`) });
  const s = summary.data;
  return (
    <>
      <div className="page-head">
        <h1>Mis postulaciones</h1>
        <p>Cada vacante a la que aplicas, con el CV exacto que enviaste, su estado y lo que pasó después.</p>
      </div>
      {s && (
        <div className="metrics">
          <div className="metric"><b>{s.total}</b><span>Postulaciones</span></div>
          <div className="metric"><b>{s.sent}</b><span>Enviadas</span></div>
          <div className="metric"><b>{(s.by_status.en_revision ?? 0) + (s.by_status.entrevista ?? 0)}</b><span>En proceso</span></div>
          <div className="metric"><b>{s.by_status.oferta ?? 0}</b><span>Ofertas</span></div>
          <div className="metric"><b>{s.response_rate === null ? "—" : `${Math.round(s.response_rate * 100)}%`}</b><span>Respuesta</span></div>
        </div>
      )}
      {s && s.due.length > 0 && (
        <div className="notice warn">
          <p><b>Para hacer hoy</b></p>
          <ul>{s.due.map((a) => <li key={a.id}><Link to={`/postulaciones/${a.id}`}>{a.role}{a.company && ` — ${a.company}`}</Link>: {a.next_action || "hacer seguimiento"}</li>)}</ul>
        </div>
      )}
      <div className="tabs" role="tablist">
        {VIEWS.map((v) => <button key={v.key} role="tab" aria-selected={view === v.key} onClick={() => setView(v.key)}>{v.label}</button>)}
      </div>
      {!adding && (
        <div style={{ marginBottom: 16 }}>
          <button className="small" onClick={() => setAdding(true)}>Registrar una postulación hecha por fuera</button>
        </div>
      )}
      {adding && <NewApplication onDone={() => setAdding(false)} />}
      {list.isPending && <Spinner />}
      <ErrorNotice error={list.error ?? summary.error} />
      {list.data?.length === 0 && <EmptyState title="Nada aquí todavía">Prepara una vacante desde la <Link to="/bandeja">Bandeja</Link>.</EmptyState>}
      {list.data?.map((a) => (
        <Link key={a.id} to={`/postulaciones/${a.id}`} className="list-item">
          <div className="row spread">
            <h3>{a.role}</h3>
            <span className="status">{a.status_label}</span>
          </div>
          <small>{[a.company, a.platform, a.applied_on ? `enviada el ${date(a.applied_on)}` : `guardada el ${date(a.created_at)}`, a.match_score !== null && `${a.match_score}/100`].filter(Boolean).join(" · ")}</small>
          {a.next_action_on && <small className="faint">Recordatorio {date(a.next_action_on)}: {a.next_action || "seguimiento"}</small>}
        </Link>
      ))}
    </>
  );
}

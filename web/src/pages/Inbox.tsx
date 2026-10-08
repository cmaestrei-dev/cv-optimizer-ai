import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useNavigate } from "react-router";

import { get, post, safeHref, type S } from "../api/client";
import { AlertsCard } from "../components/inbox/AlertsCard";
import { EmptyState, ErrorNotice, Notice, ScoreBar, Spinner } from "../components/ui";
import { freshness } from "../lib/format";
import { useJob } from "../lib/useJob";

type TriageItem = { url: string; status: string; message: string; score: number | null };

function SearchPortals() {
  const [city, setCity] = useState("");
  const [title, setTitle] = useState("");
  const titles = useMutation({ mutationFn: () => get<S["TitlesOut"]>("/discovery/titles") });
  const links = useQuery({
    queryKey: ["links", title, city],
    queryFn: () => get<S["SearchLinkOut"][]>(`/discovery/links?title=${encodeURIComponent(title)}&city=${encodeURIComponent(city)}`),
    enabled: title.trim().length > 1,
    staleTime: Infinity,
  });
  return (
    <details className="card">
      <summary><b>1. Buscar vacantes en los portales</b></summary>
      <div className="stack" style={{ marginTop: 12 }}>
        <p className="muted">Elige un cargo y abre la búsqueda en cada portal. Copia el enlace de cada vacante que te interese y pégalo abajo.</p>
        <div className="grid-2">
          <label>Cargo<input type="text" value={title} onChange={(e) => setTitle(e.target.value)} placeholder="Ej.: Auxiliar administrativa" /></label>
          <label>Ciudad (opcional)<input type="text" value={city} onChange={(e) => setCity(e.target.value)} placeholder="Ej.: Bogotá" /></label>
        </div>
        <div className="row">
          <button className="small" onClick={() => titles.mutate()} disabled={titles.isPending}>
            {titles.isPending ? "Buscando cargos…" : "Sugerir cargos afines a mi perfil"}
          </button>
          {titles.data?.titles.map((t) => (
            <button key={t} className={`small ${t === title ? "primary" : ""}`} onClick={() => setTitle(t)}>{t}</button>
          ))}
        </div>
        <ErrorNotice error={titles.error} />
        {links.data && (
          <div className="row">
            {links.data.map((l) => (
              <a key={l.portal} className="btn small" href={safeHref(l.url)} target="_blank" rel="noopener noreferrer">{l.portal} ↗</a>
            ))}
          </div>
        )}
      </div>
    </details>
  );
}

function AddLinks() {
  const queryClient = useQueryClient();
  const [links, setLinks] = useState("");
  const [skipped, setSkipped] = useState(0);
  const batch = useJob();
  const result = batch.job?.result as { done?: number; total?: number; results?: TriageItem[] } | null | undefined;

  async function submit() {
    const done = await batch.run(async () => {
      const out = await post<S["InboxOut"]>("/inbox", { links });
      setSkipped(out.skipped);
      return out.job;
    });
    if (done) setLinks("");
    queryClient.invalidateQueries({ queryKey: ["applications"] });
    queryClient.invalidateQueries({ queryKey: ["usage"] });
  }

  return (
    <section className="card stack">
      <h2>2. Pega los enlaces que te interesaron</h2>
      <label>
        Enlaces (hasta 10 a la vez, uno por línea)
        <textarea rows={4} value={links} onChange={(e) => setLinks(e.target.value)} disabled={batch.running}
          placeholder={"https://co.computrabajo.com/ofertas-de-trabajo/…\nhttps://www.linkedin.com/jobs/view/…"} />
      </label>
      <div><button className="primary" onClick={submit} disabled={batch.running || !links.trim()}>Traer y analizar</button></div>
      {batch.running && (
        <Spinner label={result?.total ? `Analizando ${result.done ?? 0} de ${result.total}` : "Leyendo las vacantes"} />
      )}
      <ErrorNotice error={batch.error} />
      {skipped > 0 && <Notice kind="warn"><p>Se procesan 10 por carga: pega los otros {skipped} en una nueva.</p></Notice>}
      {result?.results && !batch.running && (
        <div className="stack" style={{ gap: 4 }}>
          {result.results.map((r) => (
            <small key={r.url}>
              <span className={`lvl ${r.status === "agregada" ? "cubre" : r.status === "repetida" ? "parcial" : "no"}`}>
                {r.status === "agregada" ? "✓" : r.status === "repetida" ? "↺" : "✗"}
              </span>{" "}
              {r.message}{r.score !== null && ` · ${r.score}/100`}
            </small>
          ))}
        </div>
      )}
    </section>
  );
}

function InboxItem({ item }: { item: S["ApplicationSummaryOut"] }) {
  const missing = item.missing_musts ?? [];
  const age = freshness(item.posted_on, item.closes_on);
  const partial = item.partial_musts ?? [];
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const prepare = useMutation({
    mutationFn: () => post<S["AnalysisOut"]>(`/applications/${item.id}/prepare`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["applications"] });
      navigate(`/postulaciones/${item.id}`);
    },
  });
  const discard = useMutation({
    mutationFn: () => post(`/applications/${item.id}/status`, { status: "descartada", note: "Descartada desde la bandeja" }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["applications"] }),
  });
  return (
    <article className="card stack">
      <div>
        <h3>{item.role}</h3>
        <small>{[item.company, item.platform].filter(Boolean).join(" · ")}</small>
        {age && (
          <small style={{ display: "block" }} className={age.stale ? "" : "muted"}>
            {age.stale && <span className={`lvl ${age.closed ? "no" : "parcial"}`}>{age.closed ? "✗" : "!"} </span>}
            {age.text}{age.closed ? ": ya no recibe postulaciones" : ""}
          </small>
        )}
      </div>
      <ScoreBar score={item.match_score} />
      {missing.length > 0 && <small><span className="lvl no">✗</span> Te falta: {missing.slice(0, 3).join("; ")}{missing.length > 3 && ` y ${missing.length - 3} más`}</small>}
      {partial.length > 0 && <small><span className="lvl parcial">½</span> A medias: {partial.slice(0, 3).join("; ")}</small>}
      {!missing.length && !partial.length && item.match_score !== null && <small><span className="lvl cubre">✓</span> Cumples los requisitos obligatorios</small>}
      <ErrorNotice error={prepare.error ?? discard.error} />
      <div className="row">
        <button className="primary small" onClick={() => prepare.mutate()} disabled={prepare.isPending}>{prepare.isPending ? "Preparando…" : "Preparar postulación"}</button>
        {safeHref(item.url) && <a className="btn small" href={safeHref(item.url)} target="_blank" rel="noopener noreferrer">Ver vacante ↗</a>}
        <button className="small" onClick={() => discard.mutate()} disabled={discard.isPending}>Descartar</button>
      </div>
    </article>
  );
}

export function Inbox() {
  const inbox = useQuery({ queryKey: ["applications", "bandeja"], queryFn: () => get<S["ApplicationSummaryOut"][]>("/applications?view=bandeja") });
  return (
    <>
      <div className="page-head">
        <h1>Bandeja de vacantes</h1>
        <p>Las vacantes de tus alertas llegan solas, o pega las que encuentres: te las ordenamos según tu perfil. Tú decides cuáles preparar; <b>la postulación la envías tú</b> en el portal.</p>
      </div>
      <AlertsCard />
      <SearchPortals />
      <AddLinks />
      <h2>3. Por revisar {inbox.data && `(${inbox.data.length})`}</h2>
      {inbox.isPending && <Spinner />}
      <ErrorNotice error={inbox.error} />
      {inbox.data?.length === 0 && (
        <EmptyState title="Tu bandeja está vacía">Busca en los portales (paso 1) y pega aquí los enlaces (paso 2). <Link to="/postulaciones">Ver mis postulaciones</Link></EmptyState>
      )}
      {inbox.data?.map((item) => <InboxItem key={item.id} item={item} />)}
    </>
  );
}

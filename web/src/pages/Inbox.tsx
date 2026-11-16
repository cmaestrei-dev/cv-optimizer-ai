import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type ReactNode } from "react";
import { useNavigate } from "react-router";

import { get, post, safeHref, type S } from "../api/client";
import { AlertsCard } from "../components/inbox/AlertsCard";
import { ArrowIcon, CloseIcon, ExternalIcon } from "../components/icons";
import { EmptyState, ErrorNotice, ExternalLink, Mark, Notice, Score, Spinner, ZONE_LABEL, zoneOf, type Zone } from "../components/ui";
import { freshness } from "../lib/format";
import { useJob } from "../lib/useJob";

type TriageItem = { url: string; status: string; message: string; score: number | null };
type Item = S["ApplicationSummaryOut"];

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
    <details className="panel">
      <summary>Buscar en los portales</summary>
      <div className="stack">
        <p className="muted">Elige un cargo y abre la búsqueda en cada portal. Copia el enlace de cada vacante que te interese y pégalo en «Traer vacantes».</p>
        <label>Cargo<input type="text" value={title} onChange={(e) => setTitle(e.target.value)} placeholder="Ej.: Auxiliar administrativa" /></label>
        <label>Ciudad (opcional)<input type="text" value={city} onChange={(e) => setCity(e.target.value)} placeholder="Ej.: Bogotá" /></label>
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
            {links.data.map((l) => <ExternalLink key={l.portal} href={safeHref(l.url)}>{l.portal}</ExternalLink>)}
          </div>
        )}
      </div>
    </details>
  );
}

const RESULT_MARK = { agregada: "ok", repetida: "repeat" } as const;

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
    <section className="panel stack">
      <h2 className="panel-title" style={{ margin: 0 }}>Traer vacantes</h2>
      <label>
        Enlaces, uno por línea (hasta 10)
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
        <div className="stack" style={{ gap: 6 }}>
          {result.results.map((r) => (
            <small key={r.url} className="row" style={{ flexWrap: "nowrap", alignItems: "flex-start" }}>
              <Mark kind={RESULT_MARK[r.status as keyof typeof RESULT_MARK] ?? "no"} label={r.status} />
              <span>{r.message}{r.score !== null && ` · ${r.score}/100`}</span>
            </small>
          ))}
        </div>
      )}
    </section>
  );
}

function usePrepare(id: number) {
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  return useMutation({
    mutationFn: () => post<S["AnalysisOut"]>(`/applications/${id}/prepare`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["applications"] });
      navigate(`/postulaciones/${id}`);
    },
  });
}

function Lacks({ item }: { item: Item }) {
  const missing = item.missing_musts ?? [];
  const partial = item.partial_musts ?? [];
  if (item.match_score === null) return <span className="faint">Sin calcular</span>;
  if (!missing.length && !partial.length) return <span className="row"><Mark kind="ok" /> Cumple lo obligatorio</span>;
  return (
    <>
      {missing.length > 0 && (
        <span className="row"><Mark kind="no" /><span>{missing.slice(0, 2).join("; ")}{missing.length > 2 && ` y ${missing.length - 2} más`}</span></span>
      )}
      {partial.length > 0 && (
        <span className="row"><Mark kind="half" /><span>A medias: {partial.slice(0, 2).join("; ")}</span></span>
      )}
    </>
  );
}

function StandingRow({ item, position }: { item: Item; position: number }) {
  const queryClient = useQueryClient();
  const age = freshness(item.posted_on, item.closes_on);
  const closed = Boolean(age?.closed);
  const zone = zoneOf(item.match_score, closed);
  const prepare = usePrepare(item.id);
  const discard = useMutation({
    mutationFn: () => post(`/applications/${item.id}/status`, { status: "descartada", note: "Descartada desde la bandeja" }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["applications"] }),
  });
  const when = age && (
    <span className={`when ${age.closed ? "closed" : age.stale ? "stale" : ""}`}>
      {age.text.split(" · ").map((part, i) => (
        <span key={i} className="when-line">{part}{age.closed && i === age.text.split(" · ").length - 1 ? ": no recibe postulaciones" : ""}</span>
      ))}
    </span>
  );
  const href = safeHref(item.url);
  return (
    <tr className={[zone, closed && "closed"].filter(Boolean).join(" ")}>
      <td className="pos">
        <span className={`pos-box ${zone}`} aria-label={`Puesto ${position}: ${ZONE_LABEL[zone]}`}>{position}</span>
      </td>
      <td className="vac">
        <h3>{item.role}</h3>
        <span className="meta">{[item.company, item.platform].filter(Boolean).join(" · ")}</span>
        {when}
      </td>
      <td className="lack-cell"><div className="lack"><Lacks item={item} /></div></td>
      <td className="score-cell num"><Score score={item.match_score} /></td>
      <td className="acts">
        <div className="row">
          <button className={closed ? "small" : "primary small"} onClick={() => prepare.mutate()} disabled={prepare.isPending}>
            {prepare.isPending ? "Preparando…" : "Preparar"}
          </button>
          {href && (
            <a className="btn small icon-btn" href={href} target="_blank" rel="noopener noreferrer" title="Ver la vacante en el portal">
              <ExternalIcon /><span className="sr-only">Ver la vacante en el portal (abre en otra pestaña)</span>
            </a>
          )}
          <button className="small ghost icon-btn" onClick={() => discard.mutate()} disabled={discard.isPending} title="Descartar (se puede recuperar)">
            <CloseIcon /><span className="sr-only">Descartar {item.role}</span>
          </button>
        </div>
        {(prepare.error || discard.error) && <div style={{ marginTop: 8, whiteSpace: "normal" }}><ErrorNotice error={prepare.error ?? discard.error} /></div>}
      </td>
    </tr>
  );
}

/** Una sola decisión: la mejor vacante vigente en zona, o qué hacer si no hay ninguna. */
function NextMove({ items }: { items: Item[] }) {
  const open = items.filter((i) => !freshness(i.posted_on, i.closes_on)?.closed);
  const best = open.find((i) => zoneOf(i.match_score) === "up");
  const prepare = usePrepare(best?.id ?? 0);
  if (best) {
    const position = items.indexOf(best) + 1;
    const others = open.filter((i) => zoneOf(i.match_score) === "up").length - 1;
    return (
      <div className="next">
        <b className="tag">Tu próxima jugada</b>
        <p>
          <strong>#{position} {best.role}</strong>{best.company && ` en ${best.company}`} está en zona con {best.match_score}/100.
          {others > 0 ? ` Hay ${others} más en zona después de esta.` : " Prepárala ahora: el CV sale en segundos."}
        </p>
        <button className="primary" onClick={() => prepare.mutate()} disabled={prepare.isPending}>
          {prepare.isPending ? "Preparando…" : "Preparar postulación"}<ArrowIcon />
        </button>
        {prepare.error && <div style={{ flexBasis: "100%" }}><ErrorNotice error={prepare.error} /></div>}
      </div>
    );
  }
  return (
    <div className="next">
      <b className="tag">Tu próxima jugada</b>
      <p>
        {items.length
          ? "Ninguna vacante vigente llega a 75. Revisa qué les falta a las primeras o trae vacantes nuevas."
          : "Tu tabla está vacía. Pega enlaces de vacantes o activa las alertas por correo para que lleguen solas."}
      </p>
    </div>
  );
}

const ZONE_RANGE: Record<Zone, string> = { up: "75 o más", mid: "50 a 74", down: "menos de 50 o cerrada", none: "" };

function zoneOfItem(i: Item): Zone {
  return zoneOf(i.match_score, Boolean(freshness(i.posted_on, i.closes_on)?.closed));
}

/** Marcador del día: cuántas hay por revisar, en cada zona y cuántas alertas han llegado. */
function DayBoard({ items }: { items: Item[] }) {
  const alerts = useQuery({ queryKey: ["alerts"], queryFn: () => get<S["AlertsOut"]>("/alerts") });
  const count = (z: Zone) => items.filter((i) => zoneOfItem(i) === z).length;
  const a = alerts.data;
  return (
    <div className="campaign tight">
      <table>
        <thead>
          <tr>
            <th scope="col">Por revisar</th><th scope="col">En zona</th><th scope="col">Repechaje</th>
            <th scope="col">Descenso</th><th scope="col">Alertas recibidas</th>
          </tr>
        </thead>
        <tbody>
          <tr>
            <td data-label="Revisar">{items.length}</td>
            <td data-label="En zona" className="lvl cubre">{count("up")}</td>
            <td data-label="Repechaje" className="lvl parcial">{count("mid")}</td>
            <td data-label="Descenso" className="lvl no">{count("down")}</td>
            <td data-label="Alertas recibidas" className="wide">
              {a?.address ? a.received_count : "—"}
              <small>{a?.address ? (a.analyzing ? `${a.analyzing} analizándose` : "por correo") : "sin activar"}</small>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  );
}

export function Inbox() {
  const inbox = useQuery({ queryKey: ["applications", "bandeja"], queryFn: () => get<Item[]>("/applications?view=bandeja") });
  const items = inbox.data ?? [];
  const rows: ReactNode[] = [];
  items.forEach((item, i) => {
    const zone = zoneOfItem(item);
    if (i === 0 || zoneOfItem(items[i - 1]!) !== zone) {
      rows.push(
        <tr key={`zona-${zone}`} className={`zone-row ${zone}`}>
          <th colSpan={5} scope="rowgroup"><i aria-hidden="true" />{ZONE_LABEL[zone]}{ZONE_RANGE[zone] && <span>{ZONE_RANGE[zone]}</span>}</th>
        </tr>,
      );
    }
    rows.push(<StandingRow key={item.id} item={item} position={i + 1} />);
  });
  return (
    <>
      <div className="page-head">
        <div>
          <h1>Bandeja</h1>
          <p>Cada vacante entra con su puesto según cuánto calza con lo que de verdad hiciste. Prepara las de arriba; las que cerraron bajan solas.</p>
        </div>
      </div>
      {inbox.data && <NextMove items={items} />}
      <div className="with-rail">
        <section className="section">
          <div className="section-head">
            <h2>Tabla de posiciones</h2>
          </div>
          {inbox.data && <DayBoard items={items} />}
          {inbox.isPending && <Spinner />}
          <ErrorNotice error={inbox.error} />
          {inbox.data?.length === 0 && (
            <EmptyState title="Sin vacantes por revisar">Pega enlaces en «Traer vacantes» o activa las alertas por correo.</EmptyState>
          )}
          {items.length > 0 && (
            <div className="standings">
              <table>
                <thead>
                  <tr>
                    <th className="pos" scope="col">#</th>
                    <th scope="col">Vacante</th>
                    <th className="lack-cell" scope="col">Le falta</th>
                    <th className="num" scope="col">Compat.</th>
                    <th className="acts" scope="col"><span className="sr-only">Acciones</span></th>
                  </tr>
                </thead>
                <tbody>{rows}</tbody>
              </table>
            </div>
          )}
        </section>
        <aside className="rail" aria-label="Traer vacantes">
          <AddLinks />
          <AlertsCard />
          <SearchPortals />
        </aside>
      </div>
    </>
  );
}

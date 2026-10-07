import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useNavigate, useParams } from "react-router";

import { del, download, get, post, put, safeHref, type S } from "../api/client";
import { CopyButton, ErrorNotice, Level, Notice, ScoreBar, Spinner } from "../components/ui";
import { date, number, PLATFORMS, STATUS_LABELS, today } from "../lib/format";
import { useJob } from "../lib/useJob";

type Detail = S["ApplicationOut"];
type Analysis = S["AnalysisOut"];
type CVDocument = { summary: string; experiences: { role: string; company: string; bullets: { text: string; included: boolean }[] }[] };

function useInvalidate(id: number) {
  const queryClient = useQueryClient();
  return (...keys: string[]) => {
    for (const key of keys) queryClient.invalidateQueries({ queryKey: [key, id] });
    queryClient.invalidateQueries({ queryKey: ["applications"] });
    queryClient.invalidateQueries({ queryKey: ["usage"] });
  };
}

// ── compatibilidad ─────────────────────────────────────────────────────

function GapForm({ id, requirement }: { id: number; requirement: S["RequirementOut"] }) {
  const invalidate = useInvalidate(id);
  const profile = useQuery({ queryKey: ["profile"], queryFn: () => get<S["ProfileOut"]>("/profile") });
  const [experience, setExperience] = useState<number | "">("");
  const [story, setStory] = useState("");
  const gap = useMutation({
    mutationFn: () => post<S["GapOut"]>(`/applications/${id}/gaps`, { requirement: requirement.index, experience_id: experience, story }),
    onSuccess: () => invalidate("analysis"),
  });
  if (gap.data) {
    return (
      <Notice kind={gap.data.added ? "ok" : "warn"}>
        <p>{gap.data.added ? `Agregamos ${gap.data.added} logro(s) a tu perfil. Actualiza la compatibilidad arriba.` : "No se agregó nada nuevo."}</p>
        {gap.data.candidates.filter((c) => c.problems.length).map((c) => <small key={c.text}>No se agregó «{c.text}»: {c.problems.join("; ")}</small>)}
      </Notice>
    );
  }
  return (
    <div className="stack" style={{ marginTop: 8 }}>
      <label>¿En qué empleo?
        <select value={experience} onChange={(e) => setExperience(e.target.value ? Number(e.target.value) : "")}>
          <option value="">Elige…</option>
          {profile.data?.experiences.map((e) => <option key={e.id} value={e.id}>{e.role} — {e.company}</option>)}
        </select>
      </label>
      <label>¿Cómo lo hacías?
        <textarea rows={3} value={story} onChange={(e) => setStory(e.target.value)} placeholder="Ej.: usaba SAP para registrar las facturas de proveedores, unas 50 al mes" />
      </label>
      <ErrorNotice error={gap.error} />
      <div><button className="small primary" disabled={!experience || !story.trim() || gap.isPending} onClick={() => gap.mutate()}>
        {gap.isPending ? "Agregando…" : "Agregar a mi perfil"}
      </button></div>
    </div>
  );
}

function Requirement({ id, req }: { id: number; req: S["RequirementOut"] }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="req">
      <Level level={req.level} />
      <div>
        <b>{req.text}</b> <small style={{ display: "inline" }}>· {req.kind}</small>
        {req.evidence.slice(0, 2).map((e) => <small key={e.ref}>↳ {e.label}</small>)}
        {!req.evidence.length && req.note && <small>{req.note}</small>}
        {req.level !== "cubre" && !open && <button className="link" onClick={() => setOpen(true)}>Sí lo he hecho: contarlo</button>}
        {open && <GapForm id={id} requirement={req} />}
      </div>
    </div>
  );
}

function AnalysisSection({ id }: { id: number }) {
  const invalidate = useInvalidate(id);
  const queryClient = useQueryClient();
  const analysis = useQuery({ queryKey: ["analysis", id], queryFn: () => get<Analysis>(`/applications/${id}/analysis`) });
  const refresh = useMutation({
    mutationFn: () => post<Analysis>(`/applications/${id}/analysis`),
    onSuccess: (data) => { queryClient.setQueryData(["analysis", id], data); invalidate("application"); },
  });
  if (analysis.isPending) return <Spinner label="Calculando compatibilidad" />;
  if (analysis.error) return <ErrorNotice error={analysis.error} />;
  const { match, stale } = analysis.data;
  return (
    <section className="card stack">
      <h2>Compatibilidad</h2>
      {(stale || !match) && (
        <Notice kind="warn">
          <p>{match ? "Tu perfil cambió desde el análisis." : "Aún no se calcula con tu perfil."} Actualízala antes de generar el CV.</p>
          <button className="small primary" onClick={() => refresh.mutate()} disabled={refresh.isPending}>{refresh.isPending ? "Actualizando…" : "Actualizar compatibilidad"}</button>
        </Notice>
      )}
      <ErrorNotice error={refresh.error} />
      {match && (
        <>
          <ScoreBar score={match.score} />
          <small>
            Tu experiencia: {number(match.experience_years)} años{match.required_years ? ` (piden ${number(match.required_years)})` : ""}
            {match.meets_years === false && " · No alcanzas los años pedidos; igual puedes postular si cumples lo demás."}
          </small>
          <div>{match.requirements.map((r) => <Requirement key={r.index} id={id} req={r} />)}</div>
        </>
      )}
    </section>
  );
}

// ── CV ─────────────────────────────────────────────────────────────────

function CVEditor({ cvId, onSaved }: { cvId: number; onSaved: () => void }) {
  const cv = useQuery({ queryKey: ["cv", cvId], queryFn: () => get<S["CVDetailOut"]>(`/cvs/${cvId}`) });
  const [doc, setDoc] = useState<CVDocument | null>(null);
  const save = useMutation({
    mutationFn: (d: CVDocument) => put<S["CVResultOut"]>(`/cvs/${cvId}/document`, {
      summary: d.summary, experiences: d.experiences.map((e) => ({ bullets: e.bullets.map((b) => ({ text: b.text, included: b.included })) })),
    }),
    onSuccess: onSaved,
  });
  if (cv.isPending) return <Spinner />;
  if (cv.error) return <ErrorNotice error={cv.error} />;
  if (!cv.data?.document) return <Notice kind="warn"><p>Este CV se generó antes de poder editarse. Genera uno nuevo.</p></Notice>;
  const current = doc ?? (cv.data.document as unknown as CVDocument);
  const update = (fn: (d: CVDocument) => void) => { const next = structuredClone(current); fn(next); setDoc(next); };
  return (
    <div className="stack">
      <small className="faint">Lo que edites aquí no lo verifica la IA: es tu responsabilidad. Se guarda como una versión nueva.</small>
      <label>Resumen<textarea rows={4} value={current.summary} onChange={(e) => update((d) => { d.summary = e.target.value; })} /></label>
      {current.experiences.map((exp, i) => (
        <div key={i} className="stack" style={{ gap: 6 }}>
          <b>{exp.role}{exp.company && ` — ${exp.company}`}</b>
          {exp.bullets.map((b, j) => (
            <div key={j} className="row" style={{ alignItems: "flex-start", flexWrap: "nowrap" }}>
              <input type="checkbox" aria-label={`Incluir la viñeta ${j + 1} de ${exp.role}`} checked={b.included} style={{ marginTop: 14, width: 18, height: 18 }}
                onChange={() => update((d) => { d.experiences[i]!.bullets[j]!.included = !b.included; })} />
              <textarea rows={2} aria-label={`Viñeta ${j + 1} de ${exp.role}`} value={b.text} style={{ minHeight: 0 }}
                onChange={(e) => update((d) => { d.experiences[i]!.bullets[j]!.text = e.target.value; })} />
            </div>
          ))}
        </div>
      ))}
      <ErrorNotice error={save.error} />
      <div><button className="primary" disabled={!doc || save.isPending} onClick={() => doc && save.mutate(doc)}>{save.isPending ? "Generando PDF…" : "Guardar versión nueva"}</button></div>
    </div>
  );
}

function CVSection({ detail }: { detail: Detail }) {
  const invalidate = useInvalidate(detail.id);
  const [focus, setFocus] = useState("");
  const [editing, setEditing] = useState<number | null>(null);
  const generation = useJob();
  const result = generation.job?.status === "done" ? (generation.job.result as { pages: number; trimmed: string[]; reverted: string[]; summary_replaced: boolean }) : null;
  const versions = [...detail.cvs].reverse();

  return (
    <section className="card stack">
      <h2>Tu CV para esta vacante</h2>
      <label>Enfoque (opcional)<input type="text" value={focus} onChange={(e) => setFocus(e.target.value)} placeholder="Ej.: destacar facturación y atención al cliente" /></label>
      <div>
        <button className="primary" disabled={generation.running} onClick={async () => {
          const done = await generation.run(() => post<S["JobOut"]>(`/applications/${detail.id}/cvs`, { focus }));
          if (done) invalidate("application");
        }}>{generation.running ? "Generando…" : versions.length ? "Generar otro CV" : "Generar CV"}</button>
      </div>
      {generation.running && <Spinner label="Eligiendo tus logros, redactando y verificando" />}
      <ErrorNotice error={generation.error} />
      {result && (
        <Notice kind="ok">
          <p>CV listo ({result.pages} página).</p>
          {result.reverted.length > 0 && <small>Se usó tu texto original en {result.reverted.length} viñeta(s): la IA agregaba datos que no están en tu perfil.</small>}
          {result.summary_replaced && <small>El resumen de la IA no se respaldaba; se usó uno armado solo con tus datos.</small>}
          {result.trimmed.length > 0 && <small>Para caber en 1 página se quitó: {result.trimmed.join("; ")}</small>}
        </Notice>
      )}
      {versions.map((cv, i) => (
        <div key={cv.id} className="stack" style={{ borderTop: "1px solid var(--border)", paddingTop: 10 }}>
          <div className="row spread">
            <span><b>{i === 0 ? "Más reciente" : `Versión ${versions.length - i}`}</b> <small style={{ display: "inline" }}>· {date(cv.created_at)}{cv.sent_at && " · enviado"}{!cv.intact && " · no coincide con su huella"}</small></span>
            <div className="row">
              <button className="small" onClick={() => download(`/cvs/${cv.id}/pdf`, cv.filename)}>PDF</button>
              <button className="small" onClick={() => download(`/cvs/${cv.id}/docx`, cv.filename.replace(/\.pdf$/, ".docx"))}>Word</button>
              <button className="small" onClick={() => setEditing(editing === cv.id ? null : cv.id)}>{editing === cv.id ? "Cerrar" : "Editar"}</button>
            </div>
          </div>
          {editing === cv.id && <CVEditor cvId={cv.id} onSaved={() => { setEditing(null); invalidate("application"); }} />}
        </div>
      ))}
    </section>
  );
}

// ── ayudas ─────────────────────────────────────────────────────────────

function ScreeningSection({ id }: { id: number }) {
  const [questions, setQuestions] = useState("");
  const answer = useMutation({ mutationFn: () => post<S["ScreeningAnswerOut"][]>(`/applications/${id}/screening`, { questions: questions.split("\n").map((q) => q.trim()).filter(Boolean) }) });
  return (
    <details className="card">
      <summary><b>Preguntas del formulario del portal</b></summary>
      <div className="stack" style={{ marginTop: 12 }}>
        <p className="muted">Pega las preguntas del portal, una por línea. Respondemos con tus datos y marcamos lo que solo tú sabes.</p>
        <label>Preguntas (una por línea)
          <textarea rows={4} value={questions} onChange={(e) => setQuestions(e.target.value)} placeholder={"¿Cuántos años de experiencia tiene en facturación?\n¿Cuál es su aspiración salarial?"} />
        </label>
        <div><button disabled={!questions.trim() || answer.isPending} onClick={() => answer.mutate()}>{answer.isPending ? "Respondiendo…" : "Proponer respuestas"}</button></div>
        <ErrorNotice error={answer.error} />
        {answer.data?.map((a) => (
          <div key={a.question} className="stack" style={{ gap: 6 }}>
            <b>{a.question}</b>
            {a.answer && <div className="row" style={{ alignItems: "flex-start", flexWrap: "nowrap" }}><div className="copy-box" style={{ flex: 1 }}>{a.answer}</div><CopyButton text={a.answer} /></div>}
            {a.needs_you ? <small className="lvl parcial">Respóndela tú: {a.note || "depende de ti"}</small> : a.note && <small>{a.note}</small>}
          </div>
        ))}
      </div>
    </details>
  );
}

function CoverSection({ id }: { id: number }) {
  const cover = useMutation({ mutationFn: () => post<S["CoverOut"]>(`/applications/${id}/cover`) });
  return (
    <details className="card">
      <summary><b>Mensaje para el reclutador</b></summary>
      <div className="stack" style={{ marginTop: 12 }}>
        <p className="muted">Para el campo «carta de presentación», un correo o un mensaje por LinkedIn. Solo usa datos de tu perfil.</p>
        <div><button disabled={cover.isPending} onClick={() => cover.mutate()}>{cover.isPending ? "Escribiendo…" : cover.data ? "Escribir otro" : "Escribir mensaje"}</button></div>
        <ErrorNotice error={cover.error} />
        {cover.data && (
          <>
            <div className="copy-box">{cover.data.text}</div>
            <div><CopyButton text={cover.data.text} label="Copiar mensaje" /></div>
            {cover.data.fallback && <small>El borrador de la IA mencionaba datos que no están en tu perfil; este usa solo tus datos.</small>}
          </>
        )}
      </div>
    </details>
  );
}

// ── envío y seguimiento ────────────────────────────────────────────────

function SendSection({ detail }: { detail: Detail }) {
  const invalidate = useInvalidate(detail.id);
  const latest = detail.cvs[detail.cvs.length - 1];
  // Sin elección explícita se usa la versión más reciente de AHORA (no la que había al abrir la página).
  const [cvId, setCvId] = useState<number | null>(null);
  const selected = detail.cvs.find((c) => c.id === cvId)?.id ?? latest?.id;
  const [platform, setPlatform] = useState(detail.platform);
  const sent = useMutation({
    mutationFn: () => post<Detail>(`/applications/${detail.id}/sent`, { cv_id: selected, platform }),
    onSuccess: () => invalidate("application"),
  });
  if (detail.cvs.some((c) => c.sent_at)) return null;
  const chosen = detail.cvs.find((c) => c.id === selected);
  const versionLabel = (index: number) => (index === detail.cvs.length - 1 ? "Más reciente" : `Versión ${index + 1}`);
  return (
    <section className="card stack">
      <h2>Antes de enviar en el portal</h2>
      <ol>
        <li>Sube <b>{chosen?.filename ?? "el CV generado para esta vacante"}</b> (o su versión Word).</li>
        <li>Responde las preguntas del formulario (sección de arriba).</li>
        <li>Si el portal lo permite, pega el mensaje para el reclutador.</li>
        <li>Vuelve aquí y marca <b>Ya la envié</b>: queda registrado qué CV exacto enviaste.</li>
      </ol>
      {safeHref(detail.url) && <div><a className="btn small" href={safeHref(detail.url)} target="_blank" rel="noopener noreferrer">Abrir la vacante para postular ↗</a></div>}
      {detail.cvs.length > 0 ? (
        <div className="grid-2">
          <label>CV que enviaste
            <select value={selected} onChange={(e) => setCvId(Number(e.target.value))}>
              {detail.cvs.map((c, i) => ({ c, i })).reverse().map(({ c, i }) => (
                <option key={c.id} value={c.id}>{versionLabel(i)} · {date(c.created_at)}</option>
              ))}
            </select>
          </label>
          <label>Portal
            <select value={platform} onChange={(e) => setPlatform(e.target.value)} required>
              <option value="">Elige…</option>
              {PLATFORMS.map((p) => <option key={p}>{p}</option>)}
            </select>
          </label>
        </div>
      ) : <small className="muted">Genera el CV primero.</small>}
      <ErrorNotice error={sent.error} />
      <div><button className="primary" disabled={!detail.cvs.length || !platform || sent.isPending} onClick={() => sent.mutate()}>Ya la envié</button></div>
    </section>
  );
}

function TrackingSection({ detail }: { detail: Detail }) {
  const invalidate = useInvalidate(detail.id);
  const navigate = useNavigate();
  const [status, setStatus] = useState(detail.status);
  const [note, setNote] = useState("");
  const [follow, setFollow] = useState({ on: detail.next_action_on ?? "", what: detail.next_action });
  const [confirming, setConfirming] = useState(false);
  const change = useMutation({
    mutationFn: () => (status !== detail.status
      ? post(`/applications/${detail.id}/status`, { status, note })
      : post(`/applications/${detail.id}/notes`, { note })),
    onSuccess: () => { setNote(""); invalidate("application"); },
  });
  const followUp = useMutation({
    mutationFn: (on: string | null) => put(`/applications/${detail.id}/follow-up`, { on, what: follow.what }),
    onSuccess: () => invalidate("application"),
  });
  const remove = useMutation({ mutationFn: () => del(`/applications/${detail.id}`), onSuccess: () => { invalidate(); navigate("/postulaciones"); } });

  return (
    <section className="card stack">
      <h2>Seguimiento</h2>
      <div className="grid-2">
        <label>Estado
          <select value={status} onChange={(e) => setStatus(e.target.value)}>
            {Object.entries(STATUS_LABELS).map(([key, label]) => <option key={key} value={key}>{label}</option>)}
          </select>
        </label>
        <label>Nota (opcional)<input type="text" value={note} onChange={(e) => setNote(e.target.value)} placeholder="Ej.: me llamaron de RRHH" /></label>
      </div>
      <div><button className="small" disabled={(status === detail.status && !note.trim()) || change.isPending} onClick={() => change.mutate()}>Guardar</button></div>
      <ErrorNotice error={change.error} />
      <div className="grid-2">
        <label>Recordatorio<input type="date" value={follow.on} onChange={(e) => setFollow({ ...follow, on: e.target.value })} min={today()} /></label>
        <label>¿Qué hacer?<input type="text" value={follow.what} onChange={(e) => setFollow({ ...follow, what: e.target.value })} placeholder="Ej.: escribirle a la reclutadora" /></label>
      </div>
      <div className="row">
        <button className="small" disabled={!follow.on || followUp.isPending} onClick={() => followUp.mutate(follow.on)}>Guardar recordatorio</button>
        {detail.next_action_on && <button className="small" onClick={() => { setFollow({ on: "", what: "" }); followUp.mutate(null); }}>Quitar recordatorio</button>}
      </div>
      <details>
        <summary className="muted">Historial ({detail.events.length})</summary>
        <ul>{[...detail.events].reverse().map((e) => (
          <li key={e.id}><small>{date(e.created_at)} · {e.kind === "estado" ? `${STATUS_LABELS[e.from_status] ?? e.from_status} → ${STATUS_LABELS[e.to_status] ?? e.to_status}` : e.kind}{e.detail && ` · ${e.detail}`}</small></li>
        ))}</ul>
      </details>
      {confirming ? (
        <div className="row">
          <span className="muted">¿Eliminar esta postulación con sus CV e historial?</span>
          <button className="small danger" onClick={() => remove.mutate()}>Sí, eliminar</button>
          <button className="small" onClick={() => setConfirming(false)}>No</button>
        </div>
      ) : <div><button className="small danger" onClick={() => setConfirming(true)}>Eliminar postulación</button></div>}
    </section>
  );
}

export function ApplicationDetail() {
  const id = Number(useParams().id);
  const detail = useQuery({ queryKey: ["application", id], queryFn: () => get<Detail>(`/applications/${id}`), enabled: Number.isInteger(id) });
  if (!Number.isInteger(id)) return <Notice kind="warn"><p>Esa postulación no existe.</p></Notice>;
  if (detail.isPending) return <Spinner />;
  if (detail.error) return <ErrorNotice error={detail.error} />;
  const d = detail.data;
  return (
    <>
      <div className="page-head">
        <small className="status activa">{d.status_label}</small>
        <h1>{d.role}</h1>
        <p>{[d.company, d.platform, d.applied_on && `enviada el ${date(d.applied_on)}`].filter(Boolean).join(" · ")}
          {safeHref(d.url) && <> · <a href={safeHref(d.url)} target="_blank" rel="noopener noreferrer">ver vacante ↗</a></>}</p>
      </div>
      {d.vacancy ? (
        <>
          <AnalysisSection id={d.id} />
          <CVSection detail={d} />
          <ScreeningSection id={d.id} />
          <CoverSection id={d.id} />
          <SendSection detail={d} />
        </>
      ) : (
        <Notice kind="info"><p>Esta postulación se registró sin el texto de la vacante: aquí solo llevas su seguimiento.</p></Notice>
      )}
      <TrackingSection key={`${d.status}-${d.next_action_on}`} detail={d} />
    </>
  );
}

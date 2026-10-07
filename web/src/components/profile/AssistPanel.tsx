import { useState } from "react";

import { post, type S } from "../../api/client";
import { ErrorNotice, Notice, Spinner } from "../ui";
import { useSaveProfile } from "./useSaveProfile";

type Candidate = S["CandidateOut"];

/** Candidatos verificados: la persona marca cuáles agregar; los que no se respaldan vienen desmarcados. */
function CandidatePicker({ experienceId, candidates, onAdded }: {
  experienceId: number; candidates: Candidate[]; onAdded: () => void;
}) {
  const save = useSaveProfile();
  const [chosen, setChosen] = useState<string[]>(candidates.filter((c) => c.suggested).map((c) => c.text));
  const [error, setError] = useState<unknown>(null);
  const [saving, setSaving] = useState(false);
  if (!candidates.length) return <p className="muted">No salió nada nuevo de eso.</p>;
  return (
    <div className="stack">
      {candidates.map((c) => (
        <label className="check" key={c.text}>
          <input type="checkbox" checked={chosen.includes(c.text)}
            onChange={() => setChosen(chosen.includes(c.text) ? chosen.filter((t) => t !== c.text) : [...chosen, c.text])} />
          <span>
            {c.text}
            {c.duplicate_of && <small>Ya lo tienes: «{c.duplicate_of}»</small>}
            {c.problems.length > 0 && <small className="lvl no">No sale de lo que escribiste: {c.problems.join("; ")}</small>}
          </span>
        </label>
      ))}
      <ErrorNotice error={error} />
      <button className="primary" disabled={!chosen.length || saving} onClick={async () => {
        setSaving(true);
        try {
          save(await post<S["ProfileOut"]>(`/experiences/${experienceId}/achievements`, { texts: chosen }));
          onAdded();
        } catch (e) { setError(e); } finally { setSaving(false); }
      }}>{saving ? "Agregando…" : `Agregar ${chosen.length} a mi perfil`}</button>
    </div>
  );
}

function FreeText({ experience }: { experience: S["ExperienceOut"] }) {
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [candidates, setCandidates] = useState<Candidate[] | null>(null);
  const [done, setDone] = useState(false);
  return (
    <div className="stack">
      <label>
        Cuéntanos con tus palabras todo lo que hacías en este cargo
        <textarea rows={5} value={text} onChange={(e) => setText(e.target.value)}
          placeholder="Ej.: hacía las facturas de los carros, unas 60 al mes, y llamaba a los clientes que debían…" />
      </label>
      <ErrorNotice error={error} />
      <button disabled={busy || !text.trim()} onClick={async () => {
        setBusy(true); setError(null); setDone(false);
        try { setCandidates(await post<Candidate[]>(`/experiences/${experience.id}/suggestions/from-text`, { text })); }
        catch (e) { setError(e); } finally { setBusy(false); }
      }}>{busy ? "Ordenando…" : "Convertir en logros"}</button>
      {busy && <Spinner label="Ordenando lo que escribiste" />}
      {done && <Notice kind="ok"><p>Agregado a tu perfil.</p></Notice>}
      {candidates && !done && (
        <CandidatePicker experienceId={experience.id} candidates={candidates}
          onAdded={() => { setDone(true); setCandidates(null); setText(""); }} />
      )}
    </div>
  );
}

function TypicalTasks({ experience }: { experience: S["ExperienceOut"] }) {
  const [tasks, setTasks] = useState<string[] | null>(null);
  const [picked, setPicked] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [candidates, setCandidates] = useState<Candidate[] | null>(null);
  const [done, setDone] = useState(false);
  if (!tasks) {
    return (
      <div className="stack">
        <p className="muted">Te mostramos tareas típicas de «{experience.role}» como recordatorio. Marca solo las que sí hiciste.</p>
        <ErrorNotice error={error} />
        <button disabled={busy} onClick={async () => {
          setBusy(true); setError(null);
          try { setTasks((await post<S["TasksOut"]>(`/experiences/${experience.id}/suggestions/tasks`)).tasks); }
          catch (e) { setError(e); } finally { setBusy(false); }
        }}>{busy ? "Buscando…" : "Ver tareas típicas"}</button>
      </div>
    );
  }
  return (
    <div className="stack">
      {tasks.map((task) => (
        <div key={task} className="stack" style={{ gap: 6 }}>
          <label className="check">
            <input type="checkbox" checked={task in picked} onChange={() => {
              const next = { ...picked };
              if (task in next) delete next[task]; else next[task] = "";
              setPicked(next);
            }} />
            {task}
          </label>
          {task in picked && (
            <input type="text" aria-label={`Detalle de: ${task}`} placeholder="Detalle opcional: cuántas, con qué herramienta…"
              value={picked[task]} onChange={(e) => setPicked({ ...picked, [task]: e.target.value })} />
          )}
        </div>
      ))}
      <ErrorNotice error={error} />
      {done && <Notice kind="ok"><p>Agregado a tu perfil.</p></Notice>}
      {!candidates && (
        <button disabled={busy || !Object.keys(picked).length} onClick={async () => {
          setBusy(true); setError(null); setDone(false);
          try {
            setCandidates(await post<Candidate[]>(`/experiences/${experience.id}/suggestions/from-tasks`, {
              items: Object.entries(picked).map(([task, detail]) => ({ task, detail })),
            }));
          } catch (e) { setError(e); } finally { setBusy(false); }
        }}>{busy ? "Preparando…" : "Revisar y agregar"}</button>
      )}
      {candidates && (
        <CandidatePicker experienceId={experience.id} candidates={candidates}
          onAdded={() => { setDone(true); setCandidates(null); setPicked({}); }} />
      )}
    </div>
  );
}

function Interview({ experience }: { experience: S["ExperienceOut"] }) {
  const save = useSaveProfile();
  const [questions, setQuestions] = useState<S["QuestionOut"][] | null>(null);
  const [answers, setAnswers] = useState<string[]>([]);
  const [proposals, setProposals] = useState<S["ProposalOut"][] | null>(null);
  const [chosen, setChosen] = useState<number[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [done, setDone] = useState(false);

  async function call<T>(fn: () => Promise<T>): Promise<T | null> {
    setBusy(true); setError(null);
    try { return await fn(); } catch (e) { setError(e); return null; } finally { setBusy(false); }
  }

  if (done) return <Notice kind="ok"><p>Listo: tus logros quedaron mejorados.</p></Notice>;
  if (!questions) {
    return (
      <div className="stack">
        <p className="muted">Te hacemos unas preguntas cortas para sumar cifras, herramientas y resultados a lo que ya escribiste.</p>
        <ErrorNotice error={error} />
        <button disabled={busy} onClick={async () => {
          const q = await call(() => post<S["QuestionOut"][]>(`/experiences/${experience.id}/interview/questions`));
          if (q) { setQuestions(q); setAnswers(q.map(() => "")); }
        }}>{busy ? "Preparando preguntas…" : "Empezar entrevista"}</button>
      </div>
    );
  }
  const answered = questions.map((q, i) => ({ achievement_id: q.achievement_id, question: q.question, answer: answers[i] ?? "" }));
  return (
    <div className="stack">
      {!proposals && questions.map((q, i) => (
        <label key={i}>
          {q.question}
          <textarea rows={2} value={answers[i] ?? ""} placeholder={q.example ? `Ej.: ${q.example}` : "Si no aplica, déjala vacía"}
            onChange={(e) => setAnswers(answers.map((a, j) => (j === i ? e.target.value : a)))} />
        </label>
      ))}
      {!proposals && (
        <button className="primary" disabled={busy || !answers.some((a) => a.trim())} onClick={async () => {
          const p = await call(() => post<S["ProposalOut"][]>(`/experiences/${experience.id}/interview/proposals`, { answers: answered }));
          if (p) { setProposals(p); setChosen(p.flatMap((x, i) => (x.problems.length ? [] : [i]))); }
        }}>{busy ? "Mejorando…" : "Proponer mejoras"}</button>
      )}
      {proposals && (
        <>
          {!proposals.length && <p className="muted">Con esas respuestas no hay mejoras que proponer.</p>}
          {proposals.map((p, i) => (
            <label className="check" key={i}>
              <input type="checkbox" disabled={p.problems.length > 0} checked={chosen.includes(i)}
                onChange={() => setChosen(chosen.includes(i) ? chosen.filter((x) => x !== i) : [...chosen, i])} />
              <span>
                {p.proposed}
                <small>{p.original ? `Antes: ${p.original}` : "Logro nuevo"}</small>
                {p.problems.length > 0 && <small className="lvl no">No sale de tus respuestas: {p.problems.join("; ")}</small>}
              </span>
            </label>
          ))}
          <div className="row">
            <button className="primary" disabled={busy || !chosen.length} onClick={async () => {
              const accepted = chosen.map((i) => ({ achievement_id: proposals[i]!.achievement_id, text: proposals[i]!.proposed }));
              const profile = await call(() => post<S["ProfileOut"]>(`/experiences/${experience.id}/interview/accept`, {
                accepted, answers: answered.map((a) => a.answer).filter((a) => a.trim()),
              }));
              if (profile) { save(profile); setDone(true); }
            }}>Aplicar {chosen.length} mejora(s)</button>
            <button onClick={() => setProposals(null)} disabled={busy}>Volver a las respuestas</button>
          </div>
        </>
      )}
      <ErrorNotice error={error} />
    </div>
  );
}

const MODES = [
  { key: "text", label: "Cuéntame" },
  { key: "tasks", label: "Tareas típicas" },
  { key: "interview", label: "Entrevista" },
] as const;

export function AssistPanel({ experience }: { experience: S["ExperienceOut"] }) {
  const [mode, setMode] = useState<(typeof MODES)[number]["key"]>("text");
  return (
    <div className="stack" style={{ background: "var(--canvas)", borderRadius: "var(--radius)", padding: 12 }}>
      <div className="tabs" role="tablist">
        {MODES.map((m) => (
          <button key={m.key} role="tab" aria-selected={mode === m.key} onClick={() => setMode(m.key)}>{m.label}</button>
        ))}
      </div>
      {mode === "text" && <FreeText experience={experience} />}
      {mode === "tasks" && <TypicalTasks experience={experience} />}
      {mode === "interview" && <Interview experience={experience} />}
      <small className="faint">Todo se verifica contra tus palabras: la IA no puede agregar datos que no diste.</small>
    </div>
  );
}

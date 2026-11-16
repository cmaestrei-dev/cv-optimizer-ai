import { useState, type FormEvent } from "react";

import { del, post, put, type S } from "../../api/client";
import { ErrorNotice } from "../ui";
import { AssistPanel } from "./AssistPanel";
import { useSaveProfile } from "./useSaveProfile";

type Experience = S["ExperienceOut"];

const hasNumber = (text: string) => /\d/.test(text);

export function ExperienceForm({ initial, onDone, onCancel }: {
  initial?: Experience; onDone: (p: S["ProfileOut"]) => void; onCancel: () => void;
}) {
  const [form, setForm] = useState({
    role: initial?.role ?? "", company: initial?.company ?? "", period_text: initial?.period_text ?? "",
    country: initial?.country ?? "", modality: initial?.modality ?? "",
    achievements: (initial?.achievements ?? []).map((a) => a.text).join("\n"),
  });
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  const set = (key: keyof typeof form) => (e: { target: { value: string } }) => setForm({ ...form, [key]: e.target.value });

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    const body = { ...form, achievements: form.achievements.split("\n").map((t) => t.trim()).filter(Boolean) };
    try {
      onDone(initial ? await put<S["ProfileOut"]>(`/experiences/${initial.id}`, body) : await post<S["ProfileOut"]>("/experiences", body));
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }

  return (
    <form className="stack" onSubmit={submit}>
      <div className="grid-2">
        <label>Cargo<input type="text" value={form.role} onChange={set("role")} required /></label>
        <label>Empresa<input type="text" value={form.company} onChange={set("company")} /></label>
        <label>Periodo<input type="text" value={form.period_text} onChange={set("period_text")} placeholder="Marzo 2023 - Presente" /></label>
        <label>Modalidad
          <select value={form.modality} onChange={set("modality")}>
            <option value="">—</option><option>Presencial</option><option>Híbrido</option><option>Remoto</option>
          </select>
        </label>
      </div>
      <label>
        Funciones y logros (uno por línea)
        <textarea rows={6} value={form.achievements} onChange={set("achievements")}
          placeholder={"Elaboré unas 120 facturas al mes en SAP\nAtendí a los clientes del taller"} />
      </label>
      <ErrorNotice error={error} />
      <div className="row">
        <button className="primary" disabled={busy}>{busy ? "Guardando…" : "Guardar"}</button>
        <button type="button" onClick={onCancel} disabled={busy}>Cancelar</button>
      </div>
    </form>
  );
}

export function ExperienceCard({ experience }: { experience: Experience }) {
  const save = useSaveProfile();
  const [mode, setMode] = useState<"view" | "edit" | "assist">("view");
  const [confirming, setConfirming] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const withNumbers = experience.achievements.filter((a) => hasNumber(a.text)).length;

  if (mode === "edit") {
    return (
      <div className="career-row" style={{ display: "block" }}>
        <ExperienceForm initial={experience} onDone={(p) => { save(p); setMode("view"); }} onCancel={() => setMode("view")} />
      </div>
    );
  }

  const total = experience.achievements.length;
  return (
    <article className="career-row">
      <div className="career-when">
        {experience.period_text || "Sin periodo"}
        <small>{[experience.modality, experience.country].filter(Boolean).join(" · ")}</small>
      </div>
      <div className="career-body">
        <h3>{experience.role}</h3>
        <div className="meta">{experience.company}{total > 0 && <> · <span className={withNumbers === total ? "lvl cubre" : withNumbers / total < 0.5 ? "lvl parcial" : ""}>{withNumbers} de {total} logros con cifras</span></>}</div>
        {total ? (
          <ul>{experience.achievements.map((a) => <li key={a.id}>{a.text}</li>)}</ul>
        ) : (
          <p className="muted" style={{ marginTop: 10 }}>Sin funciones ni logros todavía. Usa «Completar con IA»: es lo que más mejora tu CV.</p>
        )}
        <ErrorNotice error={error} />
        <div className="row acts-row">
          <button className={mode === "assist" ? "small" : "small primary"} onClick={() => setMode(mode === "assist" ? "view" : "assist")}>
            {mode === "assist" ? "Cerrar" : "Completar con IA"}
          </button>
          <button className="small" onClick={() => setMode("edit")}>Editar</button>
          {confirming ? (
            <>
              <button className="small danger" onClick={async () => {
                try { save(await del<S["ProfileOut"]>(`/experiences/${experience.id}`)); } catch (e) { setError(e); }
              }}>Sí, eliminar</button>
              <button className="small" onClick={() => setConfirming(false)}>No</button>
            </>
          ) : (
            <button className="small ghost" onClick={() => setConfirming(true)}>Eliminar</button>
          )}
        </div>
        {mode === "assist" && <div style={{ marginTop: 14 }}><AssistPanel experience={experience} /></div>}
      </div>
    </article>
  );
}

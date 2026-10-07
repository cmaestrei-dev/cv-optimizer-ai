import { useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { post, type S } from "../../api/client";
import { useJob } from "../../lib/useJob";
import { ErrorNotice, Notice, Spinner } from "../ui";

type ImportResult = {
  data: {
    experiences: { role: string; company: string; period_text: string; achievements: string[] }[];
    skills: { name: string; category: string }[];
    education: { title: string; institution: string }[];
  };
  new_experiences: number[];
  duplicate_experiences: number[];
  new_skills: number[];
  new_education: number[];
  discarded: string[];
};

function toggle(list: number[], i: number): number[] {
  return list.includes(i) ? list.filter((x) => x !== i) : [...list, i];
}

/** Subir el CV o el PDF de LinkedIn → revisar lo leído → guardar lo elegido. */
export function ImportCard({ prominent = false, onSaved }: { prominent?: boolean; onSaved?: (message: string) => void }) {
  const queryClient = useQueryClient();
  const reading = useJob();
  const [choice, setChoice] = useState<{ exp: number[]; skills: number[]; edu: number[] } | null>(null);
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<unknown>(null);
  const [saved, setSaved] = useState<string | null>(null);

  const result = reading.job?.status === "done" ? (reading.job.result as unknown as ImportResult) : null;

  async function upload(file: File) {
    setSaved(null);
    setChoice(null);
    const form = new FormData();
    form.append("file", file);
    const done = await reading.run(() => post<S["JobOut"]>("/profile/import", form));
    const r = done?.result as unknown as ImportResult | undefined;
    if (r) setChoice({ exp: r.new_experiences, skills: r.new_skills, edu: r.new_education });
  }

  async function save() {
    if (!reading.job || !choice) return;
    setSaving(true);
    setSaveError(null);
    try {
      const out = await post<S["ImportApplyOut"]>(`/profile/import/${reading.job.id}/apply`, {
        experiences: choice.exp, skills: choice.skills, education: choice.edu, fill_contact: true,
      });
      queryClient.setQueryData(["profile"], out.profile);
      queryClient.invalidateQueries({ queryKey: ["me"] });
      const c = out.counts;
      const message = `Guardado: ${c.experiencias} experiencias, ${c.logros} logros, ${c.habilidades} habilidades y ${c.estudios} estudios.`;
      setSaved(message);
      onSaved?.(message); // la tarjeta puede cambiar de lugar al dejar de estar vacío el perfil
      reading.reset();
      setChoice(null);
    } catch (e) {
      setSaveError(e);
    } finally {
      setSaving(false);
    }
  }

  return (
    <section className="card stack">
      <div>
        <h2>{prominent ? "Empieza con tu CV" : "Importar CV o LinkedIn"}</h2>
        <p className="muted">
          Sube tu CV en PDF o el PDF de tu perfil de LinkedIn (en LinkedIn: «Más» → «Guardar en PDF»). La IA solo
          copia lo que dice; lo que no esté en el PDF se descarta y tú eliges qué guardar.
        </p>
      </div>
      {saved && <Notice kind="ok"><p>{saved} Ahora completa tus logros: mientras más cifras, mejor el CV.</p></Notice>}
      {!result && (
        <label>
          Archivo PDF
          <input
            type="file"
            accept="application/pdf,.pdf"
            disabled={reading.running}
            onChange={(e) => {
              const file = e.target.files?.[0];
              if (file) void upload(file);
              e.target.value = "";
            }}
          />
        </label>
      )}
      {reading.running && <Spinner label="Leyendo tu CV" />}
      <ErrorNotice error={reading.error} />

      {result && choice && (
        <div className="stack">
          <h3>Revisa lo que encontramos</h3>
          {result.data.experiences.length > 0 && (
            <fieldset className="stack" style={{ border: 0, padding: 0, margin: 0 }}>
              <legend className="muted">Experiencias</legend>
              {result.data.experiences.map((e, i) => {
                const duplicate = result.duplicate_experiences.includes(i);
                return (
                  <label className="check" key={i}>
                    <input type="checkbox" disabled={duplicate} checked={choice.exp.includes(i)}
                      onChange={() => setChoice({ ...choice, exp: toggle(choice.exp, i) })} />
                    <span>
                      <b>{e.role}</b>{e.company && ` — ${e.company}`}
                      <small style={{ display: "block" }}>
                        {[e.period_text, duplicate ? "ya está en tu perfil" : `${e.achievements.length} logros`].filter(Boolean).join(" · ")}
                      </small>
                    </span>
                  </label>
                );
              })}
            </fieldset>
          )}
          {result.new_skills.length > 0 && (
            <div className="row">
              {result.new_skills.map((i) => (
                <label className="check chip" key={i}>
                  <input type="checkbox" checked={choice.skills.includes(i)}
                    onChange={() => setChoice({ ...choice, skills: toggle(choice.skills, i) })} />
                  {result.data.skills[i]?.name}
                </label>
              ))}
            </div>
          )}
          {result.new_education.map((i) => (
            <label className="check" key={`e${i}`}>
              <input type="checkbox" checked={choice.edu.includes(i)}
                onChange={() => setChoice({ ...choice, edu: toggle(choice.edu, i) })} />
              <span>{result.data.education[i]?.title} <small>{result.data.education[i]?.institution}</small></span>
            </label>
          ))}
          {result.discarded.length > 0 && (
            <details>
              <summary className="muted">No se importó ({result.discarded.length}): no aparece en el PDF</summary>
              <ul>{result.discarded.map((d) => <li key={d}><small>{d}</small></li>)}</ul>
            </details>
          )}
          <ErrorNotice error={saveError} />
          <div className="row">
            <button className="primary" onClick={save} disabled={saving}>{saving ? "Guardando…" : "Guardar en mi perfil"}</button>
            <button onClick={() => { reading.reset(); setChoice(null); }} disabled={saving}>Descartar</button>
          </div>
        </div>
      )}
    </section>
  );
}

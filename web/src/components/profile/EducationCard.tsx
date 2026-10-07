import { useState, type FormEvent } from "react";

import { del, post, type S } from "../../api/client";
import { ErrorNotice } from "../ui";
import { useSaveProfile } from "./useSaveProfile";

export function EducationCard({ education }: { education: S["EducationOut"][] }) {
  const save = useSaveProfile();
  const [form, setForm] = useState({ title: "", institution: "", period_text: "" });
  const [adding, setAdding] = useState(false);
  const [error, setError] = useState<unknown>(null);

  async function add(e: FormEvent) {
    e.preventDefault();
    setError(null);
    try {
      save(await post<S["ProfileOut"]>("/education", form));
      setForm({ title: "", institution: "", period_text: "" });
      setAdding(false);
    } catch (err) {
      setError(err);
    }
  }

  return (
    <section className="card stack">
      <h2>Educación y certificados</h2>
      {education.map((d) => (
        <div className="row spread" key={d.id}>
          <span><b>{d.title}</b> <small>{[d.institution, d.period_text].filter(Boolean).join(" · ")}</small></span>
          <button className="small danger" onClick={async () => {
            try { save(await del<S["ProfileOut"]>(`/education/${d.id}`)); } catch (err) { setError(err); }
          }}>Quitar</button>
        </div>
      ))}
      {adding ? (
        <form className="stack" onSubmit={add}>
          <div className="grid-2">
            <label>Título o curso<input type="text" required value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} /></label>
            <label>Institución<input type="text" value={form.institution} onChange={(e) => setForm({ ...form, institution: e.target.value })} /></label>
            <label>Periodo<input type="text" value={form.period_text} onChange={(e) => setForm({ ...form, period_text: e.target.value })} placeholder="2018 - 2020" /></label>
          </div>
          <div className="row">
            <button className="primary small">Guardar</button>
            <button type="button" className="small" onClick={() => setAdding(false)}>Cancelar</button>
          </div>
        </form>
      ) : (
        <button className="small" onClick={() => setAdding(true)}>Agregar estudio o certificado</button>
      )}
      <ErrorNotice error={error} />
    </section>
  );
}

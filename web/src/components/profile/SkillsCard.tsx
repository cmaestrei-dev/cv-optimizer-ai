import { useState, type FormEvent } from "react";

import { ApiError, del, post, type S } from "../../api/client";
import { ErrorNotice } from "../ui";
import { useSaveProfile } from "./useSaveProfile";

const CATEGORIES = ["Herramientas y software", "Conocimientos del área", "Procesos y metodologías", "Idiomas", "Habilidades blandas", "Otros"];

export function SkillsCard({ skills }: { skills: S["SkillOut"][] }) {
  const save = useSaveProfile();
  const [name, setName] = useState("");
  const [category, setCategory] = useState(CATEGORIES[0]!);
  const [error, setError] = useState<unknown>(null);

  async function add(e: FormEvent) {
    e.preventDefault();
    if (!name.trim()) return;
    setError(null);
    try {
      save(await post<S["ProfileOut"]>("/skills", { name: name.trim(), category }));
      setName("");
    } catch (err) {
      setError(err instanceof ApiError && err.status === 409 ? new Error("Ya tienes esa habilidad.") : err);
    }
  }

  const groups = CATEGORIES.map((c) => [c, skills.filter((s) => s.category === c)] as const)
    .concat([["Otras", skills.filter((s) => !CATEGORIES.includes(s.category))] as const])
    .filter(([, list]) => list.length);

  return (
    <section className="card stack">
      <h2>Habilidades</h2>
      {groups.map(([label, list]) => (
        <div key={label}>
          <small>{label}</small>
          <div className="row" style={{ marginTop: 6 }}>
            {list.map((s) => (
              <span className="chip" key={s.id}>
                {s.name}
                <button aria-label={`Quitar ${s.name}`} onClick={async () => {
                  try { save(await del<S["ProfileOut"]>(`/skills/${s.id}`)); } catch (err) { setError(err); }
                }}>×</button>
              </span>
            ))}
          </div>
        </div>
      ))}
      <form className="grid-2" onSubmit={add}>
        <label>Nueva habilidad<input type="text" value={name} onChange={(e) => setName(e.target.value)} placeholder="Ej.: Excel, SAP, inglés" /></label>
        <label>Tipo
          <select value={category} onChange={(e) => setCategory(e.target.value)}>
            {CATEGORIES.map((c) => <option key={c}>{c}</option>)}
          </select>
        </label>
        <button className="small" disabled={!name.trim()}>Agregar habilidad</button>
      </form>
      <ErrorNotice error={error} />
    </section>
  );
}

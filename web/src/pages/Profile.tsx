import { useQuery } from "@tanstack/react-query";
import { useState } from "react";

import { get, type S } from "../api/client";
import { PlusIcon } from "../components/icons";
import { ContactCard } from "../components/profile/ContactCard";
import { EducationCard } from "../components/profile/EducationCard";
import { ExperienceCard, ExperienceForm } from "../components/profile/ExperienceCard";
import { ImportCard } from "../components/profile/ImportCard";
import { LinkLegacyCard } from "../components/profile/LinkLegacyCard";
import { SkillsCard } from "../components/profile/SkillsCard";
import { useSaveProfile } from "../components/profile/useSaveProfile";
import { ErrorNotice, Notice, Spinner } from "../components/ui";

export function Profile() {
  const profile = useQuery({ queryKey: ["profile"], queryFn: () => get<S["ProfileOut"]>("/profile") });
  const save = useSaveProfile();
  const [adding, setAdding] = useState(false);
  const [imported, setImported] = useState<string | null>(null);

  if (profile.isPending) return <Spinner />;
  if (profile.error) return <ErrorNotice error={profile.error} />;
  const p = profile.data;
  const empty = p.experiences.length === 0;
  const total = p.achievements_total;
  const withNumbers = p.achievements_with_numbers;

  return (
    <>
      <div className="page-head">
        <div>
          <h1>{p.contact.full_name || "Tu perfil"}</h1>
          <p>Todo lo que hiciste, con tus palabras y tus cifras. De aquí sale cada CV: nunca se inventa nada.</p>
        </div>
      </div>
      {!empty && (
        <div className="campaign tight">
          <table>
            <thead>
              <tr><th scope="col">Cargos</th><th scope="col">Logros</th><th scope="col">Con cifras</th><th scope="col">Habilidades</th><th scope="col">Estudios</th></tr>
            </thead>
            <tbody>
              <tr>
                <td data-label="Cargos">{p.experiences.length}</td>
                <td data-label="Logros">{total}</td>
                <td data-label="Con cifras" className={["wide", total && withNumbers === total ? "lvl cubre" : total && withNumbers / total < 0.5 ? "lvl parcial" : ""].filter(Boolean).join(" ")}>
                  {withNumbers}<small>{withNumbers} de {total} logros tienen cifras</small>
                </td>
                <td data-label="Habilidades">{p.skills.length}</td>
                <td data-label="Estudios">{p.education.length}</td>
              </tr>
            </tbody>
          </table>
        </div>
      )}

      {imported && (
        <Notice kind="ok"><p>{imported} Ahora completa tus logros con «Completar con IA»: mientras más cifras, mejor el CV.</p></Notice>
      )}
      {empty && <LinkLegacyCard />}
      {empty && <ImportCard prominent onSaved={setImported} />}
      {!empty && total > 0 && withNumbers / total < 0.5 && (
        <Notice kind="warn"><p>Menos de la mitad de tus logros tienen cifras. Usa «Completar con IA» en cada cargo: los logros con cifras pesan más en el CV.</p></Notice>
      )}

      <div className="with-rail">
        <section className="section">
          <div className="section-head">
            <h2>Trayectoria</h2>
            {!adding && <button className="small" onClick={() => setAdding(true)}><PlusIcon />Agregar cargo</button>}
          </div>
          {adding && (
            <div className="panel" style={{ marginBottom: 16 }}>
              <ExperienceForm onDone={(np) => { save(np); setAdding(false); }} onCancel={() => setAdding(false)} />
            </div>
          )}
          {p.experiences.length > 0 ? (
            <div className="career">{p.experiences.map((e) => <ExperienceCard key={e.id} experience={e} />)}</div>
          ) : (
            !adding && <p className="muted">Aún no hay cargos. Importa tu CV arriba o agrega el primero a mano.</p>
          )}
        </section>
        <aside className="rail" aria-label="Habilidades, estudios y contacto">
          <SkillsCard skills={p.skills} />
          <EducationCard education={p.education} />
          <ContactCard key={JSON.stringify(p.contact)} contact={p.contact} />
          {!empty && <ImportCard onSaved={setImported} />}
        </aside>
      </div>
    </>
  );
}

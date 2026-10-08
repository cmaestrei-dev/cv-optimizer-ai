import { useQuery } from "@tanstack/react-query";
import { useState } from "react";

import { get, type S } from "../api/client";
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

  return (
    <>
      <div className="page-head">
        <h1>Tu perfil</h1>
        <p>Todo lo que hiciste, con tus palabras y tus cifras. De aquí sale cada CV: nunca se inventa nada.</p>
      </div>
      {imported && (
        <Notice kind="ok"><p>{imported} Ahora completa tus logros con «Completar con IA»: mientras más cifras, mejor el CV.</p></Notice>
      )}
      {empty && <LinkLegacyCard />}
      {empty && <ImportCard prominent onSaved={setImported} />}
      {!empty && (
        <div className="notice info">
          <p>
            <b>{p.achievements_with_numbers} de {p.achievements_total}</b> logros tienen cifras.
            {p.achievements_total > 0 && p.achievements_with_numbers / p.achievements_total < 0.5 &&
              " Usa «Completar con IA» en cada cargo: los logros con cifras pesan más en el CV."}
          </p>
        </div>
      )}

      <section className="stack" style={{ marginBottom: 16 }}>
        <div className="row spread">
          <h2>Experiencia</h2>
          {!adding && <button className="small" onClick={() => setAdding(true)}>Agregar cargo</button>}
        </div>
        {adding && (
          <div className="card">
            <ExperienceForm onDone={(np) => { save(np); setAdding(false); }} onCancel={() => setAdding(false)} />
          </div>
        )}
        {p.experiences.map((e) => <ExperienceCard key={e.id} experience={e} />)}
      </section>

      <SkillsCard skills={p.skills} />
      <EducationCard education={p.education} />
      <ContactCard key={JSON.stringify(p.contact)} contact={p.contact} />
      {!empty && <ImportCard onSaved={setImported} />}
    </>
  );
}

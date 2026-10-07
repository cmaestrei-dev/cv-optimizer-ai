import { useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";

import { put, type S } from "../../api/client";
import { ErrorNotice, Notice } from "../ui";

export function ContactCard({ contact }: { contact: S["ContactOut"] }) {
  const queryClient = useQueryClient();
  const [form, setForm] = useState(contact);
  const [error, setError] = useState<unknown>(null);
  const [saved, setSaved] = useState(false);
  const set = (key: keyof S["ContactOut"]) => (e: { target: { value: string } }) => { setSaved(false); setForm({ ...form, [key]: e.target.value }); };

  async function submit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    try {
      const out = await put<S["ContactOut"]>("/me/contact", form);
      setForm(out);
      setSaved(true);
      queryClient.invalidateQueries({ queryKey: ["profile"] });
    } catch (err) {
      setError(err);
    }
  }

  return (
    <form className="card stack" onSubmit={submit}>
      <h2>Datos de contacto</h2>
      <p className="muted">Van en el encabezado de tu CV.</p>
      <div className="grid-2">
        <label>Nombre completo<input type="text" value={form.full_name} onChange={set("full_name")} autoComplete="name" /></label>
        <label>Correo<input type="email" value={form.email} onChange={set("email")} autoComplete="email" /></label>
        <label>Teléfono<input type="tel" value={form.phone} onChange={set("phone")} autoComplete="tel" /></label>
        <label>LinkedIn<input type="text" inputMode="url" value={form.linkedin_url} onChange={set("linkedin_url")} placeholder="www.linkedin.com/in/tu-perfil" /></label>
      </div>
      <ErrorNotice error={error} />
      {saved && <Notice kind="ok"><p>Guardado.</p></Notice>}
      <div><button className="primary small">Guardar contacto</button></div>
    </form>
  );
}

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";

import { post, type S } from "../../api/client";
import { ErrorNotice } from "../ui";

/** Trae el perfil que la persona usaba en la versión anterior (Streamlit), con su usuario y contraseña. */
export function LinkLegacyCard() {
  const queryClient = useQueryClient();
  const [form, setForm] = useState({ username: "", password: "" });
  const link = useMutation({
    mutationFn: () => post<S["MeOut"]>("/me/link-legacy", form),
    onSuccess: () => queryClient.invalidateQueries(), // ahora la cuenta es el perfil anterior: todo cambia
  });
  const submit = (e: FormEvent) => { e.preventDefault(); link.mutate(); };
  return (
    <details className="card">
      <summary><b>¿Ya usabas CV Optimizer?</b> Trae tu perfil de la versión anterior</summary>
      <form className="stack" style={{ marginTop: 12 }} onSubmit={submit}>
        <p className="muted">
          Usa el nombre de perfil y la contraseña con que entrabas antes. Tus experiencias, CV y postulaciones pasan
          a esta cuenta. Si tu perfil no tenía contraseña, ponle una en la versión anterior («Editar perfil») y vuelve aquí.
        </p>
        <div className="grid-2">
          <label>Nombre de perfil<input type="text" value={form.username} autoComplete="username" required
            onChange={(e) => setForm({ ...form, username: e.target.value })} /></label>
          <label>Contraseña<input type="password" value={form.password} autoComplete="current-password" required
            onChange={(e) => setForm({ ...form, password: e.target.value })} /></label>
        </div>
        <ErrorNotice error={link.error} />
        <div><button className="primary" disabled={link.isPending || !form.username || !form.password}>
          {link.isPending ? "Trayendo…" : "Traer mi perfil"}
        </button></div>
      </form>
    </details>
  );
}

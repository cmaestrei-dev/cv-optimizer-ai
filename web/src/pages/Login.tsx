import { useState, type FormEvent } from "react";

import { useAuth } from "../auth/auth";
import { ErrorNotice } from "../components/ui";

export function Login() {
  const { signIn } = useAuth();
  const [name, setName] = useState("");
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (!name.trim()) return;
    setBusy(true);
    setError(null);
    try {
      await signIn(name.trim());
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="main" style={{ maxWidth: 440, paddingTop: "12vh" }}>
      <h1>CV Optimizer</h1>
      <p className="muted">Tu CV a la medida de cada vacante, sin inventar nada. Tú decides y tú envías.</p>
      <form className="card stack" onSubmit={submit}>
        <label>
          Tu nombre
          <input type="text" value={name} onChange={(e) => setName(e.target.value)} autoComplete="name" autoFocus />
        </label>
        <ErrorNotice error={error} />
        <button className="primary" disabled={busy || !name.trim()}>{busy ? "Entrando…" : "Entrar"}</button>
        <small className="faint">Versión de prueba: el inicio con Google o correo llega en la siguiente fase.</small>
      </form>
    </main>
  );
}

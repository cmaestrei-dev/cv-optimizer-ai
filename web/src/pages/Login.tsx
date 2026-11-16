import { SignIn } from "@clerk/react";
import { useState, type FormEvent } from "react";

import { useAuth } from "../auth/auth";
import { ErrorNotice } from "../components/ui";

function DevLogin() {
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
    <form className="panel stack" onSubmit={submit}>
      <label>
        Tu nombre
        <input type="text" value={name} onChange={(e) => setName(e.target.value)} autoComplete="name" autoFocus />
      </label>
      <ErrorNotice error={error} />
      <button className="primary" disabled={busy || !name.trim()}>{busy ? "Entrando…" : "Entrar"}</button>
      <small className="faint">Modo de desarrollo: entrada solo por nombre.</small>
    </form>
  );
}

export function Login() {
  const { mode } = useAuth();
  return (
    <div className="gate">
      <header className="band"><span className="brand"><span className="brand-mark" aria-hidden="true">CV</span>Optimizer</span></header>
      <main className="gate-main">
        <h1>Cada vacante, en su puesto</h1>
        <p>Tu CV a la medida de cada vacante, armado solo con lo que de verdad hiciste. Tú decides cuáles van.</p>
        {mode === "clerk" ? <SignIn routing="hash" /> : <DevLogin />}
      </main>
    </div>
  );
}

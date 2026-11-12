import { useState } from "react";
import type { FormEvent } from "react";
import { ArrowRight, BookOpen, LockKeyhole } from "lucide-react";
import { useAuth } from "../auth";
import { errorMessage } from "../api/client";
import { Alert } from "../components/common";

export function Login() {
    const { signIn, notice } = useAuth();
    const [busy, setBusy] = useState(false);
    const [error, setError] = useState("");
    async function submit(event: FormEvent<HTMLFormElement>) {
        event.preventDefault();
        const form = event.currentTarget;
        const data = new FormData(form);
        setBusy(true);
        setError("");
        try {
            await signIn(
                String(data.get("username")),
                String(data.get("password")),
            );
            form.reset();
        } catch (failure) {
            setError(errorMessage(failure));
        } finally {
            setBusy(false);
        }
    }
    return (
        <main className="login-layout">
            <section className="login-story" aria-label="Biblioteca documental">
                <div className="brand">
                    <span className="brand-symbol" aria-hidden="true">
                        a.
                    </span>
                    <div>
                        Archivo<span>Biblioteca documental</span>
                    </div>
                </div>
                <div className="story-main">
                    <span className="eyebrow">MEMORIA QUE PERMANECE</span>
                    <h1>
                        Un lugar para cuidar
                        <br />
                        lo que importa.
                    </h1>
                    <p>
                        Documentos, personas e historia.
                        <br />
                        Un espacio de trabajo compartido.
                    </p>
                    <div className="paper-stack" aria-hidden="true">
                        <div className="paper back" />
                        <div className="paper middle" />
                        <div className="paper front">
                            <BookOpen size={35} strokeWidth={1.2} />
                            <span />
                            <span />
                            <span />
                            <i />
                        </div>
                    </div>
                </div>
                <span className="story-footer">
                    Organizar. Comprender. Preservar.
                </span>
            </section>
            <section className="login-panel">
                <div className="login-form-wrap">
                    <span className="section-label">
                        BIENVENIDO A TU ESPACIO
                    </span>
                    <h2>Inicia sesión</h2>
                    <p>Accede con tu cuenta de la biblioteca.</p>
                    {notice && <Alert success>{notice}</Alert>}
                    {error && <Alert>{error}</Alert>}
                    <form
                        onSubmit={(event) => void submit(event)}
                        aria-label="Iniciar sesión"
                    >
                        <label className="field">
                            Usuario
                            <input
                                name="username"
                                autoComplete="username"
                                maxLength={64}
                                required
                                autoFocus
                                disabled={busy}
                            />
                        </label>
                        <label className="field">
                            Contraseña
                            <input
                                name="password"
                                type="password"
                                autoComplete="current-password"
                                maxLength={128}
                                required
                                disabled={busy}
                            />
                        </label>
                        <button
                            className="button primary full-width"
                            disabled={busy}
                            type="submit"
                        >
                            {busy
                                ? "Validando acceso…"
                                : "Entrar a mi biblioteca"}
                            <ArrowRight size={17} aria-hidden="true" />
                        </button>
                    </form>
                    <p className="login-help">
                        Si necesitas una cuenta o ayuda para acceder, contacta
                        al administrador de la biblioteca.
                    </p>
                    <div className="secure-note">
                        <LockKeyhole size={14} aria-hidden="true" />
                        Acceso privado
                    </div>
                </div>
            </section>
        </main>
    );
}

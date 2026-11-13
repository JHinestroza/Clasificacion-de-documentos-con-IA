import { useState } from "react";
import type { FormEvent } from "react";
import { KeyRound } from "lucide-react";
import { useAuth } from "../auth";
import { errorMessage } from "../api/client";
import { permissionLabels } from "../api/models";
import { Alert, date, PageHeading } from "../components/common";

export function AccountPage() {
    const { api, user, clear } = useAuth();
    const [busy, setBusy] = useState(false);
    const [error, setError] = useState("");
    async function submit(event: FormEvent<HTMLFormElement>) {
        event.preventDefault();
        const form = event.currentTarget;
        const data = new FormData(form);
        if (data.get("new") !== data.get("confirm")) {
            setError("Las contraseñas nuevas no coinciden.");
            return;
        }
        setBusy(true);
        setError("");
        try {
            await api.password(
                String(data.get("current")),
                String(data.get("new")),
            );
            form.reset();
            clear("Contraseña actualizada. Inicia sesión de nuevo.");
        } catch (failure) {
            setError(errorMessage(failure));
        } finally {
            setBusy(false);
        }
    }
    if (!user) return null;
    return (
        <>
            <PageHeading
                eyebrow="SEGURIDAD PERSONAL"
                title="Mi cuenta"
                description="Tu identidad y tus opciones de acceso."
            />
            <div className="account-grid">
                <section className="surface section-content">
                    <h2>Datos de acceso</h2>
                    <dl className="account-details">
                        <div>
                            <dt>Usuario</dt>
                            <dd>{user.username}</dd>
                        </div>
                        <div>
                            <dt>Tipo de cuenta</dt>
                            <dd>
                                {user.is_superuser ? "Superusuario" : "Usuario"}
                            </dd>
                        </div>
                        <div>
                            <dt>Fecha de creación</dt>
                            <dd>{date(user.created_at)}</dd>
                        </div>
                        <div>
                            <dt>Identificador de cuenta</dt>
                            <dd className="identifier">{user.id}</dd>
                        </div>
                    </dl>
                    <h3>Acciones autorizadas</h3>
                    {user.is_superuser ? (
                        <p>Tu cuenta puede administrar usuarios y permisos.</p>
                    ) : user.permissions.length ? (
                        <ul className="permission-summary">
                            {user.permissions.map((code) => (
                                <li key={code}>
                                    {permissionLabels[code] ?? code}
                                </li>
                            ))}
                        </ul>
                    ) : (
                        <p>
                            Tu cuenta no tiene permisos adicionales asignados.
                        </p>
                    )}
                </section>
                <section className="surface section-content">
                    <div className="panel-heading">
                        <KeyRound size={21} aria-hidden="true" />
                        <h2>Cambiar contraseña</h2>
                    </div>
                    <p>Al guardar se cerrarán todas tus sesiones.</p>
                    {error && <Alert>{error}</Alert>}
                    <form onSubmit={(event) => void submit(event)}>
                        <fieldset disabled={busy}>
                            <label className="field">
                                Contraseña actual
                                <input
                                    name="current"
                                    type="password"
                                    autoComplete="current-password"
                                    maxLength={128}
                                    required
                                />
                            </label>
                            <div className="field">
                                <label htmlFor="new-password">
                                    Nueva contraseña
                                </label>
                                <input
                                    id="new-password"
                                    name="new"
                                    type="password"
                                    autoComplete="new-password"
                                    minLength={16}
                                    maxLength={128}
                                    required
                                    aria-describedby="new-password-help"
                                />
                                <small id="new-password-help">
                                    De 16 a 128 caracteres en una sola línea.
                                </small>
                            </div>
                            <label className="field">
                                Repite la nueva contraseña
                                <input
                                    name="confirm"
                                    type="password"
                                    autoComplete="new-password"
                                    minLength={16}
                                    maxLength={128}
                                    required
                                />
                            </label>
                        </fieldset>
                        <button
                            className="button primary"
                            type="submit"
                            disabled={busy}
                        >
                            {busy ? "Guardando…" : "Guardar contraseña"}
                        </button>
                    </form>
                </section>
            </div>
        </>
    );
}

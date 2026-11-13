import { useCallback, useState } from "react";
import type { FormEvent } from "react";
import {
    KeyRound,
    Plus,
    RefreshCw,
    UserRoundCheck,
    UserRoundX,
} from "lucide-react";
import type { User } from "../api/models";
import { permissionLabels } from "../api/models";
import { errorMessage } from "../api/client";
import { useAuth } from "../auth";
import { useResource } from "../hooks/useResource";
import {
    Alert,
    Busy,
    date,
    Modal,
    PageHeading,
    Pagination,
} from "../components/common";

function CreateUser({
    onClose,
    onDone,
}: {
    onClose: () => void;
    onDone: () => void;
}) {
    const { api } = useAuth();
    const [busy, setBusy] = useState(false);
    const [error, setError] = useState("");
    const [admin, setAdmin] = useState(false);
    async function submit(event: FormEvent<HTMLFormElement>) {
        event.preventDefault();
        const form = event.currentTarget;
        const data = new FormData(form);
        setBusy(true);
        setError("");
        try {
            await api.createUser(
                String(data.get("username")),
                String(data.get("password")),
                admin,
            );
            form.reset();
            onDone();
        } catch (failure) {
            setError(errorMessage(failure));
        } finally {
            setBusy(false);
        }
    }
    return (
        <Modal title="Crear una cuenta" onClose={onClose} busy={busy}>
            <p className="modal-description">
                La cuenta comenzará sin permisos adicionales. Podrás asignarlos
                después.
            </p>
            {error && <Alert>{error}</Alert>}
            <form onSubmit={(event) => void submit(event)}>
                <fieldset disabled={busy}>
                    <div className="field">
                        <label htmlFor="create-username">Usuario</label>
                        <input
                            id="create-username"
                            name="username"
                            autoComplete="off"
                            pattern="(?:[A-Za-z0-9_.]|-){3,64}"
                            minLength={3}
                            maxLength={64}
                            required
                            autoFocus
                            aria-describedby="create-username-help"
                        />
                        <small id="create-username-help">
                            De 3 a 64 letras ASCII, números, puntos, guiones o
                            subrayados.
                        </small>
                    </div>
                    <div className="field">
                        <label htmlFor="create-password">
                            Contraseña inicial
                        </label>
                        <input
                            id="create-password"
                            name="password"
                            type="password"
                            autoComplete="new-password"
                            minLength={16}
                            maxLength={128}
                            required
                            aria-describedby="create-password-help"
                        />
                        <small id="create-password-help">
                            Entre 16 y 128 caracteres en una sola línea.
                        </small>
                    </div>
                    <label className="check-field">
                        <input
                            type="checkbox"
                            checked={admin}
                            onChange={(event) => setAdmin(event.target.checked)}
                        />
                        <span>
                            Dar acceso de superusuario
                            <small>
                                Podrá administrar todas las cuentas y sus
                                permisos.
                            </small>
                        </span>
                    </label>
                </fieldset>
                <div className="form-actions">
                    <button
                        type="button"
                        className="button"
                        onClick={onClose}
                        disabled={busy}
                    >
                        Cancelar
                    </button>
                    <button
                        type="submit"
                        className="button primary"
                        disabled={busy}
                    >
                        {busy ? "Creando…" : "Crear cuenta"}
                    </button>
                </div>
            </form>
        </Modal>
    );
}
function Permissions({
    target,
    onClose,
    onDone,
}: {
    target: User;
    onClose: () => void;
    onDone: () => void;
}) {
    const { api } = useAuth();
    const [selected, setSelected] = useState(new Set(target.permissions));
    const [busy, setBusy] = useState(false);
    const [error, setError] = useState("");
    const load = useCallback(
        (signal: AbortSignal) => api.permissions(signal),
        [api],
    );
    const catalog = useResource(load);
    const changed =
        [...selected].sort().join("|") !==
        [...target.permissions].sort().join("|");
    async function submit(event: FormEvent<HTMLFormElement>) {
        event.preventDefault();
        const data = new FormData(event.currentTarget);
        setBusy(true);
        setError("");
        try {
            await api.grant(
                target.id,
                [...selected].sort(),
                String(data.get("reason")).trim(),
            );
            onDone();
        } catch (failure) {
            setError(errorMessage(failure));
        } finally {
            setBusy(false);
        }
    }
    return (
        <Modal
            title={`Permisos de ${target.username}`}
            onClose={onClose}
            busy={busy}
        >
            <p className="modal-description">
                Selecciona las acciones autorizadas. Los cambios cerrarán las
                sesiones de esta cuenta.
            </p>
            {error && <Alert>{error}</Alert>}
            {catalog.loading ? (
                <Busy />
            ) : catalog.error ? (
                <Alert>{catalog.error}</Alert>
            ) : (
                <form onSubmit={(event) => void submit(event)}>
                    <fieldset disabled={busy}>
                        <div className="permission-list">
                            {catalog.data?.map((code) => (
                                <label className="check-field" key={code}>
                                    <input
                                        type="checkbox"
                                        checked={selected.has(code)}
                                        onChange={(event) =>
                                            setSelected((previous) => {
                                                const next = new Set(previous);
                                                if (event.target.checked)
                                                    next.add(code);
                                                else next.delete(code);
                                                return next;
                                            })
                                        }
                                    />
                                    <span>
                                        {permissionLabels[code] ?? code}
                                    </span>
                                </label>
                            ))}
                        </div>
                        <p className="field-help">
                            Algunas acciones estarán disponibles cuando se
                            habilite su función. No conceden acceso automático
                            al contenido de un fondo.
                        </p>
                        <label className="field">
                            Motivo del cambio
                            <textarea
                                name="reason"
                                minLength={3}
                                maxLength={500}
                                rows={3}
                                required
                                placeholder="Ej. Cambio de responsabilidades."
                            />
                        </label>
                    </fieldset>
                    <div className="form-actions">
                        <button
                            className="button"
                            type="button"
                            onClick={onClose}
                            disabled={busy}
                        >
                            Cancelar
                        </button>
                        <button
                            className="button primary"
                            type="submit"
                            disabled={busy || !changed}
                        >
                            {busy ? "Guardando…" : "Guardar permisos"}
                        </button>
                    </div>
                </form>
            )}
        </Modal>
    );
}
function Active({
    target,
    onClose,
    onDone,
}: {
    target: User;
    onClose: () => void;
    onDone: () => void;
}) {
    const { api } = useAuth();
    const [busy, setBusy] = useState(false);
    const [error, setError] = useState("");
    const action = target.is_active ? "Desactivar" : "Activar";
    async function submit(event: FormEvent<HTMLFormElement>) {
        event.preventDefault();
        const data = new FormData(event.currentTarget);
        setBusy(true);
        setError("");
        try {
            await api.active(
                target.id,
                !target.is_active,
                String(data.get("reason")).trim(),
            );
            onDone();
        } catch (failure) {
            setError(errorMessage(failure));
        } finally {
            setBusy(false);
        }
    }
    return (
        <Modal
            title={`${action} a ${target.username}`}
            onClose={onClose}
            busy={busy}
        >
            <p className="modal-description">
                {target.is_active
                    ? "Se cerrarán sus sesiones. La cuenta y su historial se conservarán."
                    : "La cuenta podrá volver a iniciar sesión con sus permisos asignados."}
            </p>
            {error && <Alert>{error}</Alert>}
            <form onSubmit={(event) => void submit(event)}>
                <label className="field">
                    Motivo del cambio
                    <textarea
                        name="reason"
                        minLength={3}
                        maxLength={500}
                        rows={3}
                        required
                        autoFocus
                        disabled={busy}
                    />
                </label>
                <div className="form-actions">
                    <button
                        className="button"
                        type="button"
                        disabled={busy}
                        onClick={onClose}
                    >
                        Cancelar
                    </button>
                    <button
                        className={`button ${target.is_active ? "danger" : "primary"}`}
                        type="submit"
                        disabled={busy}
                    >
                        {busy ? "Guardando…" : `${action} cuenta`}
                    </button>
                </div>
            </form>
        </Modal>
    );
}
export function UsersPage() {
    const { api, user } = useAuth();
    const [offset, setOffset] = useState(0);
    const [notice, setNotice] = useState("");
    const [creating, setCreating] = useState(false);
    const [permissions, setPermissions] = useState<User | null>(null);
    const [active, setActive] = useState<User | null>(null);
    const load = useCallback(
        (signal: AbortSignal) => api.users(offset, signal),
        [api, offset],
    );
    const query = useResource(load);
    function done(message: string) {
        setCreating(false);
        setPermissions(null);
        setActive(null);
        setNotice(message);
        query.refresh();
    }
    return (
        <>
            <PageHeading
                eyebrow="PERSONAS Y ACCESO"
                title="Usuarios de la biblioteca"
                description="Cada persona, con el acceso que necesita."
                action={
                    <button
                        className="button primary"
                        onClick={() => setCreating(true)}
                    >
                        <Plus size={17} aria-hidden="true" />
                        Crear cuenta
                    </button>
                }
            />
            {notice && <Alert success>{notice}</Alert>}
            <section className="surface">
                <div className="section-title">
                    <div>
                        <h2>Cuentas registradas</h2>
                        <p>Activa, desactiva y administra permisos.</p>
                    </div>
                    <button
                        className="button"
                        disabled={query.loading}
                        onClick={query.refresh}
                    >
                        <RefreshCw size={15} aria-hidden="true" />
                        Actualizar
                    </button>
                </div>
                {query.loading ? (
                    <Busy />
                ) : query.error ? (
                    <div className="section-content">
                        <Alert>{query.error}</Alert>
                    </div>
                ) : (
                    <>
                        <div className="table-wrap">
                            <table>
                                <caption className="sr-only">
                                    Cuentas registradas en esta página
                                </caption>
                                <thead>
                                    <tr>
                                        <th>Usuario</th>
                                        <th>Tipo de cuenta</th>
                                        <th>Estado</th>
                                        <th className="created-column">
                                            Creación
                                        </th>
                                        <th>Acciones</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {query.data?.map((person) => (
                                        <tr key={person.id}>
                                            <td>
                                                <div className="person-cell">
                                                    <span
                                                        className="avatar"
                                                        aria-hidden="true"
                                                    >
                                                        {person.username
                                                            .slice(0, 1)
                                                            .toUpperCase()}
                                                    </span>
                                                    <div>
                                                        <strong>
                                                            {person.username}
                                                        </strong>
                                                        <span className="cell-secondary">
                                                            {person.id ===
                                                            user?.id
                                                                ? "Tu cuenta"
                                                                : `${person.permissions.length} permisos asignados`}
                                                        </span>
                                                    </div>
                                                </div>
                                            </td>
                                            <td>
                                                {person.is_superuser
                                                    ? "Superusuario"
                                                    : "Usuario"}
                                            </td>
                                            <td>
                                                <span
                                                    className={`badge ${person.is_active ? "positive" : "neutral"}`}
                                                >
                                                    {person.is_active
                                                        ? "Activa"
                                                        : "Inactiva"}
                                                </span>
                                            </td>
                                            <td className="date-cell created-column">
                                                {date(person.created_at)}
                                            </td>
                                            <td>
                                                <div className="row-actions">
                                                    <button
                                                        className="button quiet"
                                                        disabled={
                                                            person.is_superuser ||
                                                            person.id ===
                                                                user?.id
                                                        }
                                                        onClick={() =>
                                                            setPermissions(
                                                                person,
                                                            )
                                                        }
                                                        aria-label={`Editar permisos de ${person.username}`}
                                                    >
                                                        <KeyRound
                                                            size={15}
                                                            aria-hidden="true"
                                                        />
                                                        Permisos
                                                    </button>
                                                    <button
                                                        className="icon-button"
                                                        disabled={
                                                            person.id ===
                                                            user?.id
                                                        }
                                                        onClick={() =>
                                                            setActive(person)
                                                        }
                                                        aria-label={`${person.is_active ? "Desactivar" : "Activar"} a ${person.username}`}
                                                    >
                                                        {person.is_active ? (
                                                            <UserRoundX
                                                                size={18}
                                                                aria-hidden="true"
                                                            />
                                                        ) : (
                                                            <UserRoundCheck
                                                                size={18}
                                                                aria-hidden="true"
                                                            />
                                                        )}
                                                    </button>
                                                </div>
                                            </td>
                                        </tr>
                                    ))}
                                </tbody>
                            </table>
                        </div>
                        {query.data?.length === 0 && (
                            <p className="empty">
                                No hay cuentas en esta página.
                            </p>
                        )}
                        <Pagination
                            offset={offset}
                            count={query.data?.length ?? 0}
                            onChange={setOffset}
                        />
                    </>
                )}
            </section>
            {creating && (
                <CreateUser
                    onClose={() => setCreating(false)}
                    onDone={() =>
                        done(
                            "Cuenta creada. Asigna los permisos que corresponden.",
                        )
                    }
                />
            )}
            {permissions && (
                <Permissions
                    target={permissions}
                    onClose={() => setPermissions(null)}
                    onDone={() =>
                        done(
                            "Permisos actualizados. Se cerraron las sesiones de esa cuenta.",
                        )
                    }
                />
            )}
            {active && (
                <Active
                    target={active}
                    onClose={() => setActive(null)}
                    onDone={() => done("Estado de la cuenta actualizado.")}
                />
            )}
        </>
    );
}

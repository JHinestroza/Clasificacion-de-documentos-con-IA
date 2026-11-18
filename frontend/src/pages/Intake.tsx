import { useCallback, useState } from "react";
import type { FormEvent } from "react";
import {
    FolderInput,
    Play,
    Pause,
    Square,
    RefreshCw,
    Plus,
    UsersRound,
    FileText,
} from "lucide-react";
import { useAuth } from "../auth";
import { errorMessage } from "../api/client";
import type { Fonds, IntakeBatch } from "../api/models";
import { useResource } from "../hooks/useResource";
import {
    Alert,
    Busy,
    Modal,
    PageHeading,
    Pagination,
    date,
} from "../components/common";

const labels: Record<string, string> = {
    running: "Ingreso activo",
    pause_requested: "Pausa solicitada",
    paused: "En pausa",
    stop_requested: "Detención solicitada",
    stopped: "Detenido",
    completed: "Ingreso terminado",
    pending: "Pendiente",
    claimed: "Trasladando",
    validating: "Validando",
    finishing: "Trasladando",
    admitted: "Admitido",
    pending_publish: "Pendiente de publicar",
    queued: "En cola",
    failed: "Fallido",
    skipped: "Omitido",
};
const commands: Record<string, string> = {
    pause: "Pausar",
    resume: "Reanudar",
    stop: "Detener",
    "retry-publication": "Reintentar publicación",
};
const actions: Record<string, string> = {
    "batch.started": "Lote iniciado",
    "batch.pause": "Pausa solicitada",
    "batch.resume": "Ingreso reanudado",
    "batch.stop": "Detención solicitada",
    "batch.retry-publication": "Publicación reintentada",
    "file.moved": "Archivo trasladado",
    "file.blocked": "Movimiento requiere revisión",
    "intake.admitted": "Documento admitido",
    "intake.skipped": "Entrega omitida",
    "intake.failed": "Ingreso fallido",
    "intake.warning": "Advertencia de contenido repetido",
    "publication.confirmed": "Publicación confirmada",
    "batch.access_revoked": "Ingreso pausado por pérdida de acceso",
};

function CreateFonds({ close, done }: { close: () => void; done: () => void }) {
    const { api } = useAuth();
    const [busy, setBusy] = useState(false),
        [error, setError] = useState("");
    async function submit(event: FormEvent<HTMLFormElement>) {
        event.preventDefault();
        const data = new FormData(event.currentTarget);
        setBusy(true);
        setError("");
        try {
            await api.createFonds(
                String(data.get("name")),
                String(data.get("key")),
            );
            done();
        } catch (e) {
            setError(errorMessage(e));
        } finally {
            setBusy(false);
        }
    }
    return (
        <Modal title="Nuevo fondo documental" onClose={close} busy={busy}>
            <form className="intake-form" onSubmit={(e) => void submit(e)}>
                {error && <Alert>{error}</Alert>}
                <label htmlFor="fonds-name">Nombre del fondo</label>
                <input id="fonds-name" name="name" required maxLength={100} />
                <label htmlFor="fonds-key">Clave de carpeta</label>
                <input
                    id="fonds-key"
                    name="key"
                    required
                    maxLength={64}
                    pattern="[A-Z0-9][A-Z0-9_\-]{0,63}"
                    aria-describedby="fonds-key-help"
                />
                <p id="fonds-key-help" className="field-help">
                    Usa mayúsculas, números, guion o guion bajo. La clave
                    identifica la carpeta y se conservará.
                </p>
                <div className="form-actions">
                    <button
                        className="button"
                        type="button"
                        disabled={busy}
                        onClick={close}
                    >
                        Cancelar
                    </button>
                    <button className="button primary" disabled={busy}>
                        Crear fondo
                    </button>
                </div>
            </form>
        </Modal>
    );
}

function Access({ fonds, close }: { fonds: Fonds; close: () => void }) {
    const { api } = useAuth();
    const [offset, setOffset] = useState(0),
        [selected, setSelected] = useState(""),
        [enabled, setEnabled] = useState(true),
        [busy, setBusy] = useState(false),
        [error, setError] = useState("");
    const users = useResource(
        useCallback(
            (signal: AbortSignal) => api.users(offset, signal),
            [api, offset],
        ),
    );
    const members = useResource(
        useCallback(
            (signal: AbortSignal) => api.fondsMembers(fonds.id, signal),
            [api, fonds.id],
        ),
    );
    async function submit(event: FormEvent<HTMLFormElement>) {
        event.preventDefault();
        const data = new FormData(event.currentTarget);
        setBusy(true);
        setError("");
        try {
            await api.fondsGrant(
                fonds.id,
                selected,
                enabled,
                String(data.get("reason")),
            );
            close();
        } catch (e) {
            setError(errorMessage(e));
        } finally {
            setBusy(false);
        }
    }
    return (
        <Modal title={`Acceso a ${fonds.name}`} onClose={close} busy={busy}>
            {error && <Alert>{error}</Alert>}
            {users.error && <Alert>{users.error}</Alert>}
            {members.error && <Alert>{members.error}</Alert>}
            {users.loading || members.loading ? (
                <Busy />
            ) : (
                <form className="intake-form" onSubmit={(e) => void submit(e)}>
                    <p>
                        El acceso al fondo se combina con los permisos de acción
                        asignados en Usuarios y permisos.
                    </p>
                    <label htmlFor="fonds-user">Cuenta</label>
                    <select
                        id="fonds-user"
                        required
                        value={selected}
                        onChange={(e) => {
                            setSelected(e.target.value);
                            setEnabled(
                                members.data?.includes(e.target.value) ?? false,
                            );
                        }}
                    >
                        <option value="">Selecciona una cuenta</option>
                        {users.data
                            ?.filter((u) => !u.is_superuser)
                            .map((u) => (
                                <option key={u.id} value={u.id}>
                                    {u.username}
                                    {members.data?.includes(u.id)
                                        ? " · con acceso"
                                        : ""}
                                </option>
                            ))}
                    </select>
                    <Pagination
                        offset={offset}
                        count={users.data?.length ?? 0}
                        onChange={(v) => {
                            setOffset(v);
                            setSelected("");
                        }}
                    />
                    <label className="checkbox-label">
                        <input
                            type="checkbox"
                            checked={enabled}
                            onChange={(e) => setEnabled(e.target.checked)}
                        />
                        Permitir acceso a este fondo
                    </label>
                    <label htmlFor="fonds-reason">Motivo</label>
                    <textarea
                        id="fonds-reason"
                        name="reason"
                        required
                        minLength={3}
                        maxLength={500}
                    />
                    <div className="form-actions">
                        <button
                            type="button"
                            className="button"
                            disabled={busy}
                            onClick={close}
                        >
                            Cancelar
                        </button>
                        <button
                            className="button primary"
                            disabled={busy || !selected}
                        >
                            Guardar acceso
                        </button>
                    </div>
                </form>
            )}
        </Modal>
    );
}

function Items({ id, revision }: { id: string; revision: number }) {
    const { api } = useAuth();
    const [offset, setOffset] = useState(0),
        [search, setSearch] = useState(""),
        [state, setState] = useState("");
    const rows = useResource(
        useCallback(
            (signal: AbortSignal) => {
                void revision;
                return api.intakeItems(id, offset, search, state, signal);
            },
            [api, id, offset, search, state, revision],
        ),
    );
    return (
        <>
            <div className="intake-filters">
                <div>
                    <label htmlFor="intake-search">Buscar por nombre</label>
                    <input
                        id="intake-search"
                        type="search"
                        value={search}
                        maxLength={100}
                        placeholder="CAB01"
                        onChange={(e) => {
                            setSearch(e.target.value);
                            setOffset(0);
                        }}
                    />
                </div>
                <div>
                    <label htmlFor="intake-state">Estado</label>
                    <select
                        id="intake-state"
                        value={state}
                        onChange={(e) => {
                            setState(e.target.value);
                            setOffset(0);
                        }}
                    >
                        <option value="">Todos</option>
                        {[
                            "pending",
                            "queued",
                            "pending_publish",
                            "failed",
                            "skipped",
                        ].map((v) => (
                            <option key={v} value={v}>
                                {labels[v]}
                            </option>
                        ))}
                    </select>
                </div>
            </div>
            {rows.loading ? (
                <Busy />
            ) : rows.error ? (
                <Alert>{rows.error}</Alert>
            ) : (
                <>
                    <div className="table-scroll">
                        <table>
                            <thead>
                                <tr>
                                    <th>Documento</th>
                                    <th>Estado</th>
                                    <th>Detalle</th>
                                </tr>
                            </thead>
                            <tbody>
                                {rows.data?.map((row) => (
                                    <tr key={row.id}>
                                        <td>
                                            <strong>{row.original_name}</strong>
                                            <div className="muted">
                                                {row.code ??
                                                    "Código por validar"}
                                                {row.pages
                                                    ? ` · ${row.pages} pág.`
                                                    : ""}
                                                {row.size_bytes
                                                    ? ` · ${(row.size_bytes / 1e6).toFixed(2)} MB`
                                                    : ""}
                                            </div>
                                        </td>
                                        <td>
                                            <span
                                                className={`intake-status ${row.job_state ?? row.state}`}
                                            >
                                                {labels[
                                                    row.job_state ?? row.state
                                                ] ?? row.state}
                                            </span>
                                        </td>
                                        <td>{row.reason_text || "—"}</td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>
                    {rows.data?.length === 0 && (
                        <p className="empty-state">
                            No hay documentos que coincidan con estos filtros.
                        </p>
                    )}
                    <Pagination
                        offset={offset}
                        count={rows.data?.length ?? 0}
                        onChange={setOffset}
                    />
                </>
            )}
        </>
    );
}

function Events({ id, revision }: { id: string; revision: number }) {
    const { api } = useAuth();
    const [offset, setOffset] = useState(0);
    const rows = useResource(
        useCallback(
            (signal: AbortSignal) => {
                void revision;
                return api.intakeEvents(id, offset, signal);
            },
            [api, id, offset, revision],
        ),
    );
    return (
        <section className="intake-history">
            <h3>Historial del lote</h3>
            {rows.loading ? (
                <Busy />
            ) : rows.error ? (
                <Alert>{rows.error}</Alert>
            ) : (
                <>
                    <ol>
                        {rows.data?.map((row) => (
                            <li key={row.id}>
                                <span>{actions[row.action] ?? row.action}</span>
                                <time>{date(row.occurred_at)}</time>
                            </li>
                        ))}
                    </ol>
                    {rows.data?.length === 0 && <p>Todavía no hay eventos.</p>}
                    <Pagination
                        offset={offset}
                        count={rows.data?.length ?? 0}
                        onChange={setOffset}
                    />
                </>
            )}
        </section>
    );
}

function BatchDetail({ id, changed }: { id: string; changed: () => void }) {
    const { api, user } = useAuth();
    const [revision, setRevision] = useState(0),
        [command, setCommand] = useState(""),
        [busy, setBusy] = useState(false),
        [error, setError] = useState("");
    const detail = useResource(
        useCallback(
            (signal: AbortSignal) => {
                void revision;
                return api.batch(id, signal);
            },
            [api, id, revision],
        ),
    );
    const can = (p: string) =>
        !!user && (user.is_superuser || user.permissions.includes(p));
    async function submit(event: FormEvent<HTMLFormElement>) {
        event.preventDefault();
        const data = new FormData(event.currentTarget);
        setBusy(true);
        setError("");
        try {
            await api.batchCommand(id, command, String(data.get("reason")));
            setCommand("");
            setRevision((v) => v + 1);
            changed();
        } catch (e) {
            setError(errorMessage(e));
        } finally {
            setBusy(false);
        }
    }
    const row = detail.data;
    return (
        <section className="panel intake-detail">
            <div className="section-heading">
                <div>
                    <p className="eyebrow">LOTE SELECCIONADO</p>
                    <h2>{row ? labels[row.state] : "Estado del lote"}</h2>
                    <p className="muted">
                        {row ? date(row.created_at) : ""} · {id.slice(0, 8)}
                    </p>
                </div>
                <button className="button" onClick={changed}>
                    <RefreshCw size={16} aria-hidden="true" />
                    Actualizar estado
                </button>
            </div>
            {detail.loading ? (
                <Busy />
            ) : detail.error ? (
                <Alert>{detail.error}</Alert>
            ) : (
                row && (
                    <>
                        <div className="intake-counts">
                            {[
                                ["queued", "En cola"],
                                ["pending_publish", "Pendientes de publicar"],
                                ["pending", "Pendientes de admitir"],
                                ["failed", "Fallidos"],
                                ["skipped", "Omitidos"],
                            ].map(([key, label]) => (
                                <div key={key}>
                                    <strong>{row.counts[key] ?? 0}</strong>
                                    <span>{label}</span>
                                </div>
                            ))}
                        </div>
                        <div className="intake-controls">
                            {can("processing.pause") &&
                                row.state === "running" && (
                                    <button
                                        className="button"
                                        onClick={() => setCommand("pause")}
                                    >
                                        <Pause size={16} aria-hidden="true" />
                                        Pausar
                                    </button>
                                )}
                            {can("processing.start") &&
                                row.state === "paused" && (
                                    <button
                                        className="button primary"
                                        onClick={() => setCommand("resume")}
                                    >
                                        <Play size={16} aria-hidden="true" />
                                        Reanudar
                                    </button>
                                )}
                            {can("processing.stop") &&
                                [
                                    "running",
                                    "paused",
                                    "pause_requested",
                                ].includes(row.state) && (
                                    <button
                                        className="button"
                                        onClick={() => setCommand("stop")}
                                    >
                                        <Square size={16} aria-hidden="true" />
                                        Detener
                                    </button>
                                )}
                            {can("processing.start") &&
                                row.blocked_publications > 0 && (
                                    <button
                                        className="button"
                                        onClick={() =>
                                            setCommand("retry-publication")
                                        }
                                    >
                                        Reintentar publicación (
                                        {row.blocked_publications})
                                    </button>
                                )}
                        </div>
                        <p className="field-help">
                            Pausar o detener permite terminar el ingreso
                            iniciado. Los documentos que ya están en cola
                            conservan su trabajo.
                        </p>
                        {(can("documents.read") || can("failed.read")) && (
                            <Items key={id} id={id} revision={revision} />
                        )}
                        {can("audit.read") && (
                            <Events
                                key={"events-" + id}
                                id={id}
                                revision={revision}
                            />
                        )}
                    </>
                )
            )}
            {command && (
                <Modal
                    title={`${commands[command]} lote`}
                    busy={busy}
                    onClose={() => setCommand("")}
                >
                    <form
                        className="intake-form"
                        onSubmit={(e) => void submit(e)}
                    >
                        {error && <Alert>{error}</Alert>}
                        <label htmlFor="batch-reason">Motivo</label>
                        <textarea
                            id="batch-reason"
                            name="reason"
                            required
                            minLength={3}
                            maxLength={500}
                        />
                        <div className="form-actions">
                            <button
                                className="button"
                                type="button"
                                disabled={busy}
                                onClick={() => setCommand("")}
                            >
                                Cancelar
                            </button>
                            <button className="button primary" disabled={busy}>
                                {commands[command]}
                            </button>
                        </div>
                    </form>
                </Modal>
            )}
        </section>
    );
}

function FondsBatches({
    fonds,
    onSelect,
    revision,
}: {
    fonds: Fonds;
    onSelect: (id: string) => void;
    revision: number;
}) {
    const { api } = useAuth();
    const [offset, setOffset] = useState(0);
    const rows = useResource(
        useCallback(
            (signal: AbortSignal) => {
                void revision;
                return api.batches(fonds.id, offset, signal);
            },
            [api, fonds.id, offset, revision],
        ),
    );
    return (
        <section className="panel intake-batches">
            <div className="section-heading">
                <h2>Lotes de {fonds.name}</h2>
                <span className="muted">Selecciona uno para ver su estado</span>
            </div>
            {rows.loading ? (
                <Busy />
            ) : rows.error ? (
                <Alert>{rows.error}</Alert>
            ) : (
                <>
                    {rows.data?.length === 0 ? (
                        <div className="empty-state">
                            <FileText size={28} aria-hidden="true" />
                            <h3>Tu primer lote empieza aquí</h3>
                            <p>
                                Deposita PDF completos en la carpeta de entrada
                                e inicia un lote.
                            </p>
                        </div>
                    ) : (
                        <ul className="intake-batch-list">
                            {rows.data?.map((row) => (
                                <li key={row.id}>
                                    <button onClick={() => onSelect(row.id)}>
                                        <span>
                                            <strong>
                                                {date(row.created_at)}
                                            </strong>
                                            <small>
                                                {row.total} documentos ·{" "}
                                                {row.id.slice(0, 8)}
                                            </small>
                                        </span>
                                        <span
                                            className={`intake-status ${row.state}`}
                                        >
                                            {labels[row.state] ?? row.state}
                                        </span>
                                    </button>
                                </li>
                            ))}
                        </ul>
                    )}
                    <Pagination
                        offset={offset}
                        count={rows.data?.length ?? 0}
                        onChange={setOffset}
                    />
                </>
            )}
        </section>
    );
}

export function IntakePage() {
    const { api, user } = useAuth();
    const [selected, setSelected] = useState(""),
        [batchId, setBatchId] = useState(""),
        [batchFonds, setBatchFonds] = useState(""),
        [revision, setRevision] = useState(0),
        [modal, setModal] = useState(""),
        [busy, setBusy] = useState(false),
        [error, setError] = useState("");
    const fonds = useResource(
        useCallback((signal: AbortSignal) => api.fonds(signal), [api]),
    );
    const active =
        fonds.data?.find((f) => f.id === selected) ?? fonds.data?.[0];
    const canStart =
        !!user &&
        (user.is_superuser || user.permissions.includes("processing.start"));
    async function start() {
        if (!active) return;
        setBusy(true);
        setError("");
        try {
            const batch: IntakeBatch = await api.startBatch(active.id);
            setBatchId(batch.id);
            setBatchFonds(active.id);
            setRevision((v) => v + 1);
        } catch (e) {
            setError(errorMessage(e));
        } finally {
            setBusy(false);
        }
    }
    return (
        <>
            <PageHeading
                eyebrow="INGRESO POR CARPETAS"
                title="Ingreso de documentos"
                description="Prepara tus PDF, inicia un lote y consulta el recorrido de cada entrega."
                action={
                    <button
                        className="button"
                        onClick={() => {
                            fonds.refresh();
                            setRevision((v) => v + 1);
                        }}
                    >
                        <RefreshCw size={16} aria-hidden="true" />
                        Actualizar
                    </button>
                }
            />
            {error && <Alert>{error}</Alert>}
            {fonds.loading ? (
                <Busy label="Consultando tus fondos…" />
            ) : fonds.error ? (
                <Alert>{fonds.error}</Alert>
            ) : (
                <>
                    <section className="panel intake-inbox">
                        <div className="intake-fonds-choice">
                            <div>
                                <label htmlFor="intake-fonds">
                                    Fondo documental
                                </label>
                                <select
                                    id="intake-fonds"
                                    value={active?.id ?? ""}
                                    onChange={(e) => {
                                        setSelected(e.target.value);
                                        setBatchId("");
                                    }}
                                >
                                    {fonds.data?.map((f) => (
                                        <option key={f.id} value={f.id}>
                                            {f.name}
                                        </option>
                                    ))}
                                </select>
                            </div>
                            <span className="intake-limit">
                                Hasta 100 MB por PDF
                            </span>
                        </div>
                        {active?.incoming_path && (
                            <div className="intake-path">
                                <FolderInput size={24} aria-hidden="true" />
                                <div>
                                    <strong>Carpeta de entrada</strong>
                                    <code>{active.incoming_path}</code>
                                    <p>
                                        Copia con extensión .part y renombra a
                                        .pdf cuando termine. También puedes usar
                                        el ayudante de depósito de la guía.
                                    </p>
                                </div>
                            </div>
                        )}
                        <div className="intake-controls">
                            {canStart && (
                                <button
                                    className="button primary"
                                    disabled={busy || !active?.active}
                                    onClick={() => void start()}
                                >
                                    <Play size={16} aria-hidden="true" />
                                    {busy ? "Creando lote…" : "Iniciar lote"}
                                </button>
                            )}
                            {user?.is_superuser && (
                                <>
                                    <button
                                        className="button"
                                        onClick={() => setModal("create")}
                                    >
                                        <Plus size={16} aria-hidden="true" />
                                        Nuevo fondo
                                    </button>
                                    {active && (
                                        <button
                                            className="button"
                                            onClick={() => setModal("access")}
                                        >
                                            <UsersRound
                                                size={16}
                                                aria-hidden="true"
                                            />
                                            Accesos al fondo
                                        </button>
                                    )}
                                </>
                            )}
                        </div>
                        {!active && (
                            <p>
                                No tienes fondos disponibles. Solicita acceso al
                                superusuario.
                            </p>
                        )}
                        <p className="field-help">
                            El lote toma los PDF completos que estén en la
                            carpeta al iniciar. Las entregas posteriores quedan
                            para otro lote.
                        </p>
                    </section>
                    <div className="intake-notice">
                        <span>EN ESTA ETAPA</span>
                        <p>
                            Los documentos admitidos quedan en cola. La
                            extracción de texto y los metadatos se habilitarán
                            en las siguientes entregas.
                        </p>
                    </div>
                    {active && (
                        <FondsBatches
                            key={active.id}
                            fonds={active}
                            revision={revision}
                            onSelect={(id) => {
                                setBatchId(id);
                                setBatchFonds(active.id);
                            }}
                        />
                    )}
                    {batchId && batchFonds === active?.id && (
                        <BatchDetail
                            key={batchId + revision}
                            id={batchId}
                            changed={() => setRevision((v) => v + 1)}
                        />
                    )}
                </>
            )}
            {modal === "create" && (
                <CreateFonds
                    close={() => setModal("")}
                    done={() => {
                        setModal("");
                        fonds.refresh();
                    }}
                />
            )}
            {modal === "access" && active && (
                <Access fonds={active} close={() => setModal("")} />
            )}
        </>
    );
}

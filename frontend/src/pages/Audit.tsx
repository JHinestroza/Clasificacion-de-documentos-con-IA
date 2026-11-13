import { useCallback, useState } from "react";
import { RefreshCw } from "lucide-react";
import { useAuth } from "../auth";
import { actionLabels } from "../api/models";
import { useResource } from "../hooks/useResource";
import {
    Alert,
    Busy,
    date,
    PageHeading,
    Pagination,
} from "../components/common";

export function AuditPage() {
    const { api, user } = useAuth();
    const [offset, setOffset] = useState(0);
    const load = useCallback(
        (signal: AbortSignal) => api.audit(offset, signal),
        [api, offset],
    );
    const query = useResource(load);
    return (
        <>
            <PageHeading
                eyebrow="TRAZABILIDAD"
                title="Actividad de la biblioteca"
                description="Consulta quién actuó, cuándo y con qué resultado."
            />
            <section className="surface">
                <div className="section-title">
                    <div>
                        <h2>Registro de auditoría</h2>
                        <p>Acciones más recientes primero.</p>
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
                                    Eventos de auditoría autorizados
                                </caption>
                                <thead>
                                    <tr>
                                        <th>Fecha</th>
                                        <th>Acción</th>
                                        <th>Actor</th>
                                        <th>Resultado</th>
                                        <th>Detalle</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {query.data?.map((entry) => (
                                        <tr key={entry.id}>
                                            <td className="date-cell">
                                                {date(entry.occurred_at)}
                                            </td>
                                            <td>
                                                <strong>
                                                    {actionLabels[
                                                        entry.action
                                                    ] ?? entry.action}
                                                </strong>
                                            </td>
                                            <td>
                                                <span
                                                    title={
                                                        entry.actor_id ??
                                                        undefined
                                                    }
                                                >
                                                    {entry.actor_id === user?.id
                                                        ? user.username
                                                        : entry.actor_id
                                                          ? `Cuenta ${entry.actor_id.slice(0, 8)}`
                                                          : "Sin autenticar"}
                                                </span>
                                            </td>
                                            <td>
                                                <span
                                                    className={`badge ${entry.outcome === "ok" ? "positive" : entry.outcome === "denied" ? "negative" : "warning"}`}
                                                >
                                                    {entry.outcome === "ok"
                                                        ? "Completado"
                                                        : entry.outcome ===
                                                            "denied"
                                                          ? "Rechazado"
                                                          : "Limitado"}
                                                </span>
                                            </td>
                                            <td className="audit-detail">
                                                {entry.reason ?? "—"}
                                                {entry.resource_id && (
                                                    <span
                                                        className="cell-secondary"
                                                        title={
                                                            entry.resource_id
                                                        }
                                                    >
                                                        Recurso{" "}
                                                        {entry.resource_id.slice(
                                                            0,
                                                            8,
                                                        )}
                                                    </span>
                                                )}
                                            </td>
                                        </tr>
                                    ))}
                                </tbody>
                            </table>
                        </div>
                        {query.data?.length === 0 && (
                            <p className="empty">
                                No hay eventos en esta página.
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
        </>
    );
}

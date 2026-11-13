import { useCallback } from "react";
import {
    ArrowUpRight,
    Database,
    FileClock,
    RefreshCw,
    ShieldCheck,
    Users,
    Workflow,
} from "lucide-react";
import { useAuth } from "../auth";
import { useResource } from "../hooks/useResource";
import { Alert, Busy, PageHeading } from "../components/common";

export function Home() {
    const { api, user } = useAuth();
    const load = useCallback((signal: AbortSignal) => api.ready(signal), [api]);
    const status = useResource(load);
    if (!user) return null;
    return (
        <>
            <PageHeading
                eyebrow="TU ESPACIO DE TRABAJO"
                title={`Bienvenido, ${user.username}.`}
                description="Aquí empieza el cuidado de tu biblioteca documental."
            />
            <section className="welcome-banner">
                <div>
                    <span className="section-label">TU CUENTA</span>
                    <h2>
                        {user.is_superuser
                            ? "Administración de la biblioteca"
                            : "Un espacio según tus permisos"}
                    </h2>
                    <p>
                        {user.is_superuser
                            ? "Administra las cuentas y decide qué puede hacer cada persona."
                            : "Consulta las opciones disponibles para tu cuenta."}
                    </p>
                </div>
                <ShieldCheck size={48} strokeWidth={1.1} aria-hidden="true" />
            </section>
            <div className="quick-links">
                {user.is_superuser && (
                    <a className="quick-link" href="#usuarios">
                        <Users size={23} aria-hidden="true" />
                        <h2>Usuarios y permisos</h2>
                        <p>Gestiona el acceso de tu equipo.</p>
                        <ArrowUpRight
                            className="quick-arrow"
                            size={18}
                            aria-hidden="true"
                        />
                    </a>
                )}
                {(user.is_superuser ||
                    user.permissions.includes("audit.read")) && (
                    <a className="quick-link" href="#auditoria">
                        <FileClock size={23} aria-hidden="true" />
                        <h2>Actividad de la biblioteca</h2>
                        <p>Consulta las acciones registradas.</p>
                        <ArrowUpRight
                            className="quick-arrow"
                            size={18}
                            aria-hidden="true"
                        />
                    </a>
                )}
                <a className="quick-link" href="#cuenta">
                    <ShieldCheck size={23} aria-hidden="true" />
                    <h2>Seguridad de mi cuenta</h2>
                    <p>Consulta tu acceso y cambia tu contraseña.</p>
                    <ArrowUpRight
                        className="quick-arrow"
                        size={18}
                        aria-hidden="true"
                    />
                </a>
            </div>
            <section className="surface service-status">
                <div className="section-title">
                    <div>
                        <h2>Estado de los servicios</h2>
                        <p>Disponibilidad consultada en este momento.</p>
                    </div>
                    <button
                        className="button"
                        disabled={status.loading}
                        onClick={status.refresh}
                    >
                        <RefreshCw size={15} aria-hidden="true" />
                        Actualizar
                    </button>
                </div>
                {status.loading ? (
                    <Busy />
                ) : status.error ? (
                    <div className="section-content">
                        <Alert>{status.error}</Alert>
                    </div>
                ) : (
                    status.data && (
                        <div className="service-grid">
                            {[
                                {
                                    key: "database" as const,
                                    label: "Base de datos",
                                    icon: Database,
                                },
                                {
                                    key: "broker" as const,
                                    label: "Cola de trabajo",
                                    icon: Workflow,
                                },
                            ].map(({ key, label, icon: Icon }) => (
                                <div className="service" key={key}>
                                    <Icon size={22} aria-hidden="true" />
                                    <span>{label}</span>
                                    <span
                                        className={`badge ${status.data?.checks[key] === "ok" ? "positive" : "negative"}`}
                                    >
                                        {status.data?.checks[key] === "ok"
                                            ? "Disponible"
                                            : "No disponible"}
                                    </span>
                                </div>
                            ))}
                        </div>
                    )
                )}
            </section>
        </>
    );
}

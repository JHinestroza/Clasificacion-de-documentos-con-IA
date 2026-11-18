/** Public identity contracts. Passwords and raw session identifiers are never response fields. */
export interface User {
    id: string;
    username: string;
    is_active: boolean;
    is_superuser: boolean;
    permissions: string[];
    created_at: string;
}
export interface AuditEntry {
    id: string;
    actor_id: string | null;
    action: string;
    resource_id: string | null;
    outcome: "ok" | "denied" | "throttled";
    occurred_at: string;
    reason: string | null;
}
export interface Readiness {
    status: "ready" | "not_ready";
    checks: { database: "ok" | "unavailable"; broker: "ok" | "unavailable" };
}
export const permissionLabels: Record<string, string> = {
    "documents.read": "Consultar documentos",
    "documents.content.read": "Ver contenido documental",
    "dashboard.read": "Consultar dashboard",
    "reports.read": "Consultar reportes",
    "processing.start": "Iniciar ingreso y procesamiento",
    "processing.pause": "Pausar ingreso y procesamiento",
    "processing.stop": "Detener ingreso y procesamiento",
    "failed.read": "Consultar fallidos",
    "failed.retry": "Reprocesar fallidos",
    "failed.dismiss": "Retirar fallidos del reencolamiento",
    "audit.read": "Consultar auditoría",
};
export const actionLabels: Record<string, string> = {
    "auth.login": "Inicio de sesión",
    "auth.logout": "Cierre de sesión",
    "auth.me": "Consulta de sesión",
    "auth.password": "Cambio de contraseña",
    "users.create": "Creación de cuenta",
    "users.bootstrap": "Inicialización de administración",
    "users.list": "Consulta de cuentas",
    "users.active": "Cambio de estado de cuenta",
    "users.permissions": "Cambio de permisos",
    "permissions.list": "Consulta de permisos",
    "audit.list": "Consulta de auditoría",
    "security.csrf": "Validación de solicitud",
    "security.validation": "Validación de datos",
};

export interface Fonds {
    id: string;
    name: string;
    storage_key: string;
    active: boolean;
    incoming_path: string | null;
}
export interface IntakeBatch {
    id: string;
    fonds_id: string;
    state: string;
    created_at: string;
    total: number;
    counts: Record<string, number>;
    blocked_publications: number;
}
export interface IntakeItem {
    id: string;
    original_name: string;
    code: string | null;
    state: string;
    job_state: string | null;
    reason_text: string;
    size_bytes: number | null;
    pages: number | null;
}
export interface IntakeEvent {
    id: string;
    item_id: string | null;
    actor_id: string | null;
    action: string;
    reason: string | null;
    occurred_at: string;
}

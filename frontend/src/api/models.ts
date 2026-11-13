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

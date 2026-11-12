import type { AuditEntry, Readiness, User } from "./models";

const messages: Record<number, string> = {
    0: "No pudimos conectar. Revisa la conexión e inténtalo de nuevo.",
    400: "Revisa los datos de la operación.",
    401: "No se pudo validar el acceso. Comprueba tus credenciales o inicia sesión de nuevo.",
    403: "Tu cuenta no tiene permiso para esta acción o la solicitud caducó.",
    409: "La operación entra en conflicto con el estado actual. Revisa la cuenta y vuelve a intentarlo.",
    422: "Revisa los campos indicados e inténtalo de nuevo.",
    429: "Se alcanzó el límite temporal de intentos. Espera antes de volver a intentarlo.",
    503: "El servicio no está disponible en este momento. Inténtalo más tarde.",
};
export class ApiError extends Error {
    constructor(public readonly status: number) {
        super(messages[status] ?? "No pudimos completar la solicitud.");
    }
}
function object(value: unknown): Record<string, unknown> {
    if (!value || typeof value !== "object" || Array.isArray(value))
        throw new ApiError(502);
    return value as Record<string, unknown>;
}
function text(value: unknown): string {
    if (typeof value !== "string") throw new ApiError(502);
    return value;
}
function strings(value: unknown): string[] {
    if (
        !Array.isArray(value) ||
        !value.every((item) => typeof item === "string")
    )
        throw new ApiError(502);
    return value as string[];
}
function user(value: unknown): User {
    const row = object(value);
    if (
        typeof row.is_active !== "boolean" ||
        typeof row.is_superuser !== "boolean"
    )
        throw new ApiError(502);
    return {
        id: text(row.id),
        username: text(row.username),
        is_active: row.is_active,
        is_superuser: row.is_superuser,
        permissions: strings(row.permissions),
        created_at: text(row.created_at),
    };
}
function entries(value: unknown): unknown[] {
    if (!Array.isArray(value)) throw new ApiError(502);
    return value;
}
function csrf(value: unknown): string {
    const token = text(object(value).csrf_token);
    if (!/^[A-Za-z0-9_-]{32,128}$/.test(token)) throw new ApiError(502);
    return token;
}
function audit(value: unknown): AuditEntry {
    const row = object(value);
    if (!["ok", "denied", "throttled"].includes(text(row.outcome)))
        throw new ApiError(502);
    return {
        id: text(row.id),
        actor_id: row.actor_id === null ? null : text(row.actor_id),
        action: text(row.action),
        resource_id: row.resource_id === null ? null : text(row.resource_id),
        outcome: row.outcome as AuditEntry["outcome"],
        occurred_at: text(row.occurred_at),
        reason: row.reason === null ? null : text(row.reason),
    };
}

/** Same-origin, verified HTTPS only. The browser keeps HttpOnly cookies; no token storage. */
export class IdentityApi {
    constructor(private readonly unauthorized: () => void = () => {}) {}
    private async request(
        path: string,
        method = "GET",
        body?: unknown,
        signal?: AbortSignal,
    ): Promise<unknown> {
        if (
            window.location.protocol !== "https:" ||
            !path.startsWith("/") ||
            path.startsWith("//")
        )
            throw new ApiError(0);
        const headers: Record<string, string> = { Accept: "application/json" };
        const options: RequestInit = {
            method,
            credentials: "same-origin",
            cache: "no-store",
            redirect: "error",
            headers,
        };
        const timeout = AbortSignal.timeout(12000);
        options.signal = signal ? AbortSignal.any([signal, timeout]) : timeout;
        if (method !== "GET") {
            headers["X-CSRF-Token"] = csrf(
                await this.request("/auth/csrf", "GET", undefined, signal),
            );
            if (body !== undefined) {
                headers["Content-Type"] = "application/json";
                options.body = JSON.stringify(body);
            }
        }
        let response: Response;
        try {
            response = await fetch("/api/v1" + path, options);
        } catch (error) {
            if (signal?.aborted) throw error;
            throw new ApiError(0);
        }
        if (signal?.aborted)
            throw new DOMException("Request cancelled", "AbortError");
        if (response.status === 401) this.unauthorized();
        if (!response.ok && !(path === "/ready" && response.status === 503))
            throw new ApiError(response.status);
        try {
            return (await response.json()) as unknown;
        } catch {
            throw new ApiError(502);
        }
    }
    async me(signal?: AbortSignal): Promise<User> {
        return user(await this.request("/auth/me", "GET", undefined, signal));
    }
    async login(username: string, password: string): Promise<User> {
        const result = object(
            await this.request("/auth/login", "POST", { username, password }),
        );
        csrf(result);
        return user(result.user);
    }
    async logout(): Promise<void> {
        await this.request("/auth/logout", "POST");
    }
    async password(
        current_password: string,
        new_password: string,
    ): Promise<void> {
        await this.request("/auth/password", "POST", {
            current_password,
            new_password,
        });
    }
    async users(offset = 0, signal?: AbortSignal): Promise<User[]> {
        return entries(
            await this.request(
                `/users?limit=20&offset=${offset}`,
                "GET",
                undefined,
                signal,
            ),
        ).map(user);
    }
    async createUser(
        username: string,
        password: string,
        is_superuser: boolean,
    ): Promise<User> {
        return user(
            await this.request("/users", "POST", {
                username,
                password,
                is_superuser,
            }),
        );
    }
    async active(id: string, active: boolean, reason: string): Promise<User> {
        return user(
            await this.request(
                `/users/${encodeURIComponent(id)}/active`,
                "PATCH",
                { active, reason },
            ),
        );
    }
    async permissions(signal?: AbortSignal): Promise<string[]> {
        return strings(
            await this.request("/permissions", "GET", undefined, signal),
        );
    }
    async grant(
        id: string,
        permissions: string[],
        reason: string,
    ): Promise<User> {
        return user(
            await this.request(
                `/users/${encodeURIComponent(id)}/permissions`,
                "PUT",
                { permissions, reason },
            ),
        );
    }
    async audit(offset = 0, signal?: AbortSignal): Promise<AuditEntry[]> {
        return entries(
            await this.request(
                `/audit?limit=20&offset=${offset}`,
                "GET",
                undefined,
                signal,
            ),
        ).map(audit);
    }
    async ready(signal?: AbortSignal): Promise<Readiness> {
        const row = object(
            await this.request("/ready", "GET", undefined, signal),
        );
        const checks = object(row.checks);
        if (
            !["ready", "not_ready"].includes(text(row.status)) ||
            !["ok", "unavailable"].includes(text(checks.database)) ||
            !["ok", "unavailable"].includes(text(checks.broker))
        )
            throw new ApiError(502);
        return row as unknown as Readiness;
    }
}
export function errorMessage(error: unknown): string {
    return error instanceof ApiError
        ? error.message
        : "No pudimos completar la operación. Inténtalo de nuevo.";
}

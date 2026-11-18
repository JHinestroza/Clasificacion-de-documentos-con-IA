import type {
    AuditEntry,
    Readiness,
    User,
    Fonds,
    IntakeBatch,
    IntakeItem,
    IntakeEvent,
} from "./models";

const messages: Record<number, string> = {
    0: "No pudimos conectar. Revisa la conexión e inténtalo de nuevo.",
    400: "Revisa los datos de la operación.",
    401: "No se pudo validar el acceso. Comprueba tus credenciales o inicia sesión de nuevo.",
    403: "Tu cuenta no tiene permiso para esta acción o la solicitud caducó.",
    409: "La operación entra en conflicto con el estado actual. Revisa el estado y vuelve a intentarlo.",
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

function number(value: unknown): number {
    if (typeof value !== "number" || !Number.isFinite(value) || value < 0)
        throw new ApiError(502);
    return value;
}
function fonds(value: unknown): Fonds {
    const r = object(value);
    if (typeof r.active !== "boolean") throw new ApiError(502);
    return {
        id: text(r.id),
        name: text(r.name),
        storage_key: text(r.storage_key),
        active: r.active,
        incoming_path:
            r.incoming_path === null || r.incoming_path === undefined
                ? null
                : text(r.incoming_path),
    };
}
function batch(value: unknown): IntakeBatch {
    const r = object(value),
        counts: Record<string, number> = {};
    if (r.counts !== undefined)
        for (const [key, value] of Object.entries(object(r.counts)))
            counts[key] = number(value);
    return {
        id: text(r.id),
        fonds_id: text(r.fonds_id),
        state: text(r.state),
        created_at: text(r.created_at),
        total:
            r.total === undefined
                ? Object.values(counts).reduce((a, b) => a + b, 0)
                : number(r.total),
        counts,
        blocked_publications:
            r.blocked_publications === undefined
                ? 0
                : number(r.blocked_publications),
    };
}
function item(value: unknown): IntakeItem {
    const r = object(value);
    return {
        id: text(r.id),
        original_name: text(r.original_name),
        code: r.code === null ? null : text(r.code),
        state: text(r.state),
        job_state: r.job_state === null ? null : text(r.job_state),
        reason_text: text(r.reason_text),
        size_bytes: r.size_bytes === null ? null : number(r.size_bytes),
        pages: r.pages === null ? null : number(r.pages),
    };
}
function intakeEvent(value: unknown): IntakeEvent {
    const r = object(value);
    return {
        id: text(r.id),
        item_id: r.item_id === null ? null : text(r.item_id),
        actor_id: r.actor_id === null ? null : text(r.actor_id),
        action: text(r.action),
        reason: r.reason === null ? null : text(r.reason),
        occurred_at: text(r.occurred_at),
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
    async fonds(signal?: AbortSignal): Promise<Fonds[]> {
        return entries(
            await this.request("/ingestion/fonds", "GET", undefined, signal),
        ).map(fonds);
    }
    async createFonds(name: string, storage_key: string): Promise<Fonds> {
        return fonds(
            await this.request("/ingestion/fonds", "POST", {
                name,
                storage_key,
            }),
        );
    }
    async fondsMembers(id: string, signal?: AbortSignal): Promise<string[]> {
        return entries(
            await this.request(
                `/ingestion/fonds/${encodeURIComponent(id)}/members`,
                "GET",
                undefined,
                signal,
            ),
        ).map((value) => text(object(value).user_id));
    }
    async fondsGrant(
        id: string,
        userId: string,
        enabled: boolean,
        reason: string,
    ): Promise<void> {
        await this.request(
            `/ingestion/fonds/${encodeURIComponent(id)}/members/${encodeURIComponent(userId)}`,
            "PUT",
            { enabled, reason },
        );
    }
    async batches(
        id: string,
        offset = 0,
        signal?: AbortSignal,
    ): Promise<IntakeBatch[]> {
        return entries(
            await this.request(
                `/ingestion/fonds/${encodeURIComponent(id)}/batches?limit=20&offset=${offset}`,
                "GET",
                undefined,
                signal,
            ),
        ).map(batch);
    }
    async startBatch(fonds_id: string): Promise<IntakeBatch> {
        return batch(
            await this.request("/ingestion/batches", "POST", { fonds_id }),
        );
    }
    async batch(id: string, signal?: AbortSignal): Promise<IntakeBatch> {
        return batch(
            await this.request(
                `/ingestion/batches/${encodeURIComponent(id)}`,
                "GET",
                undefined,
                signal,
            ),
        );
    }
    async batchCommand(
        id: string,
        command: string,
        reason: string,
    ): Promise<IntakeBatch> {
        return batch(
            await this.request(
                `/ingestion/batches/${encodeURIComponent(id)}/${encodeURIComponent(command)}`,
                "POST",
                { reason },
            ),
        );
    }
    async intakeItems(
        id: string,
        offset = 0,
        search = "",
        state = "",
        signal?: AbortSignal,
    ): Promise<IntakeItem[]> {
        return entries(
            await this.request(
                `/ingestion/batches/${encodeURIComponent(id)}/items?limit=20&offset=${offset}&search=${encodeURIComponent(search)}&state=${encodeURIComponent(state)}`,
                "GET",
                undefined,
                signal,
            ),
        ).map(item);
    }
    async intakeEvents(
        id: string,
        offset = 0,
        signal?: AbortSignal,
    ): Promise<IntakeEvent[]> {
        return entries(
            await this.request(
                `/ingestion/batches/${encodeURIComponent(id)}/events?limit=20&offset=${offset}`,
                "GET",
                undefined,
                signal,
            ),
        ).map(intakeEvent);
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

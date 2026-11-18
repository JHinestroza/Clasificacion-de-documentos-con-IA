import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, expect, it, vi } from "vitest";
import { AuthProvider } from "./auth";
import { App } from "./App";
import type { User } from "./api/models";

const admin: User = {
    id: "11111111-1111-4111-8111-111111111111",
    username: "synthetic_admin",
    is_active: true,
    is_superuser: true,
    permissions: [],
    created_at: "2026-11-13T10:00:00Z",
};
const reader: User = {
    ...admin,
    id: "22222222-2222-4222-8222-222222222222",
    username: "synthetic_operator",
    is_superuser: false,
    permissions: ["processing.start", "documents.read"],
};
const fonds = {
    id: "33333333-3333-4333-8333-333333333333",
    name: "UFM",
    storage_key: "UFM",
    active: true,
    incoming_path: "C:/synthetic/UFM/incoming",
};
const id = "44444444-4444-4444-8444-444444444444";
let current: User;
let state: string;
let fetcher: ReturnType<typeof vi.fn>;
const response = (body: unknown, status = 200) =>
    new Response(JSON.stringify(body), {
        status,
        headers: { "Content-Type": "application/json" },
    });
function batch() {
    return {
        id,
        fonds_id: fonds.id,
        state,
        created_at: "2026-11-13T11:00:00Z",
        total: 2,
        counts: { queued: 1, pending: 1 },
        blocked_publications: 0,
    };
}
function mount() {
    window.location.hash = "ingreso";
    return render(
        <AuthProvider>
            <App />
        </AuthProvider>,
    );
}
beforeEach(() => {
    current = { ...admin };
    state = "running";
    fetcher = vi.fn(async (input: string, options: RequestInit = {}) => {
        if (input.endsWith("/auth/me")) return response(current);
        if (input.endsWith("/auth/csrf"))
            return response({ csrf_token: "c".repeat(64) });
        if (input.endsWith("/ready"))
            return response({
                status: "ready",
                checks: { database: "ok", broker: "ok" },
            });
        if (input.endsWith("/ingestion/fonds")) return response([fonds]);
        if (input.includes("/members/") && options.method === "PUT")
            return response({ enabled: true, user_id: reader.id });
        if (input.endsWith("/members")) return response([]);
        if (input.includes("/users?")) return response([admin, reader]);
        if (input.includes("/batches?") || input.includes("/batches?limit"))
            return response([batch()]);
        if (input.endsWith("/ingestion/batches") && options.method === "POST")
            return response(batch(), 201);
        if (input.includes("/items?"))
            return response([
                {
                    id: "item",
                    original_name: "<img src=x onerror=alert(1)>.pdf",
                    code: null,
                    state: "admitted",
                    job_state: "queued",
                    reason_text: "",
                    size_bytes: 2000,
                    pages: 1,
                },
            ]);
        if (input.includes("/events?"))
            return response([
                {
                    id: "event",
                    item_id: null,
                    actor_id: admin.id,
                    action: "batch.started",
                    reason: null,
                    occurred_at: "2026-11-13T11:00:00Z",
                },
            ]);
        if (input.endsWith("/pause") && options.method === "POST") {
            state = "pause_requested";
            return response(batch());
        }
        if (input.endsWith("/resume") && options.method === "POST") {
            state = "running";
            return response(batch());
        }
        if (input.endsWith("/batches/" + id)) return response(batch());
        return response({}, 404);
    });
    vi.stubGlobal("fetch", fetcher);
});

it("hides intake and rejects its direct URL without an action permission", async () => {
    current = { ...reader, permissions: [] };
    mount();
    expect(
        await screen.findByRole("heading", { name: "Acceso restringido" }),
    ).toBeInTheDocument();
    expect(
        fetcher.mock.calls.some(([url]) =>
            String(url).includes("/ingestion/fonds"),
        ),
    ).toBe(false);
});

it("starts an authorized batch, displays real states and escapes filenames", async () => {
    current = { ...reader };
    const user = userEvent.setup();
    mount();
    expect(await screen.findByText(fonds.incoming_path)).toBeInTheDocument();
    expect(
        screen.queryByRole("button", { name: "Nuevo fondo" }),
    ).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Iniciar lote" }));
    expect(
        await screen.findByText("<img src=x onerror=alert(1)>.pdf"),
    ).toBeInTheDocument();
    expect(document.querySelector("img")).toBeNull();
    expect(screen.getByText("Pendientes de publicar")).toBeInTheDocument();
    expect(
        screen.queryByRole("heading", { name: "Historial del lote" }),
    ).not.toBeInTheDocument();
    const call = fetcher.mock.calls.find(
        ([url, options]) =>
            String(url).endsWith("/ingestion/batches") &&
            options.method === "POST",
    );
    expect(JSON.parse(String(call?.[1].body))).toEqual({ fonds_id: fonds.id });
    expect((call?.[1].headers as Record<string, string>)["X-CSRF-Token"]).toBe(
        "c".repeat(64),
    );
});

it("requires a reason for pause and keeps controls consistent with persisted state", async () => {
    const user = userEvent.setup();
    mount();
    await screen.findByText(fonds.incoming_path);
    await user.click(screen.getByRole("button", { name: "Iniciar lote" }));
    await user.click(await screen.findByRole("button", { name: "Pausar" }));
    const dialog = screen.getByRole("dialog");
    await user.click(within(dialog).getByRole("button", { name: "Pausar" }));
    expect(
        fetcher.mock.calls.some(([url]) => String(url).endsWith("/pause")),
    ).toBe(false);
    await user.type(
        within(dialog).getByLabelText("Motivo"),
        "Revisión de lote sintético",
    );
    await user.click(within(dialog).getByRole("button", { name: "Pausar" }));
    expect(
        await screen.findByRole("heading", { name: "Pausa solicitada" }),
    ).toBeInTheDocument();
    expect(
        screen.queryByRole("button", { name: "Reanudar" }),
    ).not.toBeInTheDocument();
    expect(
        await screen.findByRole("button", {
            name: /2 documentos.*Pausa solicitada/,
        }),
    ).toBeInTheDocument();
    state = "paused";
    await user.click(screen.getByRole("button", { name: "Actualizar estado" }));
    expect(
        await screen.findByRole("button", { name: "Reanudar" }),
    ).toBeInTheDocument();
});

it("grants fonds access to the selected account with a reason and CSRF", async () => {
    const user = userEvent.setup();
    mount();
    await screen.findByText(fonds.incoming_path);
    await user.click(screen.getByRole("button", { name: "Accesos al fondo" }));
    const dialog = await screen.findByRole("dialog");
    await user.selectOptions(
        await within(dialog).findByLabelText("Cuenta"),
        reader.id,
    );
    await user.click(
        within(dialog).getByRole("checkbox", {
            name: "Permitir acceso a este fondo",
        }),
    );
    await user.type(
        within(dialog).getByLabelText("Motivo"),
        "Ingreso documental UFM",
    );
    await user.click(
        within(dialog).getByRole("button", { name: "Guardar acceso" }),
    );
    await waitFor(() =>
        expect(screen.queryByRole("dialog")).not.toBeInTheDocument(),
    );
    const call = fetcher.mock.calls.find(
        ([url, options]) =>
            String(url).endsWith("/members/" + reader.id) &&
            options.method === "PUT",
    );
    expect(JSON.parse(String(call?.[1].body))).toEqual({
        enabled: true,
        reason: "Ingreso documental UFM",
    });
});

it("sanitizes backend failures and keeps the current private document view empty", async () => {
    fetcher.mockImplementation(async (input: string) =>
        input.endsWith("/auth/me")
            ? response(admin)
            : response({ detail: "SECRET path postgres://password" }, 503),
    );
    mount();
    expect(await screen.findByRole("alert")).toHaveTextContent(
        "El servicio no está disponible",
    );
    expect(screen.queryByText(/SECRET path/)).not.toBeInTheDocument();
});

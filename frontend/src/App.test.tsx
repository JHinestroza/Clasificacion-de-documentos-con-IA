import {
    act,
    fireEvent,
    render,
    screen,
    waitFor,
    within,
} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { User } from "./api/models";
import { App } from "./App";
import { AuthProvider } from "./auth";

const PASSWORD = "Synthetic-account-password-2026!";
const admin: User = {
    id: "11111111-1111-4111-8111-111111111111",
    username: "demo_admin",
    is_active: true,
    is_superuser: true,
    permissions: [],
    created_at: "2026-11-12T10:00:00Z",
};
const ordinary: User = {
    ...admin,
    id: "22222222-2222-4222-8222-222222222222",
    username: "demo_reader",
    is_superuser: false,
};
const response = (body: unknown, status = 200) =>
    new Response(JSON.stringify(body), {
        status,
        headers: { "Content-Type": "application/json" },
    });
let session: User | null;
let people: User[];
let logoutFails: boolean;
let fetcher: ReturnType<typeof vi.fn>;
function mount() {
    return render(
        <AuthProvider>
            <App />
        </AuthProvider>,
    );
}
function nav() {
    return within(
        screen.getByRole("complementary", { name: "Navegación principal" }),
    );
}
beforeEach(() => {
    session = { ...admin };
    people = [{ ...admin }, { ...ordinary }];
    logoutFails = false;
    fetcher = vi.fn(async (input: string, options: RequestInit = {}) => {
        const body = options.body
            ? (JSON.parse(String(options.body)) as Record<string, unknown>)
            : {};
        if (input.endsWith("/auth/csrf"))
            return response({ csrf_token: "c".repeat(64) });
        if (input.endsWith("/auth/login")) {
            if (body.password !== PASSWORD)
                return response({ detail: "credentials rejected" }, 401);
            session = { ...admin };
            return response({ user: session, csrf_token: "d".repeat(64) });
        }
        if (input.endsWith("/auth/me"))
            return session ? response(session) : response({}, 401);
        if (input.endsWith("/ready"))
            return response({
                status: "ready",
                checks: { database: "ok", broker: "ok" },
            });
        if (!session) return response({}, 401);
        if (input.endsWith("/auth/logout")) {
            if (logoutFails) return response({}, 503);
            session = null;
            return response({ status: "signed_out" });
        }
        if (input.endsWith("/auth/password")) {
            session = null;
            return response({ status: "password_changed_sessions_revoked" });
        }
        if (input.includes("/users?") && session.is_superuser)
            return response(people);
        if (
            input.endsWith("/users") &&
            options.method === "POST" &&
            session.is_superuser
        ) {
            const created = {
                ...ordinary,
                id: "33333333-3333-4333-8333-333333333333",
                username: String(body.username),
                is_superuser: body.is_superuser === true,
            };
            people.push(created);
            return response(created, 201);
        }
        if (input.endsWith("/permissions") && options.method === "GET")
            return response(["audit.read", "documents.read"]);
        if (input.includes("/users/") && options.method === "PUT") {
            people = people.map((person) =>
                person.id === ordinary.id
                    ? { ...person, permissions: body.permissions as string[] }
                    : person,
            );
            return response(people[1]);
        }
        if (input.includes("/users/") && options.method === "PATCH") {
            people = people.map((person) =>
                person.id === ordinary.id
                    ? { ...person, is_active: body.active === true }
                    : person,
            );
            return response(people[1]);
        }
        if (
            input.includes("/audit?") &&
            (session.is_superuser || session.permissions.includes("audit.read"))
        )
            return response([
                {
                    id: "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
                    actor_id: admin.id,
                    resource_id: ordinary.id,
                    action: "users.active",
                    outcome: "ok",
                    occurred_at: "2026-11-12T10:00:00Z",
                    reason: '<img src=x onerror="alert(1)">',
                },
            ]);
        return response({}, 403);
    });
    vi.stubGlobal("fetch", fetcher);
});
describe("React portal", () => {
    it("rejects malformed usernames before creating an account", async () => {
        const user = userEvent.setup();
        window.location.hash = "usuarios";
        mount();
        await user.click(
            await screen.findByRole("button", { name: "Crear cuenta" }),
        );
        const dialog = within(await screen.findByRole("dialog"));
        fireEvent.change(dialog.getByLabelText("Usuario", { exact: true }), {
            target: { value: "bad user" },
        });
        fireEvent.change(dialog.getByLabelText("Contraseña inicial"), {
            target: { value: PASSWORD },
        });
        expect(dialog.getByLabelText("Usuario", { exact: true })).toBeInvalid();
        await user.click(dialog.getByRole("button", { name: "Crear cuenta" }));
        expect(
            fetcher.mock.calls.some(
                (call) =>
                    call[0].endsWith("/users") && call[1]?.method === "POST",
            ),
        ).toBe(false);
    });

    it("signs in using the existing cookie/CSRF API", async () => {
        session = null;
        const user = userEvent.setup();
        mount();
        await screen.findByRole("heading", { name: "Inicia sesión" });
        await user.type(
            screen.getByLabelText("Usuario", { exact: true }),
            admin.username,
        );
        await user.type(
            screen.getByLabelText("Contraseña", { exact: true }),
            PASSWORD,
        );
        await user.click(
            screen.getByRole("button", { name: "Entrar a mi biblioteca" }),
        );
        await screen.findByRole("heading", { name: "Bienvenido, demo_admin." });
        expect(
            screen.queryByLabelText("Contraseña", { exact: true }),
        ).not.toBeInTheDocument();
    });
    it("shows a generic error for a failed login", async () => {
        session = null;
        const user = userEvent.setup();
        mount();
        await screen.findByRole("heading", { name: "Inicia sesión" });
        await user.type(
            screen.getByLabelText("Usuario", { exact: true }),
            "does_not_exist",
        );
        await user.type(
            screen.getByLabelText("Contraseña", { exact: true }),
            "incorrect",
        );
        await user.click(
            screen.getByRole("button", { name: "Entrar a mi biblioteca" }),
        );
        expect(await screen.findByRole("alert")).toHaveTextContent(
            "No se pudo validar el acceso",
        );
        expect(
            screen.getByRole("button", { name: "Entrar a mi biblioteca" }),
        ).toBeEnabled();
    });
    it("hides administration and guards direct URLs for an ordinary account", async () => {
        session = { ...ordinary };
        window.location.hash = "usuarios";
        mount();
        await screen.findByRole("heading", { name: "Acceso restringido" });
        expect(
            screen.queryByRole("link", { name: "Usuarios y permisos" }),
        ).not.toBeInTheDocument();
        expect(
            fetcher.mock.calls.some((call) => call[0].includes("/users?")),
        ).toBe(false);
    });
    it("creates a local account without granting permissions by default", async () => {
        const user = userEvent.setup();
        mount();
        await screen.findByRole("heading", { name: "Bienvenido, demo_admin." });
        await user.click(
            nav().getByRole("link", { name: "Usuarios y permisos" }),
        );
        await screen.findByRole("heading", {
            name: "Usuarios de la biblioteca",
        });
        await user.click(screen.getByRole("button", { name: "Crear cuenta" }));
        const dialog = within(await screen.findByRole("dialog"));
        await user.type(
            dialog.getByLabelText("Usuario", { exact: true }),
            "new_reader",
        );
        await user.type(dialog.getByLabelText("Contraseña inicial"), PASSWORD);
        await user.click(dialog.getByRole("button", { name: "Crear cuenta" }));
        await screen.findByText("new_reader");
        const request = fetcher.mock.calls.find(
            (call) => call[0].endsWith("/users") && call[1]?.method === "POST",
        );
        expect(JSON.parse(String(request?.[1]?.body))).toMatchObject({
            username: "new_reader",
            is_superuser: false,
        });
    });
    it("assigns permissions with an explicit reason", async () => {
        const user = userEvent.setup();
        window.location.hash = "usuarios";
        mount();
        await screen.findByRole("button", {
            name: "Editar permisos de demo_reader",
        });
        await user.click(
            screen.getByRole("button", {
                name: "Editar permisos de demo_reader",
            }),
        );
        const dialog = within(await screen.findByRole("dialog"));
        await user.click(
            await dialog.findByRole("checkbox", {
                name: "Consultar auditoría",
            }),
        );
        await user.type(
            dialog.getByLabelText("Motivo del cambio"),
            "Cambio de responsabilidades",
        );
        await user.click(
            dialog.getByRole("button", { name: "Guardar permisos" }),
        );
        await screen.findByText(
            "Permisos actualizados. Se cerraron las sesiones de esa cuenta.",
        );
        const request = fetcher.mock.calls.find(
            (call) => call[1]?.method === "PUT",
        );
        expect(JSON.parse(String(request?.[1]?.body))).toEqual({
            permissions: ["audit.read"],
            reason: "Cambio de responsabilidades",
        });
    });
    it("disables another account while protecting the current account in the UI", async () => {
        const user = userEvent.setup();
        window.location.hash = "usuarios";
        mount();
        await screen.findByRole("button", { name: "Desactivar a demo_reader" });
        expect(
            screen.getByRole("button", { name: "Desactivar a demo_admin" }),
        ).toBeDisabled();
        await user.click(
            screen.getByRole("button", { name: "Desactivar a demo_reader" }),
        );
        const dialog = within(await screen.findByRole("dialog"));
        await user.type(
            dialog.getByLabelText("Motivo del cambio"),
            "Fin de acceso temporal",
        );
        await user.click(
            dialog.getByRole("button", { name: "Desactivar cuenta" }),
        );
        await screen.findByText("Estado de la cuenta actualizado.");
        await waitFor(() =>
            expect(
                screen.getByRole("button", { name: "Activar a demo_reader" }),
            ).toBeEnabled(),
        );
    });
    it("renders audit reasons as text and never executes HTML", async () => {
        session = { ...ordinary, permissions: ["audit.read"] };
        window.location.hash = "auditoria";
        mount();
        await screen.findByText('<img src=x onerror="alert(1)">');
        expect(document.querySelector("img")).toBeNull();
        expect(
            screen.queryByRole("link", { name: "Usuarios y permisos" }),
        ).not.toBeInTheDocument();
    });
    it("does not claim logout succeeded when the server is unavailable", async () => {
        const user = userEvent.setup();
        logoutFails = true;
        mount();
        await screen.findByRole("heading", { name: "Bienvenido, demo_admin." });
        await user.click(screen.getByRole("button", { name: "Cerrar sesión" }));
        expect(await screen.findByRole("alert")).toHaveTextContent(
            "El servicio no está disponible",
        );
        expect(
            screen.getByRole("link", { name: "Mi cuenta" }),
        ).toBeInTheDocument();
        logoutFails = false;
        await user.click(screen.getByRole("button", { name: "Cerrar sesión" }));
        await screen.findByRole("heading", { name: "Inicia sesión" });
        expect(screen.queryByRole("complementary")).not.toBeInTheDocument();
    });
    it("clears private views after server-side session revocation", async () => {
        const user = userEvent.setup();
        mount();
        await screen.findByRole("heading", { name: "Bienvenido, demo_admin." });
        session = null;
        await user.click(nav().getByRole("link", { name: "Auditoría" }));
        await screen.findByRole("heading", { name: "Inicia sesión" });
        expect(screen.getByRole("status")).toHaveTextContent(
            "Tu sesión terminó",
        );
        expect(screen.queryByRole("table")).not.toBeInTheDocument();
    });
    it("changes password and returns to login after revocation", async () => {
        const user = userEvent.setup();
        window.location.hash = "cuenta";
        mount();
        await screen.findByRole("heading", { name: "Mi cuenta" });
        fireEvent.change(screen.getByLabelText("Contraseña actual"), {
            target: { value: PASSWORD },
        });
        fireEvent.change(
            screen.getByLabelText("Nueva contraseña", { exact: true }),
            { target: { value: "Replacement synthetic password!" } },
        );
        fireEvent.change(screen.getByLabelText("Repite la nueva contraseña"), {
            target: { value: "Mismatch synthetic password!" },
        });
        await user.click(
            screen.getByRole("button", { name: "Guardar contraseña" }),
        );
        expect(await screen.findByRole("alert")).toHaveTextContent(
            "no coinciden",
        );
        expect(
            fetcher.mock.calls.some((call) =>
                call[0].endsWith("/auth/password"),
            ),
        ).toBe(false);
        fireEvent.change(screen.getByLabelText("Repite la nueva contraseña"), {
            target: { value: "Replacement synthetic password!" },
        });
        await user.click(
            screen.getByRole("button", { name: "Guardar contraseña" }),
        );
        await screen.findByRole("heading", { name: "Inicia sesión" });
        expect(screen.getByRole("status")).toHaveTextContent(
            "Contraseña actualizada",
        );
    });
    it("shows no private view when the initial session cannot be verified", async () => {
        fetcher.mockResolvedValue(response({}, 503));
        mount();
        await screen.findByRole("heading", {
            name: "No pudimos verificar tu acceso.",
        });
        expect(screen.queryByRole("complementary")).not.toBeInTheDocument();
        await act(async () => {
            await Promise.resolve();
        });
    });
});

import { describe, expect, it, vi } from "vitest";
import { ApiError, IdentityApi } from "./client";

const person = {
    id: "11111111-1111-4111-8111-111111111111",
    username: "synthetic_user",
    is_active: true,
    is_superuser: false,
    permissions: [],
    created_at: "2026-11-12T10:00:00Z",
};
const response = (body: unknown, status = 200) =>
    new Response(JSON.stringify(body), {
        status,
        headers: { "Content-Type": "application/json" },
    });
describe("identity transport", () => {
    it("uses same-origin cookies and fresh CSRF without persisting credentials", async () => {
        const storage = vi.spyOn(Storage.prototype, "setItem");
        const fetcher = vi
            .fn()
            .mockResolvedValueOnce(response({ csrf_token: "a".repeat(64) }))
            .mockResolvedValueOnce(
                response({
                    user: person,
                    csrf_token: "b".repeat(64),
                    session_token: "not-to-be-exposed",
                }),
            );
        vi.stubGlobal("fetch", fetcher);
        expect(
            await new IdentityApi().login(
                "synthetic_user",
                "Synthetic password for testing!",
            ),
        ).toEqual(person);
        expect(fetcher.mock.calls[0][0]).toBe("/api/v1/auth/csrf");
        const options = fetcher.mock.calls[1][1] as RequestInit;
        expect(options.credentials).toBe("same-origin");
        expect(options.redirect).toBe("error");
        expect(options.cache).toBe("no-store");
        expect(options.headers).toMatchObject({
            "X-CSRF-Token": "a".repeat(64),
        });
        expect(storage).not.toHaveBeenCalled();
        expect(
            fetcher.mock.calls.every(
                (call) => !String(call[0]).includes("password"),
            ),
        ).toBe(true);
    });
    it("rejects a malformed CSRF before sending a password", async () => {
        const fetcher = vi
            .fn()
            .mockResolvedValue(response({ csrf_token: "bad" }));
        vi.stubGlobal("fetch", fetcher);
        await expect(
            new IdentityApi().login("synthetic_user", "Synthetic password!"),
        ).rejects.toMatchObject({ status: 502 });
        expect(fetcher).toHaveBeenCalledTimes(1);
    });
    it("never echoes private server errors", async () => {
        vi.stubGlobal(
            "fetch",
            vi
                .fn()
                .mockResolvedValue(
                    response(
                        { detail: "postgresql://private:password@host/secret" },
                        503,
                    ),
                ),
        );
        try {
            await new IdentityApi().me();
            throw new Error("Expected failure");
        } catch (error) {
            expect(error).toBeInstanceOf(ApiError);
            expect((error as Error).message).not.toMatch(
                /postgresql|private|password|secret/,
            );
        }
    });
    it("notifies session loss on unauthorized reads", async () => {
        const expired = vi.fn();
        vi.stubGlobal(
            "fetch",
            vi.fn().mockResolvedValue(response({ detail: "generic" }, 401)),
        );
        await expect(new IdentityApi(expired).me()).rejects.toMatchObject({
            status: 401,
        });
        expect(expired).toHaveBeenCalledOnce();
    });
    it("represents real unavailability from the readiness endpoint", async () => {
        const state = {
            status: "not_ready",
            checks: { database: "unavailable", broker: "ok" },
        };
        vi.stubGlobal("fetch", vi.fn().mockResolvedValue(response(state, 503)));
        expect(await new IdentityApi().ready()).toEqual(state);
    });
    it("refuses plaintext before making any request", async () => {
        const fetcher = vi.fn();
        vi.stubGlobal("fetch", fetcher);
        vi.stubGlobal("window", { location: { protocol: "http:" } });
        await expect(new IdentityApi().me()).rejects.toMatchObject({
            status: 0,
        });
        expect(fetcher).not.toHaveBeenCalled();
    });
    it("does not deliver an expired response from a cancelled view", async () => {
        const controller = new AbortController();
        const expired = vi.fn();
        vi.stubGlobal(
            "fetch",
            vi.fn().mockImplementation(async () => {
                controller.abort();
                return response({}, 401);
            }),
        );
        await expect(
            new IdentityApi(expired).me(controller.signal),
        ).rejects.toHaveProperty("name", "AbortError");
        expect(expired).not.toHaveBeenCalled();
    });
});

import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach, vi } from "vitest";

Object.defineProperty(HTMLDialogElement.prototype, "showModal", {
    configurable: true,
    value() {
        this.open = true;
    },
});
Object.defineProperty(HTMLDialogElement.prototype, "close", {
    configurable: true,
    value() {
        this.open = false;
    },
});
afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
    window.location.hash = "";
});

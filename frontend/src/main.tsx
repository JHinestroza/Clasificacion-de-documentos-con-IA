import { Component } from "react";
import type { ReactNode } from "react";
import { createRoot } from "react-dom/client";
import { App } from "./App";
import { AuthProvider } from "./auth";
import "./styles.css";

class ErrorBoundary extends Component<
    { children: ReactNode },
    { failed: boolean }
> {
    state = { failed: false };
    static getDerivedStateFromError() {
        return { failed: true };
    }
    render() {
        return this.state.failed ? (
            <main className="standalone">
                <h1>No pudimos mostrar esta vista.</h1>
                <p>Vuelve a cargar la página para continuar.</p>
                <button
                    className="button primary"
                    onClick={() => window.location.reload()}
                >
                    Volver a cargar
                </button>
            </main>
        ) : (
            this.props.children
        );
    }
}
const root = document.getElementById("root");
if (!root) throw new Error("Root element required");
createRoot(root, { onCaughtError: () => {}, onUncaughtError: () => {} }).render(
    <ErrorBoundary>
        <AuthProvider>
            <App />
        </AuthProvider>
    </ErrorBoundary>,
);

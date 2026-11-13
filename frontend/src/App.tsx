import { useEffect, useState } from "react";
import {
    BookOpen,
    FileClock,
    Home as HomeIcon,
    LogOut,
    ShieldCheck,
    Users,
} from "lucide-react";
import { useAuth } from "./auth";
import { errorMessage } from "./api/client";
import { Alert, Busy } from "./components/common";
import { Login } from "./pages/Login";
import { Home } from "./pages/Home";
import { UsersPage } from "./pages/Users";
import { AuditPage } from "./pages/Audit";
import { AccountPage } from "./pages/Account";

const labels: Record<string, string> = {
    inicio: "Inicio",
    usuarios: "Usuarios y permisos",
    auditoria: "Auditoría",
    cuenta: "Mi cuenta",
};
export function App() {
    const { phase, user, signOut, refresh } = useAuth();
    const [page, setPage] = useState(
        () => window.location.hash.slice(1) || "inicio",
    );
    const [logoutBusy, setLogoutBusy] = useState(false);
    const [error, setError] = useState("");
    useEffect(() => {
        const navigate = () =>
            setPage(window.location.hash.slice(1) || "inicio");
        window.addEventListener("hashchange", navigate);
        return () => window.removeEventListener("hashchange", navigate);
    }, []);
    async function logout() {
        setLogoutBusy(true);
        setError("");
        try {
            await signOut();
        } catch (failure) {
            setError(errorMessage(failure));
        } finally {
            setLogoutBusy(false);
        }
    }
    if (phase === "checking")
        return (
            <main className="standalone">
                <span className="brand-symbol" aria-hidden="true">
                    a.
                </span>
                <Busy label="Verificando tu acceso…" />
            </main>
        );
    if (phase === "unavailable")
        return (
            <main className="standalone">
                <BookOpen size={38} aria-hidden="true" />
                <h1>No pudimos verificar tu acceso.</h1>
                <p>El servicio no está disponible en este momento.</p>
                <button
                    className="button primary"
                    onClick={() => void refresh()}
                >
                    Volver a intentar
                </button>
            </main>
        );
    if (phase === "guest" || !user) return <Login />;
    const canAudit =
        user.is_superuser || user.permissions.includes("audit.read");
    const links = [
        { id: "inicio", label: "Inicio", icon: HomeIcon, allowed: true },
        {
            id: "usuarios",
            label: "Usuarios y permisos",
            icon: Users,
            allowed: user.is_superuser,
        },
        {
            id: "auditoria",
            label: "Auditoría",
            icon: FileClock,
            allowed: canAudit,
        },
        { id: "cuenta", label: "Mi cuenta", icon: ShieldCheck, allowed: true },
    ];
    const denied =
        (page === "usuarios" && !user.is_superuser) ||
        (page === "auditoria" && !canAudit);
    return (
        <>
            <a
                className="skip-link"
                href="#main-content"
                onClick={(event) => {
                    event.preventDefault();
                    document.getElementById("main-content")?.focus();
                }}
            >
                Ir al contenido
            </a>
            <div className="shell">
                <aside className="sidebar" aria-label="Navegación principal">
                    <a className="brand" href="#inicio">
                        <span className="brand-symbol" aria-hidden="true">
                            a.
                        </span>
                        <div>
                            Archivo<span>Biblioteca documental</span>
                        </div>
                    </a>
                    <p className="nav-heading">ESPACIO DE TRABAJO</p>
                    <nav>
                        {links
                            .filter((link) => link.allowed)
                            .map(({ id, label, icon: Icon }) => (
                                <a
                                    className={`nav-item ${page === id ? "active" : ""}`}
                                    href={`#${id}`}
                                    aria-current={
                                        page === id ? "page" : undefined
                                    }
                                    key={id}
                                >
                                    <Icon size={18} aria-hidden="true" />
                                    {label}
                                </a>
                            ))}
                    </nav>
                    <div className="sidebar-bottom">
                        <span className="avatar" aria-hidden="true">
                            {user.username.slice(0, 1).toUpperCase()}
                        </span>
                        <div>
                            <strong>{user.username}</strong>
                            <span>
                                {user.is_superuser ? "Superusuario" : "Usuario"}
                            </span>
                        </div>
                        <button
                            className="icon-button"
                            onClick={() => void logout()}
                            disabled={logoutBusy}
                            aria-label="Cerrar sesión"
                        >
                            <LogOut size={18} aria-hidden="true" />
                        </button>
                    </div>
                </aside>
                <main id="main-content" className="workspace" tabIndex={-1}>
                    <header className="topbar">
                        <span>
                            Biblioteca <span className="separator">/</span>{" "}
                            {labels[page] ?? "Página"}
                        </span>
                        <span className="access-tag">
                            <ShieldCheck size={13} aria-hidden="true" />
                            Acceso privado
                        </span>
                    </header>
                    <div className="page-content">
                        {error && <Alert>{error}</Alert>}
                        {denied ? (
                            <section className="empty-page">
                                <ShieldCheck size={34} aria-hidden="true" />
                                <h1>Acceso restringido</h1>
                                <p>
                                    Tu cuenta no tiene permiso para consultar
                                    esta vista.
                                </p>
                                <a className="button" href="#inicio">
                                    Volver al inicio
                                </a>
                            </section>
                        ) : page === "inicio" ? (
                            <Home />
                        ) : page === "usuarios" ? (
                            <UsersPage />
                        ) : page === "auditoria" ? (
                            <AuditPage />
                        ) : page === "cuenta" ? (
                            <AccountPage />
                        ) : (
                            <section className="empty-page">
                                <h1>No encontramos esta página.</h1>
                                <a className="button" href="#inicio">
                                    Volver al inicio
                                </a>
                            </section>
                        )}
                    </div>
                    <footer className="page-footer">
                        Archivo · Biblioteca documental
                        <span>Un espacio para preservar la memoria.</span>
                    </footer>
                </main>
            </div>
        </>
    );
}

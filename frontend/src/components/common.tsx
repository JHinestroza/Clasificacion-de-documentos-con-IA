import { useEffect, useRef } from "react";
import type { ReactNode } from "react";
import {
    AlertCircle,
    ArrowLeft,
    ArrowRight,
    LoaderCircle,
    X,
} from "lucide-react";

export function Busy({ label = "Cargando…" }: { label?: string }) {
    return (
        <div className="busy" role="status">
            <LoaderCircle className="spin" aria-hidden="true" />
            {label}
        </div>
    );
}
export function Alert({
    children,
    success = false,
}: {
    children: ReactNode;
    success?: boolean;
}) {
    return (
        <div
            className={`alert ${success ? "success" : "error"}`}
            role={success ? "status" : "alert"}
        >
            <AlertCircle size={18} aria-hidden="true" />
            <span>{children}</span>
        </div>
    );
}
export function PageHeading({
    eyebrow,
    title,
    description,
    action,
}: {
    eyebrow: string;
    title: string;
    description: string;
    action?: ReactNode;
}) {
    return (
        <header className="page-heading">
            <div>
                <p className="eyebrow">{eyebrow}</p>
                <h1>{title}</h1>
                <p>{description}</p>
            </div>
            {action}
        </header>
    );
}
export function Pagination({
    offset,
    count,
    onChange,
}: {
    offset: number;
    count: number;
    onChange: (offset: number) => void;
}) {
    return (
        <nav className="pagination" aria-label="Paginación">
            <span>
                Página {offset / 20 + 1} · {count} registros
            </span>
            <div>
                <button
                    className="button"
                    disabled={offset === 0}
                    onClick={() => onChange(offset - 20)}
                >
                    <ArrowLeft size={16} aria-hidden="true" />
                    Anterior
                </button>
                <button
                    className="button"
                    disabled={count < 20 || offset >= 100000}
                    onClick={() => onChange(offset + 20)}
                >
                    Siguiente
                    <ArrowRight size={16} aria-hidden="true" />
                </button>
            </div>
        </nav>
    );
}
export function Modal({
    title,
    children,
    onClose,
    busy = false,
}: {
    title: string;
    children: ReactNode;
    onClose: () => void;
    busy?: boolean;
}) {
    const dialog = useRef<HTMLDialogElement>(null);
    useEffect(() => {
        dialog.current?.showModal();
    }, []);
    return (
        <dialog
            className="modal"
            ref={dialog}
            aria-labelledby="modal-title"
            onCancel={(event) => {
                if (busy) event.preventDefault();
                else onClose();
            }}
        >
            <div className="modal-heading">
                <h2 id="modal-title">{title}</h2>
                <button
                    className="icon-button"
                    aria-label="Cerrar ventana"
                    disabled={busy}
                    onClick={onClose}
                >
                    <X size={20} aria-hidden="true" />
                </button>
            </div>
            {children}
        </dialog>
    );
}
export function date(value: string) {
    const result = new Date(value);
    return Number.isNaN(result.getTime())
        ? "—"
        : new Intl.DateTimeFormat("es-GT", {
              dateStyle: "short",
              timeStyle: "short",
          }).format(result);
}

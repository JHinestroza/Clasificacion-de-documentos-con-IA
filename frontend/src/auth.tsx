import {
    createContext,
    useCallback,
    useContext,
    useEffect,
    useMemo,
    useRef,
    useState,
} from "react";
import type { ReactNode } from "react";
import { ApiError, IdentityApi } from "./api/client";
import type { User } from "./api/models";

type Phase = "checking" | "signed" | "guest" | "unavailable";
interface AuthState {
    user: User | null;
    phase: Phase;
    notice: string;
    api: IdentityApi;
    signIn: (username: string, password: string) => Promise<void>;
    signOut: () => Promise<void>;
    refresh: () => Promise<void>;
    clear: (notice?: string) => void;
}
const Auth = createContext<AuthState | null>(null);
export function AuthProvider({ children }: { children: ReactNode }) {
    const [user, setUser] = useState<User | null>(null);
    const [phase, setPhase] = useState<Phase>("checking");
    const [notice, setNotice] = useState("");
    const current = useRef<User | null>(null);
    const generation = useRef(0);
    const clear = useCallback((message = "") => {
        generation.current += 1;
        current.current = null;
        setUser(null);
        setPhase("guest");
        setNotice(message);
    }, []);
    const api = useMemo(
        () =>
            new IdentityApi(() =>
                clear(
                    current.current
                        ? "Tu sesión terminó. Vuelve a iniciar sesión."
                        : "",
                ),
            ),
        [clear],
    );
    const refresh = useCallback(async () => {
        const version = ++generation.current;
        setPhase("checking");
        try {
            const result = await api.me();
            if (version !== generation.current) return;
            current.current = result;
            setUser(result);
            setPhase("signed");
        } catch (error) {
            if (version !== generation.current) return;
            current.current = null;
            setUser(null);
            setPhase(
                error instanceof ApiError && error.status === 401
                    ? "guest"
                    : "unavailable",
            );
        }
    }, [api]);
    useEffect(() => {
        void refresh();
    }, [refresh]);
    useEffect(() => {
        const check = () => {
            if (document.visibilityState === "visible" && current.current)
                void refresh();
        };
        document.addEventListener("visibilitychange", check);
        return () => document.removeEventListener("visibilitychange", check);
    }, [refresh]);
    const signIn = async (username: string, password: string) => {
        const result = await api.login(username, password);
        generation.current += 1;
        current.current = result;
        setUser(result);
        setPhase("signed");
        setNotice("");
    };
    const signOut = async () => {
        try {
            await api.logout();
        } catch (error) {
            if (!(error instanceof ApiError && error.status === 401))
                throw error;
        }
        clear("Has cerrado sesión.");
        window.location.hash = "inicio";
    };
    return (
        <Auth.Provider
            value={{
                user,
                phase,
                notice,
                api,
                signIn,
                signOut,
                refresh,
                clear,
            }}
        >
            {children}
        </Auth.Provider>
    );
}
export function useAuth(): AuthState {
    const value = useContext(Auth);
    if (!value) throw new Error("AuthProvider is required");
    return value;
}

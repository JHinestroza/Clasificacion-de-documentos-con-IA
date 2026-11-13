import { useCallback, useEffect, useState } from "react";
import { errorMessage } from "../api/client";

/** Discard stale data while loading and cancel the previous view's request on unmount. */
export function useResource<T>(load: (signal: AbortSignal) => Promise<T>) {
    const [revision, setRevision] = useState(0);
    const [state, setState] = useState<{
        data: T | null;
        loading: boolean;
        error: string | null;
    }>({ data: null, loading: true, error: null });
    useEffect(() => {
        const controller = new AbortController();
        setState({ data: null, loading: true, error: null });
        void load(controller.signal)
            .then((data) => {
                if (!controller.signal.aborted)
                    setState({ data, loading: false, error: null });
            })
            .catch((error) => {
                if (!controller.signal.aborted)
                    setState({
                        data: null,
                        loading: false,
                        error: errorMessage(error),
                    });
            });
        return () => controller.abort();
    }, [load, revision]);
    const refresh = useCallback(() => setRevision((value) => value + 1), []);
    return { ...state, refresh };
}

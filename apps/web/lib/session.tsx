"use client";

import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";
import { api, ApiError } from "./api-client";
import type { SessionResponse } from "./types";

interface SessionContextValue {
  session: SessionResponse | null;
  loading: boolean;
  refresh: () => Promise<void>;
  logout: () => Promise<void>;
}

const SessionContext = createContext<SessionContextValue | null>(null);

export function SessionProvider({ children }: { children: ReactNode }) {
  const [session, setSession] = useState<SessionResponse | null>(null);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    try {
      const data = await api.get<SessionResponse>("/auth/session");
      setSession(data);
    } catch (err) {
      // 401 just means "not logged in" — not an application error worth surfacing.
      if (!(err instanceof ApiError && err.status === 401)) {
        console.error("Failed to load session:", err);
      }
      setSession(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const logout = useCallback(async () => {
    await api.post("/auth/logout");
    setSession(null);
  }, []);

  return (
    <SessionContext.Provider value={{ session, loading, refresh, logout }}>{children}</SessionContext.Provider>
  );
}

export function useSession(): SessionContextValue {
  const ctx = useContext(SessionContext);
  if (!ctx) throw new Error("useSession must be used within a SessionProvider");
  return ctx;
}

import {
  createContext,
  useCallback,
  useEffect,
  useState,
  type ReactNode,
} from "react";
import * as authApi from "@/api/auth";
import type { User } from "@/lib/types";
import { STORAGE_KEYS } from "@/lib/constants";

export interface AuthContextValue {
  user: User | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  login: (code: string) => Promise<void>;
  logout: () => Promise<void>;
  hasPermission: (permission: string) => boolean;
}

export const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  const isAuthenticated = user !== null;

  // On mount: validate existing token
  useEffect(() => {
    const token = localStorage.getItem(STORAGE_KEYS.ACCESS_TOKEN);
    if (!token) {
      setIsLoading(false);
      return;
    }

    authApi
      .getMe()
      .then(setUser)
      .catch(() => {
        localStorage.removeItem(STORAGE_KEYS.ACCESS_TOKEN);
        localStorage.removeItem(STORAGE_KEYS.REFRESH_TOKEN);
      })
      .finally(() => setIsLoading(false));
  }, []);

  const login = useCallback(async (code: string) => {
    const redirectUri = `${window.location.origin}/auth/callback`;
    const tokens = await authApi.googleLogin(code, redirectUri);

    localStorage.setItem(STORAGE_KEYS.ACCESS_TOKEN, tokens.access_token);
    localStorage.setItem(STORAGE_KEYS.REFRESH_TOKEN, tokens.refresh_token);

    const me = await authApi.getMe();
    setUser(me);
  }, []);

  const logout = useCallback(async () => {
    try {
      await authApi.logout();
    } catch {
      // Best-effort logout
    } finally {
      localStorage.removeItem(STORAGE_KEYS.ACCESS_TOKEN);
      localStorage.removeItem(STORAGE_KEYS.REFRESH_TOKEN);
      setUser(null);
      window.location.href = "/login";
    }
  }, []);

  const hasPermission = useCallback(
    (permission: string) => {
      if (!user) return false;
      return user.permissions.includes(permission);
    },
    [user]
  );

  return (
    <AuthContext.Provider
      value={{ user, isAuthenticated, isLoading, login, logout, hasPermission }}
    >
      {children}
    </AuthContext.Provider>
  );
}

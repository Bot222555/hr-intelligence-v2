import { useEffect, useRef } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { useAuth } from "@/hooks/useAuth";

export function AuthCallbackPage() {
  const [searchParams] = useSearchParams();
  const { login } = useAuth();
  const navigate = useNavigate();
  const calledRef = useRef(false);

  useEffect(() => {
    // Prevent double-call in StrictMode
    if (calledRef.current) return;
    calledRef.current = true;

    const code = searchParams.get("code");
    const error = searchParams.get("error");

    if (error || !code) {
      navigate("/login", { replace: true });
      return;
    }

    login(code)
      .then(() => navigate("/dashboard", { replace: true }))
      .catch(() => navigate("/login", { replace: true }));
  }, [searchParams, login, navigate]);

  return (
    <div className="flex h-screen items-center justify-center">
      <div className="flex flex-col items-center gap-3">
        <div className="h-8 w-8 animate-spin rounded-full border-4 border-primary border-t-transparent" />
        <p className="text-sm text-muted-foreground">Signing you in…</p>
      </div>
    </div>
  );
}

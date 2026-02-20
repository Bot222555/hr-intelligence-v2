import { useNavigate } from "react-router-dom";
import { FileQuestion } from "lucide-react";
import { Button } from "@/components/ui/button";

export function NotFoundPage() {
  const navigate = useNavigate();

  return (
    <div className="flex min-h-screen flex-col items-center justify-center gap-4 p-4">
      <FileQuestion className="h-16 w-16 text-muted-foreground/40" />
      <h1 className="text-4xl font-bold text-foreground">404</h1>
      <p className="text-muted-foreground">
        The page you're looking for doesn't exist.
      </p>
      <Button onClick={() => navigate("/dashboard")} className="mt-2">
        Go to Dashboard
      </Button>
    </div>
  );
}

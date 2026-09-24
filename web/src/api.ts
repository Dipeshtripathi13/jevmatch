const API_URL = import.meta.env.VITE_API_URL || "http://localhost:8000";

export async function api<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`${API_URL}${path}`, options);
  if (!response.ok) {
    let message = `Request failed (${response.status})`;
    try {
      const body = (await response.json()) as { detail?: unknown };
      if (typeof body.detail === "string") {
        message = body.detail;
      } else if (Array.isArray(body.detail)) {
        const details = body.detail
          .map((item) => {
            if (!item || typeof item !== "object") return null;
            const error = item as { loc?: unknown[]; msg?: string };
            const location = Array.isArray(error.loc)
              ? error.loc.filter((part) => part !== "body").join(".")
              : "";
            return error.msg
              ? `${location ? `${location}: ` : ""}${error.msg}`
              : null;
          })
          .filter(Boolean);
        if (details.length) message = details.join("; ");
      }
    } catch {
      // Preserve the status fallback for non-JSON errors.
    }
    throw new Error(message);
  }
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

export function jsonRequest(body: unknown): RequestInit {
  return {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  };
}

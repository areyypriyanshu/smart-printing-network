import type { ReactNode } from "react";

import { cn } from "../../lib/cn";

type AlertProps = {
  variant?: "error" | "success" | "info";
  children: ReactNode;
};

const VARIANTS = {
  error: "border-red-200 bg-red-50 text-red-800",
  success: "border-green-200 bg-green-50 text-green-800",
  info: "border-beige-deep bg-cream text-ink",
} as const;

export function Alert({ variant = "error", children }: AlertProps) {
  return (
    <div
      role="alert"
      className={cn("rounded-md border px-3 py-2 text-sm", VARIANTS[variant])}
    >
      {children}
    </div>
  );
}

import type { ReactNode } from "react";

import { cn } from "../../lib/cn";
import { Icon, type IconName } from "./Icon";

type AlertProps = {
  variant?: "error" | "success" | "info";
  children: ReactNode;
};

const VARIANTS = {
  error: {
    icon: "alert",
    className: "border-danger-border bg-danger-bg text-danger",
  },
  success: {
    icon: "check",
    className: "border-success-border bg-success-bg text-success",
  },
  info: {
    icon: "info",
    className: "border-info-border bg-info-bg text-info",
  },
} as const satisfies Record<string, { icon: IconName; className: string }>;

export function Alert({ variant = "error", children }: AlertProps) {
  const { icon, className } = VARIANTS[variant];
  return (
    <div
      role="alert"
      className={cn(
        "flex items-start gap-2 rounded-lg border px-3 py-2 text-sm",
        className,
      )}
    >
      <Icon name={icon} size={18} className="mt-0.5 shrink-0" />
      <div>{children}</div>
    </div>
  );
}

import type { ButtonHTMLAttributes } from "react";

import { cn } from "../../lib/cn";

type Variant = "primary" | "secondary" | "danger";

type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: Variant;
  pending?: boolean;
  pendingLabel?: string;
};

const VARIANTS: Record<Variant, string> = {
  primary:
    "bg-primary text-white enabled:hover:bg-primary-deep disabled:bg-hairline disabled:text-muted",
  secondary:
    "border border-hairline-strong bg-transparent text-ink enabled:hover:bg-surface",
  danger: "bg-red-600 text-white enabled:hover:bg-red-700 disabled:bg-red-200",
};

export function Button({
  variant = "primary",
  pending = false,
  pendingLabel,
  className,
  children,
  disabled,
  ...rest
}: ButtonProps) {
  return (
    <button
      {...rest}
      disabled={disabled === true || pending}
      className={cn(
        "inline-flex min-h-11 items-center justify-center rounded-md px-4 py-2 text-sm font-medium",
        "focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary",
        "disabled:cursor-not-allowed disabled:opacity-80",
        VARIANTS[variant],
        className,
      )}
    >
      {pending ? (pendingLabel ?? "Working…") : children}
    </button>
  );
}

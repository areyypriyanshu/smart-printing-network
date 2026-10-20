import type { ButtonHTMLAttributes } from "react";

import { cn } from "../../lib/cn";

type Variant = "primary" | "secondary" | "danger";

type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: Variant;
  pending?: boolean;
  pendingLabel?: string;
};

const VARIANTS: Record<Variant, string> = {
  // A disabled primary button keeps its shape but drops the contrast, so
  // the label stays readable instead of turning into a smudge.
  primary:
    "bg-primary text-white enabled:hover:bg-primary-deep disabled:bg-hairline disabled:text-stone",
  secondary:
    "border border-hairline-strong bg-canvas text-ink enabled:hover:border-ink enabled:hover:bg-surface",
  danger:
    "bg-danger-solid text-white enabled:hover:bg-danger disabled:bg-danger-border disabled:text-danger",
};

export function buttonClassName(
  variant: Variant = "primary",
  className?: string,
) {
  return cn(
    "inline-flex min-h-11 items-center justify-center gap-2 rounded-lg px-4 py-2 text-sm font-medium",
    "transition-[background-color,border-color,color,transform] duration-150 ease-out",
    "active:enabled:translate-y-px motion-reduce:transition-none motion-reduce:active:translate-y-0",
    "focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary",
    "disabled:cursor-not-allowed disabled:opacity-80",
    VARIANTS[variant],
    className,
  );
}

export function Button({
  variant = "primary",
  pending = false,
  pendingLabel,
  className,
  children,
  disabled,
  type = "button",
  ...rest
}: ButtonProps) {
  return (
    <button
      {...rest}
      // A button defaults to submitting its form, which is a trap for a
      // button that is only ever a button. Submitting is opt in.
      type={type}
      disabled={disabled === true || pending}
      aria-busy={pending || undefined}
      className={buttonClassName(variant, className)}
    >
      {pending ? (pendingLabel ?? "Working…") : children}
    </button>
  );
}

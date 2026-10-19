import type { InputHTMLAttributes } from "react";

import { cn } from "../../lib/cn";

export function Input({
  className,
  ...rest
}: InputHTMLAttributes<HTMLInputElement>) {
  return (
    <input
      {...rest}
      className={cn(
        "block w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900",
        "focus:border-primary-600 focus:outline-2 focus:outline-offset-0 focus:outline-primary-600",
        "aria-[invalid=true]:border-red-600",
        className,
      )}
    />
  );
}

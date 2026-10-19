import type { TextareaHTMLAttributes } from "react";

import { cn } from "../../lib/cn";

export function Textarea({
  className,
  ...rest
}: TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return (
    <textarea
      {...rest}
      className={cn(
        "block w-full rounded-lg border border-hairline-strong bg-canvas px-3 py-2 text-sm text-ink",
        "transition-[border-color,box-shadow] duration-150 ease-out",
        "placeholder:text-stone",
        "focus:border-primary focus:outline-2 focus:outline-offset-0 focus:outline-primary",
        "aria-[invalid=true]:border-danger aria-[invalid=true]:bg-danger-bg",
        className,
      )}
    />
  );
}

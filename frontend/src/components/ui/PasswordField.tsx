import { useState, type InputHTMLAttributes } from "react";

import { cn } from "../../lib/cn";
import { Icon } from "./Icon";
import { Input } from "./Input";

type PasswordFieldProps = Omit<
  InputHTMLAttributes<HTMLInputElement>,
  "type"
> & {
  label: string;
  name: string;
  error?: string;
};

export function PasswordField({
  label,
  name,
  error,
  className,
  ...rest
}: PasswordFieldProps) {
  const [visible, setVisible] = useState(false);
  const errorId = `${name}-error`;

  return (
    <div className="flex flex-col gap-1.5">
      <label htmlFor={name} className="text-sm font-medium text-ink">
        {label}
      </label>
      <div className="relative">
        <Input
          id={name}
          name={name}
          type={visible ? "text" : "password"}
          aria-invalid={error !== undefined}
          aria-describedby={error !== undefined ? errorId : undefined}
          className={cn("pr-12", className)}
          {...rest}
        />
        <button
          type="button"
          onClick={() => setVisible((current) => !current)}
          aria-label={visible ? "Hide password" : "Show password"}
          aria-pressed={visible}
          // 44 px, so the button is a comfortable target on a phone.
          className="absolute right-0 top-1/2 inline-flex h-11 w-11 -translate-y-1/2 items-center justify-center rounded-md text-steel transition-colors duration-150 hover:text-ink focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary"
        >
          <Icon name={visible ? "eye-off" : "eye"} size={18} />
        </button>
      </div>
      {error !== undefined && (
        <p id={errorId} role="alert" className="text-sm text-danger">
          {error}
        </p>
      )}
    </div>
  );
}

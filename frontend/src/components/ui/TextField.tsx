import type { InputHTMLAttributes } from "react";

import { Input } from "./Input";

type TextFieldProps = InputHTMLAttributes<HTMLInputElement> & {
  label: string;
  name: string;
  error?: string;
};

export function TextField({ label, name, error, ...rest }: TextFieldProps) {
  const errorId = `${name}-error`;
  return (
    <div className="flex flex-col gap-1.5">
      <label htmlFor={name} className="text-sm font-medium text-ink">
        {label}
      </label>
      <Input
        id={name}
        name={name}
        aria-invalid={error !== undefined}
        aria-describedby={error !== undefined ? errorId : undefined}
        {...rest}
      />
      {error !== undefined && (
        <p id={errorId} role="alert" className="text-sm text-danger">
          {error}
        </p>
      )}
    </div>
  );
}

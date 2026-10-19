import { cn } from "../../lib/cn";

type StepperProps = {
  steps: string[];
  current: number;
};

export function Stepper({ steps, current }: StepperProps) {
  return (
    <ol className="flex flex-wrap items-center gap-2 text-sm">
      {steps.map((label, index) => {
        const number = index + 1;
        const state =
          number === current
            ? "current"
            : number < current
              ? "done"
              : "upcoming";
        return (
          <li key={label} className="flex items-center gap-2">
            {index > 0 && (
              <span aria-hidden="true" className="text-muted">
                /
              </span>
            )}
            <span
              aria-current={state === "current" ? "step" : undefined}
              className={cn(
                "inline-flex items-center gap-2 rounded-full border px-3 py-1",
                state === "current" &&
                  "border-primary bg-primary font-medium text-white",
                state === "done" && "border-hairline bg-cream text-ink",
                state === "upcoming" && "border-hairline bg-canvas text-steel",
              )}
            >
              <span className="text-xs">{number}</span>
              {label}
            </span>
          </li>
        );
      })}
    </ol>
  );
}

import { cn } from "../../lib/cn";
import { Icon } from "./Icon";

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
              <span aria-hidden="true" className="text-stone">
                /
              </span>
            )}
            <span
              aria-current={state === "current" ? "step" : undefined}
              className={cn(
                "inline-flex items-center gap-2 rounded-full border px-3 py-1",
                state === "current" &&
                  "border-primary bg-primary font-medium text-white",
                // A finished step and a step still to come must not look
                // the same. The tick and the dashed border carry the
                // state, so it never depends on the colour alone.
                state === "done" && "border-hairline-strong bg-canvas text-ink",
                state === "upcoming" &&
                  "border-dashed border-hairline-strong bg-canvas text-steel",
              )}
            >
              {state === "done" ? (
                <>
                  <Icon name="check" size={14} className="shrink-0" />
                  <span className="sr-only">Done:</span>
                </>
              ) : (
                <span className="text-xs">{number}</span>
              )}
              {label}
            </span>
          </li>
        );
      })}
    </ol>
  );
}

import { useEffect, useRef, type ReactNode } from "react";

import { cn } from "../../lib/cn";
import { Icon } from "./Icon";
import { sectionTitleClassName } from "./typography";

type DialogProps = {
  open: boolean;
  onClose: () => void;
  title: string;
  description?: string;
  children?: ReactNode;
  footer?: ReactNode;
};

/**
 * A modal dialog built on the native `<dialog>` element.
 *
 * The native element gives focus trapping, Escape to close, an inert
 * background and top layer rendering for free, so no dialog library is
 * needed. `showModal` is used when it exists and the `open` attribute is
 * used as the fallback, which keeps the component working in test
 * environments without dialog support.
 */
export function Dialog({
  open,
  onClose,
  title,
  description,
  children,
  footer,
}: DialogProps) {
  const dialogRef = useRef<HTMLDialogElement>(null);

  useEffect(() => {
    const dialog = dialogRef.current;
    if (dialog === null) return;
    if (typeof dialog.showModal === "function") {
      if (open && !dialog.open) dialog.showModal();
      else if (!open && dialog.open) dialog.close();
      return;
    }
    dialog.open = open;
  }, [open]);

  return (
    <dialog
      ref={dialogRef}
      aria-label={title}
      onClose={onClose}
      onCancel={(event) => {
        event.preventDefault();
        dialogRef.current?.close();
      }}
      className={cn(
        "m-auto w-[min(28rem,calc(100vw-2rem))] rounded-xl border border-hairline",
        "bg-canvas p-0 text-ink shadow-4 backdrop:bg-ink/40",
      )}
    >
      <div className="flex flex-col gap-4 p-6">
        <div className="flex items-start justify-between gap-4">
          <div className="flex flex-col gap-1">
            <h2 className={sectionTitleClassName()}>{title}</h2>
            {description !== undefined && (
              <p className="text-sm text-steel">{description}</p>
            )}
          </div>
          <button
            type="button"
            onClick={() => dialogRef.current?.close()}
            aria-label="Close"
            className="-m-2 inline-flex h-11 w-11 items-center justify-center rounded-lg text-steel transition-colors duration-150 hover:bg-surface hover:text-ink focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary"
          >
            <Icon name="x" size={18} />
          </button>
        </div>

        {children}

        {footer !== undefined && (
          <div className="flex flex-wrap justify-end gap-3 border-t border-hairline pt-4">
            {footer}
          </div>
        )}
      </div>
    </dialog>
  );
}

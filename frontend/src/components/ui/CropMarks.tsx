import { cn } from "../../lib/cn";

export function CropMarks({ className }: { className?: string }) {
  return (
    <div
      aria-hidden="true"
      className={cn("pointer-events-none absolute inset-4", className)}
    >
      <span className="absolute -left-px -top-px h-5 w-5 border-l border-t border-stone/70" />
      <span className="absolute -right-px -top-px h-5 w-5 border-r border-t border-stone/70" />
      <span className="absolute -bottom-px -left-px h-5 w-5 border-b border-l border-stone/70" />
      <span className="absolute -bottom-px -right-px h-5 w-5 border-b border-r border-stone/70" />
    </div>
  );
}

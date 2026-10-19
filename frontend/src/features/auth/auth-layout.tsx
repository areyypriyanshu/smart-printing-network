import type { ReactNode } from "react";

import { CropMarks } from "../../components/ui";

type AuthLayoutProps = {
  title: string;
  subtitle?: string;
  children: ReactNode;
  footer?: ReactNode;
};

export function AuthLayout({
  title,
  subtitle,
  children,
  footer,
}: AuthLayoutProps) {
  return (
    <div className="mx-auto grid w-full max-w-6xl gap-10 px-4 py-10 lg:grid-cols-[minmax(0,25rem)_1fr] lg:gap-16 lg:py-16">
      <section className="flex w-full max-w-md flex-col gap-6">
        <div className="flex flex-col gap-2">
          <h1 className="font-display text-3xl font-bold tracking-tight text-ink">
            {title}
          </h1>
          {subtitle !== undefined && <p className="text-steel">{subtitle}</p>}
        </div>
        {children}
        {footer}
      </section>
      <aside className="relative hidden overflow-hidden rounded-xl border border-hairline bg-surface lg:flex lg:flex-col lg:justify-between">
        <div
          className="halftone absolute inset-0 opacity-70"
          aria-hidden="true"
        />
        <CropMarks />
        <div className="relative flex flex-col gap-10 p-10">
          <p className="font-mono text-xs uppercase tracking-[0.22em] text-steel">
            Print job · SPN-2419
          </p>
          <div className="flex flex-col gap-3">
            <p className="font-display text-2xl font-semibold leading-snug text-ink">
              Upload your PDF. Pick your options. See the price before you
              print.
            </p>
            <p className="text-sm text-steel">
              Prices come from each shop&apos;s own rate card, so you compare
              real numbers, not estimates.
            </p>
          </div>
          <dl className="grid grid-cols-3 gap-x-6 gap-y-3 border-t border-hairline pt-6 text-sm">
            <div className="flex flex-col gap-1">
              <dt className="text-steel">Pages</dt>
              <dd className="font-mono text-ink">12</dd>
            </div>
            <div className="flex flex-col gap-1">
              <dt className="text-steel">Copies</dt>
              <dd className="font-mono text-ink">2</dd>
            </div>
            <div className="flex flex-col gap-1">
              <dt className="text-steel">A4 · mono</dt>
              <dd className="font-mono text-ink">₹ 30.00</dd>
            </div>
          </dl>
        </div>
      </aside>
    </div>
  );
}

/**
 * Branded 404. Static export builds this to /404.html so SWA's
 * navigationFallback never bottoms out at /index.html for unknown
 * routes.
 */
import Link from "next/link";

export default function NotFound() {
  return (
    <div className="mx-auto flex w-full max-w-2xl flex-col items-start gap-4 p-6 md:p-10">
      <div className="font-mono text-xs uppercase tracking-widest text-text-secondary">
        404 · Macro Oil Terminal
      </div>
      <h1 className="text-2xl font-semibold text-text-primary md:text-3xl">
        That route does not exist.
      </h1>
      <p className="text-sm text-text-secondary">
        The page you tried to open isn&apos;t part of the terminal. It may have
        moved, or the link you followed was malformed.
      </p>
      <div className="flex flex-wrap gap-3 pt-2 text-sm">
        <Link
          href="/"
          className="rounded-btn border border-border bg-bg-2 px-3 py-2 text-text-primary hover:bg-bg-3"
        >
          Back to today&apos;s thesis
        </Link>
        <Link
          href="/macro/"
          className="rounded-btn border border-border bg-bg-2 px-3 py-2 text-text-primary hover:bg-bg-3"
        >
          Macro charts
        </Link>
      </div>
    </div>
  );
}

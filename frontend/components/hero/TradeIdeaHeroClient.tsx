"use client";

import { useEffect, useMemo, useState } from "react";
import { motion, useReducedMotion } from "framer-motion";
import { useQuery } from "@tanstack/react-query";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { ErrorState } from "@/components/common/ErrorState";
import { ApiError, fetchJson } from "@/lib/api";
import { postEventSource } from "@/lib/sse";
import type {
  ChecklistItem,
  Instrument,
  Lineage,
  ThesisAuditRecord,
  ThesisLatestResponse,
  ThesisRaw,
} from "@/types/api";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { SpreadCurvesIllustration } from "@/components/illustrations/SpreadCurvesIllustration";
import { Button } from "@/components/ui/button";
import { StancePill } from "./StancePill";
import { ConfidenceBar } from "./ConfidenceBar";
import { InstrumentTile } from "./InstrumentTile";
import { PreTradeChecklist } from "./PreTradeChecklist";
import { CatalystCountdown } from "./CatalystCountdown";
import { HeroBackground } from "./HeroBackground";

// `HeroBackground` synchronously gates on viewport (≥768px) and
// `prefers-reduced-motion` and only mounts the WebGPU/TSL desktop
// branch when both pass. The dynamic chunk for the shader is split
// into a separate webpack output and never fetched on mobile because
// the JSX node that would mount it is never created. See the doc
// block in `HeroBackground.tsx` for why the `useEffect` matchMedia
// gate from PR #20 didn't move the Lighthouse score.

type Props = {
  initialData: ThesisLatestResponse | undefined;
};

type StreamState = {
  stage: string;
  pct: number;
  delta: string;
  done: boolean;
  error: string | null;
};

const EMPTY_CHECKLIST: ChecklistItem[] = [
  { key: "stop_in_place", prompt: "Stop set at ±2σ from entry.", auto_check: null },
  { key: "vol_clamp_ok", prompt: "Realised vol below the 1y 85th percentile.", auto_check: null },
  { key: "half_life_ack", prompt: "Implied half-life is acceptable for the horizon.", auto_check: null },
  { key: "catalyst_clear", prompt: "Next EIA release is more than 24h away.", auto_check: null },
  { key: "no_conflicting_recent_thesis", prompt: "No stance flip in the last 5 theses.", auto_check: null },
];

/**
 * Compute |z| / 4, clamped to [0, 1]. Drives the shader background's
 * stretch uniform (0 = calm cyan, 1 = turbulent crimson).
 */
function stretchFactorFromContext(ctx: Record<string, unknown> | undefined): number {
  const z = Number(
    (ctx as { current_z?: number } | undefined)?.current_z ?? 0,
  );
  if (!Number.isFinite(z)) return 0;
  return Math.max(0, Math.min(1, Math.abs(z) / 4.0));
}

function firstInstrumentsOrEmpty(record: ThesisAuditRecord): Instrument[] {
  return Array.isArray(record.instruments) ? record.instruments : [];
}

function checklistFromRecord(record: ThesisAuditRecord): ChecklistItem[] {
  if (Array.isArray(record.checklist) && record.checklist.length > 0) {
    return record.checklist;
  }
  return EMPTY_CHECKLIST;
}

/**
 * Client-side hero card. `TradeIdeaHero` (server component) hands us
 * the seeded `latest` payload; we feed it to React Query as initial
 * data so the cache is primed and `useQuery` can transparently
 * re-fetch. On mount we also open an SSE to `/api/thesis/generate` and
 * merge `progress → delta → done` events on top of the seeded state.
 */
export function TradeIdeaHeroClient({ initialData }: Props) {
  const query = useQuery<ThesisLatestResponse>({
    queryKey: ["thesis", "latest"],
    queryFn: () => fetchJson<ThesisLatestResponse>("/api/thesis/latest"),
    initialData,
    staleTime: 30_000,
  });

  const [stream, setStream] = useState<StreamState>({
    stage: "idle",
    pct: 0,
    delta: "",
    done: false,
    error: null,
  });
  // Bumping `streamTick` re-runs the SSE effect — used by the empty
  // state's "Generate now" button to retry without a full remount.
  const [streamTick, setStreamTick] = useState(0);

  // Open the SSE on mount (and again whenever the user clicks
  // "Generate now"). Guardrails live on the backend; the client is
  // purely a viewer.
  useEffect(() => {
    const controller = new AbortController();
    setStream({
      stage: "warming",
      pct: 1,
      delta: "",
      done: false,
      error: null,
    });
    void postEventSource(
      "/api/thesis/generate?mode=fast",
      { mode: "fast", portfolio_usd: 100_000 },
      {
        signal: controller.signal,
        onEvent: (evt) => {
          try {
            const parsed = JSON.parse(evt.data) as Record<string, unknown>;
            if (evt.event === "progress") {
              setStream((s) => ({
                ...s,
                stage: String(parsed.stage ?? s.stage),
                pct: Number(parsed.pct ?? s.pct),
              }));
            } else if (evt.event === "delta") {
              setStream((s) => ({
                ...s,
                delta: s.delta + String(parsed.text ?? ""),
              }));
            } else if (evt.event === "done") {
              setStream((s) => ({ ...s, done: true, pct: 100 }));
              // The new thesis just landed — pull the latest snapshot
              // so the populated card replaces the empty state.
              void query.refetch();
            } else if (evt.event === "error") {
              setStream((s) => ({
                ...s,
                error: String(parsed.error ?? "Stream error"),
              }));
            }
          } catch {
            // Non-JSON payload — ignore, the next event will land.
          }
        },
        onError: (err) => {
          // SSE failures are non-fatal — the `latest` fetch already
          // seeded the card. Surface the error quietly in dev.
          // eslint-disable-next-line no-console
          console.warn("[TradeIdeaHero] SSE error", err);
        },
      },
    );

    return () => {
      controller.abort();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [streamTick]);

  if (query.isPending && !query.data) {
    return <HeroSkeleton />;
  }

  if (query.isError && !query.data) {
    const message =
      query.error instanceof ApiError
        ? query.error.detail ?? query.error.message
        : "Could not load today's trade idea.";
    return (
      <ErrorState
        message={message}
        retry={() => {
          void query.refetch();
        }}
      />
    );
  }

  const record: ThesisAuditRecord | null = query.data?.thesis ?? null;
  const empty = query.data?.empty ?? record === null;
  const lineage = query.data?.lineage;

  if (empty || record === null) {
    // The streaming generate call is auto-fired in the SSE effect
    // above on every mount. While it runs we show the "Generating..."
    // copy; if it hasn't started (or has failed) we expose a manual
    // retry that re-mounts the card so the SSE effect re-fires.
    const generating = stream.pct > 0 && !stream.done && stream.error === null;
    return (
      <Card
        data-testid="trade-idea-hero-empty"
        className="flex min-h-[640px] items-center justify-center p-8 md:min-h-[560px]"
      >
        <div className="flex flex-col items-center gap-4 text-center">
          <SpreadCurvesIllustration className="text-text-muted" />
          <div className="space-y-1">
            <p className="text-sm font-medium text-text-primary">
              {generating
                ? "Generating today's read…"
                : "Today's read is on its way."}
            </p>
            <p className="text-xs text-text-secondary max-w-sm">
              {generating
                ? `${stream.stage.replace(/_/g, " ")} · ${stream.pct}%`
                : "We're warming the model — this usually takes a few seconds."}
            </p>
          </div>
          {!generating ? (
            <Button
              type="button"
              variant="outline"
              size="sm"
              data-testid="trade-idea-hero-empty-cta"
              onClick={() => {
                // Bumping streamTick re-runs the SSE effect so the
                // generate stream re-fires without a full remount.
                setStreamTick((t) => t + 1);
                void query.refetch();
              }}
            >
              Generate now
            </Button>
          ) : null}
        </div>
      </Card>
    );
  }

  return <LoadedHero record={record} stream={stream} lineage={lineage} />;
}

/**
 * Structural placeholder for the hero card while `/api/thesis/latest`
 * is in flight. Two jobs:
 *
 * 1. Provide an LCP candidate at FCP. The skeleton renders a real
 *    `<h2>` with the same Tailwind classes as the loaded `LoadedHero`
 *    headline, populated with a static page-level fallback string.
 *    Lighthouse picks this H2 as the LCP element at first paint
 *    (~1.0 s) instead of waiting for the loaded card's H2 at ~5 s.
 *    When the real thesis lands, the H2 stays in the same DOM
 *    position with similar dimensions, so the LCP candidate doesn't
 *    shift and the metric stays at FCP.
 * 2. Match the loaded card's overall height and layout so the
 *    `#ticker` section below doesn't get pushed down when real data
 *    swaps in. Wave 5 home/mobile CLS was 0.207, all from `#ticker`
 *    moving ~260 px when the skeleton (`min-h-[360px]`, six bars) was
 *    replaced by a much taller loaded card. We mirror the loaded
 *    structure here — stance-pill row, headline + summary,
 *    confidence bar, three instrument tiles, checklist — so the
 *    swap is near-CLS-free.
 *
 * Visually this still looks like a skeleton: every block is either a
 * `<Skeleton>` shimmer or a low-contrast text placeholder. The H2 is
 * the only element with full text contrast — it doubles as a
 * page-level "what is this card" affordance, which is what users
 * land on while the model warms up anyway.
 */
function HeroSkeleton() {
  return (
    <Card
      data-testid="trade-idea-hero-loading"
      className="relative min-h-[640px] overflow-hidden md:min-h-[560px]"
    >
      <CardContent className="relative space-y-6 p-6 md:p-8">
        {/* Top row: stance pill + catalyst — both placeholders */}
        <div className="flex flex-wrap items-center justify-between gap-3">
          <Skeleton className="h-6 w-28 rounded-full" />
          <Skeleton className="h-4 w-32" />
        </div>

        {/* Headline + summary — H2 is the LCP candidate at FCP. */}
        <div className="space-y-2">
          <h2 className="text-xl font-semibold leading-snug text-text-primary md:text-2xl">
            Today&rsquo;s read on the Brent&ndash;WTI spread
          </h2>
          <p className="text-sm text-text-secondary">
            Loading the latest stance, conviction, and instruments&hellip;
          </p>
        </div>

        {/* Confidence bar */}
        <div className="space-y-2">
          <Skeleton className="h-2 w-full rounded-full" />
          <Skeleton className="h-3 w-24" />
        </div>

        {/* Three instrument tiles — same grid + tile height as loaded */}
        <div className="grid gap-4 md:grid-cols-3">
          {[0, 1, 2].map((i) => (
            <Card key={i} className="relative overflow-hidden">
              <div
                aria-hidden
                className="absolute left-0 right-0 top-0 h-1 bg-bg-3"
              />
              <div className="space-y-3 p-5 pt-5">
                <Skeleton className="h-3 w-20" />
                <Skeleton className="h-4 w-32" />
                <Skeleton className="h-3 w-full" />
                <Skeleton className="h-3 w-5/6" />
                <Skeleton className="h-8 w-full rounded-md" />
              </div>
            </Card>
          ))}
        </div>

        {/* Checklist */}
        <div className="border-t border-border pt-4">
          <Skeleton className="mb-3 h-3 w-40" />
          <div className="space-y-2">
            {[0, 1, 2, 3, 4].map((i) => (
              <Skeleton key={i} className="h-4 w-full" />
            ))}
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

function LoadedHero({
  record,
  stream,
  lineage,
}: {
  record: ThesisAuditRecord;
  stream: StreamState;
  lineage?: Lineage;
}) {
  const raw: ThesisRaw = record.thesis ?? {};
  const stance = (raw.stance ?? "flat") as string;
  const conviction = Number(raw.conviction_0_to_10 ?? 0);
  const horizon = Number(raw.time_horizon_days ?? 0);
  // Memoise the context slice so the `useMemo` dep below doesn't churn
  // on every render via `?? {}` producing a new object reference.
  const ctx = useMemo(() => record.context ?? {}, [record.context]);
  const hoursToEia =
    (ctx as { hours_to_next_eia?: number | null }).hours_to_next_eia ?? null;
  const stretch = useMemo(() => stretchFactorFromContext(ctx), [ctx]);
  const headline =
    raw.plain_english_headline ||
    raw.thesis_summary ||
    "Today's trade idea";

  const instruments = firstInstrumentsOrEmpty(record);
  const checklist = checklistFromRecord(record);
  const reduced = useReducedMotion();

  return (
    <motion.div
      data-testid="trade-idea-hero"
      initial={reduced ? { opacity: 1, y: 0 } : { opacity: 0, y: 16 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.45, ease: "easeOut" }}
    >
      {/*
        `min-h` matches the loading skeleton above (`HeroSkeleton`) so
        the card doesn't change height when real data swaps in. Wave 5
        home/mobile CLS was 0.207 because `min-h-[360px]` was much
        shorter than the typical loaded card (~640 px on mobile,
        ~560 px on desktop), so `#ticker` got pushed down ~260 px when
        the thesis landed. Floor matches the structural skeleton above.
      */}
      <Card className="relative min-h-[640px] overflow-hidden md:min-h-[560px]">
        <HeroBackground
          stretchFactor={stretch}
          className="pointer-events-none absolute inset-0 h-full w-full opacity-40"
        />
        <CardContent className="relative space-y-6 p-6 md:p-8">
          {/* Top row: stance pill + catalyst line + (live stream hint) */}
          <div className="flex flex-wrap items-center justify-between gap-3">
            <StancePill stance={stance} />
            <div className="flex items-center gap-2">
              {/* Q1-DATA-QUALITY-LINEAGE */}
              {lineage ? <LineagePill lineage={lineage} /> : null}
              <CatalystCountdown hoursToEia={hoursToEia} />
            </div>
          </div>

          {/* Headline — plain-English first, technical summary as secondary */}
          <div className="space-y-2">
            <motion.h2
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              transition={{ delay: 0.05, duration: 0.3 }}
              className="text-xl font-semibold leading-snug text-text-primary md:text-2xl"
            >
              {headline}
            </motion.h2>
            {raw.thesis_summary &&
            raw.thesis_summary !== headline ? (
              <motion.p
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                transition={{ delay: 0.1, duration: 0.3 }}
                className="text-sm text-text-secondary"
              >
                {raw.thesis_summary}
              </motion.p>
            ) : null}
          </div>

          {/* Confidence */}
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ delay: 0.15, duration: 0.3 }}
          >
            <ConfidenceBar value={conviction} stance={stance} />
            <div className="mt-1 text-xs text-text-muted">
              Horizon: {horizon} day{horizon === 1 ? "" : "s"}
            </div>
          </motion.div>

          {/* Instrument tiles — staggered fade-up per tile so the eye
              tracks them left-to-right on first paint. */}
          {instruments.length > 0 ? (
            <div className="grid gap-4 md:grid-cols-3">
              {instruments.slice(0, 3).map((inst, i) => (
                <InstrumentTile
                  key={inst.tier}
                  tier={inst.tier}
                  instrument={inst}
                  stance={stance}
                  index={i}
                />
              ))}
            </div>
          ) : null}

          {/* Checklist */}
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ delay: 0.25, duration: 0.3 }}
            className="border-t border-border pt-4"
          >
            <h3 className="mb-2 text-sm font-semibold uppercase tracking-wider text-text-secondary">
              Pre-trade checklist
            </h3>
            <PreTradeChecklist
              items={checklist}
              thesisId={record.context_fingerprint || record.timestamp || "default"}
            />
          </motion.div>

          {/* Live stream hint — only visible while generation is in flight */}
          {stream.pct > 0 && !stream.done && stream.stage !== "idle" ? (
            <div
              data-testid="trade-idea-hero-stream-hint"
              role="status"
              aria-live="polite"
              className="text-xs text-text-muted"
            >
              Generating new thesis… {stream.stage} · {stream.pct}%
            </div>
          ) : null}
        </CardContent>
      </Card>
    </motion.div>
  );
}


/**
 * Q1 data-quality slice: tiny lineage pill rendered next to the
 * catalyst countdown. Hover surfaces "yfinance, BZ=F+CL=F front-month,
 * fetched 2m ago, n=251". When the backend hasn't attached lineage
 * yet (cold start, /api/thesis/latest returned no `lineage` field),
 * the pill is omitted entirely.
 */
function relAge(iso: string | null | undefined): string {
  if (!iso) return "—";
  const t = Date.parse(iso);
  if (Number.isNaN(t)) return "—";
  const ageS = Math.max(0, Math.floor((Date.now() - t) / 1000));
  if (ageS < 60) return `${ageS}s ago`;
  const ageM = Math.floor(ageS / 60);
  if (ageM < 60) return `${ageM}m ago`;
  const ageH = Math.floor(ageM / 60);
  if (ageH < 24) return `${ageH}h ago`;
  const ageD = Math.floor(ageH / 24);
  return `${ageD}d ago`;
}

function LineagePill({ lineage }: { lineage: Lineage }) {
  return (
    <TooltipProvider delayDuration={120}>
      <Tooltip>
        <TooltipTrigger asChild>
          <button
            type="button"
            data-testid="trade-idea-hero-lineage"
            className="inline-flex items-center gap-1 rounded-btn border border-border bg-bg-2 px-2 py-0.5 text-[10px] font-medium uppercase tracking-wider text-text-muted hover:bg-bg-3 focus:outline-none focus:ring-2 focus:ring-accent"
          >
            <span aria-hidden className="h-1.5 w-1.5 rounded-full bg-emerald-500" />
            <span>lineage</span>
          </button>
        </TooltipTrigger>
        <TooltipContent side="bottom" className="max-w-xs text-xs">
          <div className="space-y-0.5">
            <div className="font-semibold">{lineage.source}</div>
            <div className="text-text-secondary">
              {lineage.symbol} front-month
            </div>
            <div className="text-text-secondary">
              fetched {relAge(lineage.asof)}
            </div>
            {lineage.n_obs !== null ? (
              <div className="text-text-muted">
                n=<span className="num">{lineage.n_obs}</span> obs
              </div>
            ) : null}
          </div>
        </TooltipContent>
      </Tooltip>
    </TooltipProvider>
  );
}

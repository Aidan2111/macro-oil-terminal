"use client";

import { useEffect, useMemo, useState } from "react";
import { motion, useReducedMotion } from "framer-motion";
import { useQuery } from "@tanstack/react-query";
import { Card, CardContent } from "@/components/ui/card";
import { ErrorState } from "@/components/common/ErrorState";
import { LoadingSkeleton } from "@/components/common/LoadingSkeleton";
import { ApiError, fetchJson } from "@/lib/api";
import { postEventSource } from "@/lib/sse";
import type {
  ChecklistItem,
  Instrument,
  ThesisAuditRecord,
  ThesisLatestResponse,
  ThesisRaw,
} from "@/types/api";
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
    return (
      <Card
        data-testid="trade-idea-hero-loading"
        className="min-h-[360px] p-6"
      >
        <LoadingSkeleton lines={6} height="h-5" />
      </Card>
    );
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

  if (empty || record === null) {
    // The streaming generate call is auto-fired in the SSE effect
    // above on every mount. While it runs we show the "Generating..."
    // copy; if it hasn't started (or has failed) we expose a manual
    // retry that re-mounts the card so the SSE effect re-fires.
    const generating = stream.pct > 0 && !stream.done && stream.error === null;
    return (
      <Card
        data-testid="trade-idea-hero-empty"
        className="min-h-[360px] flex items-center justify-center p-8"
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

  return <LoadedHero record={record} stream={stream} />;
}

function LoadedHero({
  record,
  stream,
}: {
  record: ThesisAuditRecord;
  stream: StreamState;
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
        `min-h-[360px]` matches the loading skeleton above, so the card
        height doesn't jump between loading→loaded→empty states. Wave 5
        Lighthouse home/mobile CLS was 0.207 (score 0.6) entirely from
        the `#ticker` section being pushed down when the loaded hero
        settled at a different height than the skeleton. Locking the
        floor here removes the shift.
      */}
      <Card className="relative min-h-[360px] overflow-hidden">
        <HeroBackground
          stretchFactor={stretch}
          className="pointer-events-none absolute inset-0 h-full w-full opacity-40"
        />
        <CardContent className="relative space-y-6 p-6 md:p-8">
          {/* Top row: stance pill + catalyst line + (live stream hint) */}
          <div className="flex flex-wrap items-center justify-between gap-3">
            <StancePill stance={stance} />
            <CatalystCountdown hoursToEia={hoursToEia} />
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

"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { motion } from "framer-motion";
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
import { StancePill } from "./StancePill";
import { ConfidenceBar } from "./ConfidenceBar";
import { InstrumentTile } from "./InstrumentTile";
import { PreTradeChecklist } from "./PreTradeChecklist";
import { CatalystCountdown } from "./CatalystCountdown";
import { HeroShaderBackground } from "./HeroShaderBackground";

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
  { key: "stop_in_place", prompt: "I have a stop at ±2σ spread move from entry.", auto_check: null },
  { key: "vol_clamp_ok", prompt: "Spread realised vol is below the 1y 85th percentile.", auto_check: null },
  { key: "half_life_ack", prompt: "I understand the implied half-life is ~N days.", auto_check: null },
  { key: "catalyst_clear", prompt: "No EIA release within the next 24 hours.", auto_check: null },
  { key: "no_conflicting_recent_thesis", prompt: "No stance flip in the last 5 thesis entries.", auto_check: null },
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
  const streamStartedRef = useRef(false);

  // Open the SSE exactly once per mount. Guardrails live on the
  // backend; the client is purely a viewer.
  useEffect(() => {
    if (streamStartedRef.current) return;
    streamStartedRef.current = true;

    const controller = new AbortController();
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
  }, []);

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
    return (
      <Card
        data-testid="trade-idea-hero-empty"
        className="min-h-[200px] flex items-center justify-center p-8"
      >
        <div className="text-center text-text-secondary">
          <p className="text-sm">
            No trade thesis generated yet. Kick off the stream via{" "}
            <code>POST /api/thesis/generate</code>.
          </p>
          {stream.pct > 0 && !stream.done ? (
            <p className="mt-2 text-xs text-text-muted">
              Streaming: {stream.stage} · {stream.pct}%
            </p>
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

  return (
    <motion.div
      data-testid="trade-idea-hero"
      initial={{ opacity: 0, y: 16 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.45, ease: "easeOut" }}
    >
      <Card className="relative overflow-hidden">
        <HeroShaderBackground
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

          {/* Instrument tiles */}
          {instruments.length > 0 ? (
            <motion.div
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.2, duration: 0.35 }}
              className="grid gap-4 md:grid-cols-3"
            >
              {instruments.slice(0, 3).map((inst) => (
                <InstrumentTile
                  key={inst.tier}
                  tier={inst.tier}
                  instrument={inst}
                  stance={stance}
                />
              ))}
            </motion.div>
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

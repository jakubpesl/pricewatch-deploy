"use client";
import { useEffect } from "react";
import { useQuery } from "@tanstack/react-query";
import { CheckCircle2, Loader2, Circle, Clock } from "lucide-react";
import type { DiscoveryJob } from "@/types/api";

const SOURCES: { key: string; label: string; flag: string }[] = [
  { key: "heureka",         label: "Heureka",          flag: "🇨🇿🇸🇰" },
  { key: "idealo",          label: "Idealo",            flag: "🇩🇪🇦🇹🇫🇷🇮🇹🇬🇧" },
  { key: "google_shopping", label: "Google Shopping",   flag: "🌍" },
  { key: "google_organic",  label: "Google Search",     flag: "🌍" },
  { key: "zbozi",           label: "Zboží.cz",          flag: "🇨🇿" },
  { key: "geizhals",        label: "Geizhals",          flag: "🇦🇹🇩🇪" },
  { key: "bing_shopping",   label: "Bing Shopping",     flag: "🌍" },
  { key: "ceneo",           label: "Ceneo",             flag: "🇵🇱" },
];

interface Props {
  jobId: number;
  onComplete: () => void;
}

export function JobProgressBar({ jobId, onComplete }: Props) {
  const { data: job } = useQuery<DiscoveryJob>({
    queryKey: ["job", jobId],
    queryFn: async () => {
      const res = await fetch(`/api/backend/v1/jobs/${jobId}`);
      return res.json();
    },
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      if (status === "completed" || status === "failed") return false;
      return 2000;
    },
  });

  useEffect(() => {
    if (job?.status === "completed") onComplete();
  }, [job?.status, onComplete]);

  if (!job) return null;

  const isRunning = job.status === "pending" || job.status === "running";
  const isDone = job.status === "completed";
  const isFailed = job.status === "failed";
  const completed = new Set(job.sources_completed ?? []);
  const progress = completed.size / SOURCES.length;

  // First source not yet completed = currently scanning
  const currentIdx = isRunning
    ? SOURCES.findIndex((s) => !completed.has(s.key))
    : -1;

  return (
    <div className="card p-6 max-w-2xl mx-auto space-y-5">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          {isRunning && <Loader2 className="w-5 h-5 text-violet-500 animate-spin" />}
          {isDone && <CheckCircle2 className="w-5 h-5 text-emerald-500" />}
          <span className="font-semibold text-slate-900">
            {isRunning && "Searching European markets…"}
            {isDone && `Done — found ${job.retailers_found} stores`}
            {isFailed && "Search failed"}
          </span>
        </div>
        {isRunning && (
          <span className="text-xs text-slate-400 tabular-nums">
            {completed.size} / {SOURCES.length} sources
          </span>
        )}
        {isDone && (
          <span className="text-sm text-emerald-600 font-medium">{job.retailers_found} stores</span>
        )}
      </div>

      {/* Progress bar */}
      <div className="h-2 bg-slate-100 rounded-full overflow-hidden">
        <div
          className="h-full bg-gradient-to-r from-violet-500 to-indigo-400 rounded-full transition-all duration-700"
          style={{ width: `${isDone ? 100 : Math.max(progress * 100, 4)}%` }}
        />
      </div>

      {/* Source list */}
      <div className="space-y-1">
        {SOURCES.map(({ key, label, flag }, idx) => {
          const done = completed.has(key);
          const active = idx === currentIdx;
          const waiting = !done && !active;

          return (
            <div
              key={key}
              className={`flex items-center gap-3 px-3 py-2 rounded-lg transition-all duration-300 ${
                active ? "bg-violet-50 border border-violet-100" : ""
              }`}
            >
              {/* Icon */}
              <div className="w-5 flex-shrink-0 flex justify-center">
                {done && <CheckCircle2 className="w-4 h-4 text-emerald-500" />}
                {active && <Loader2 className="w-4 h-4 text-violet-500 animate-spin" />}
                {waiting && !isDone && <Circle className="w-4 h-4 text-slate-300" />}
                {waiting && isDone && <Circle className="w-4 h-4 text-slate-200" />}
              </div>

              {/* Label */}
              <span className={`text-sm flex-1 ${
                done ? "text-slate-700 font-medium" :
                active ? "text-violet-700 font-semibold" :
                "text-slate-400"
              }`}>
                <span className="mr-1.5">{flag}</span>{label}
              </span>

              {/* Status badge */}
              {done && (
                <span className="text-xs text-emerald-600 bg-emerald-50 px-2 py-0.5 rounded-full">
                  Done
                </span>
              )}
              {active && (
                <span className="text-xs text-violet-600 bg-violet-50 px-2 py-0.5 rounded-full animate-pulse">
                  Scanning…
                </span>
              )}
              {waiting && isRunning && (
                <span className="text-xs text-slate-400 flex items-center gap-1">
                  <Clock className="w-3 h-3" /> Waiting
                </span>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

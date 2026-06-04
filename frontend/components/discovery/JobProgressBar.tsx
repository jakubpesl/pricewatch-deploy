"use client";
import { useEffect } from "react";
import { useQuery } from "@tanstack/react-query";
import { CheckCircle2, Loader2 } from "lucide-react";
import type { DiscoveryJob } from "@/types/api";

const SOURCE_LABELS: Record<string, string> = {
  heureka: "Heureka CZ/SK",
  idealo: "Idealo DE/AT/FR/IT/ES/GB/PL",
  google_shopping: "Google Shopping (16 markets)",
  google_organic: "Google organic results",
  zbozi: "Zboží.cz",
  geizhals: "Geizhals AT/DE",
  bing_shopping: "Bing Shopping",
  ceneo: "Ceneo.pl",
};

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
      return 2000; // poll every 2 seconds
    },
  });

  useEffect(() => {
    if (job?.status === "completed") {
      onComplete();
    }
  }, [job?.status, onComplete]);

  if (!job) return null;

  const isRunning = job.status === "pending" || job.status === "running";
  const isDone = job.status === "completed";
  const isFailed = job.status === "failed";
  const sources = job.sources_completed ?? [];

  return (
    <div className="card p-6 max-w-2xl mx-auto space-y-4">
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
        {isDone && (
          <span className="text-sm text-emerald-600 font-medium">
            {job.retailers_found} stores
          </span>
        )}
      </div>

      {/* Source progress */}
      <div className="space-y-2">
        {Object.entries(SOURCE_LABELS).map(([key, label]) => {
          const done = sources.includes(key);
          return (
            <div key={key} className="flex items-center gap-3 text-sm">
              <div className={`w-4 h-4 rounded-full flex-shrink-0 ${
                done ? "bg-emerald-400" : isRunning ? "bg-slate-200 animate-pulse" : "bg-slate-200"
              }`} />
              <span className={done ? "text-slate-700" : "text-slate-400"}>{label}</span>
              {done && <span className="ml-auto text-xs text-slate-400">✓</span>}
            </div>
          );
        })}
      </div>

      {/* Animated progress bar */}
      {isRunning && (
        <div className="h-1.5 bg-slate-100 rounded-full overflow-hidden">
          <div
            className="h-full bg-gradient-to-r from-violet-500 to-indigo-400 rounded-full transition-all duration-500"
            style={{ width: `${sources.length > 0 ? (sources.length / Object.keys(SOURCE_LABELS).length) * 100 : 10}%` }}
          />
        </div>
      )}
    </div>
  );
}

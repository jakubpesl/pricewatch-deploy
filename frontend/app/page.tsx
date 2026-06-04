"use client";
import { useState, useCallback } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Search, Loader2, Globe, TrendingDown, Store } from "lucide-react";
import { DiscoveryResults } from "@/components/discovery/DiscoveryResults";
import { JobProgressBar } from "@/components/discovery/JobProgressBar";
import type { DiscoveryJob } from "@/types/api";

const EXAMPLE_MODELS = [
  "Samsung QE65Q80C",
  "LG OLED55C34LA",
  "iPhone 15 Pro",
  "PlayStation 5",
  "Sony WH-1000XM5",
  "Dyson V15 Detect",
];

export default function HomePage() {
  const [modelNumber, setModelNumber] = useState("");
  const [activeJobId, setActiveJobId] = useState<number | null>(null);
  const queryClient = useQueryClient();

  const discoverMutation = useMutation({
    mutationFn: async (model: string) => {
      const res = await fetch("/api/backend/v1/discover", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ model_number: model }),
      });
      if (!res.ok) throw new Error("Discovery failed");
      return res.json() as Promise<DiscoveryJob>;
    },
    onSuccess: (job) => {
      setActiveJobId(job.id);
    },
  });

  const handleSearch = useCallback(
    (e: React.FormEvent) => {
      e.preventDefault();
      if (!modelNumber.trim()) return;
      discoverMutation.mutate(modelNumber.trim());
    },
    [modelNumber, discoverMutation]
  );

  const handleJobComplete = useCallback(() => {
    queryClient.invalidateQueries({ queryKey: ["product", modelNumber] });
  }, [queryClient, modelNumber]);

  return (
    <div className="space-y-10">
      {/* Hero */}
      <div className="text-center py-12 space-y-4">
        <h1 className="text-4xl font-bold text-slate-900">
          Find every retailer selling your product
        </h1>
        <p className="text-lg text-slate-500 max-w-xl mx-auto">
          Enter a model number — PriceWatch searches Google Shopping, Heureka, Idealo, Ceneo
          and dozens of price comparators across 16 European markets.
        </p>
      </div>

      {/* Search bar */}
      <form onSubmit={handleSearch} className="max-w-2xl mx-auto">
        <div className="relative flex items-center">
          <Search className="absolute left-4 text-slate-400 w-5 h-5" />
          <input
            type="text"
            value={modelNumber}
            onChange={(e) => setModelNumber(e.target.value)}
            placeholder="Samsung QE65Q80C, iPhone 15 Pro, Dyson V15..."
            className="w-full pl-12 pr-36 py-4 text-lg rounded-2xl border border-slate-200 bg-white
                       shadow-sm focus:outline-none focus:ring-2 focus:ring-violet-500 focus:border-transparent"
          />
          <button
            type="submit"
            disabled={discoverMutation.isPending || !modelNumber.trim()}
            className="absolute right-2 btn-primary flex items-center gap-2 py-2"
          >
            {discoverMutation.isPending ? (
              <><Loader2 className="w-4 h-4 animate-spin" /> Searching…</>
            ) : (
              "Find stores"
            )}
          </button>
        </div>

        {/* Example queries */}
        <div className="mt-3 flex flex-wrap gap-2 justify-center">
          {EXAMPLE_MODELS.map((m) => (
            <button
              key={m}
              type="button"
              onClick={() => setModelNumber(m)}
              className="text-xs px-3 py-1 rounded-full bg-slate-100 text-slate-600
                         hover:bg-violet-50 hover:text-violet-700 transition-colors"
            >
              {m}
            </button>
          ))}
        </div>
      </form>

      {/* Stats row */}
      {!activeJobId && !discoverMutation.isPending && (
        <div className="grid grid-cols-3 gap-6 max-w-2xl mx-auto">
          {[
            { icon: Globe, label: "16 countries", sub: "CZ, SK, DE, AT, PL, FR, IT, GB and more" },
            { icon: Store, label: "10,000+ stores", sub: "From major retailers to small e-shops" },
            { icon: TrendingDown, label: "Real prices", sub: "Live scraping, no paid APIs" },
          ].map(({ icon: Icon, label, sub }) => (
            <div key={label} className="card p-5 text-center">
              <Icon className="w-7 h-7 mx-auto text-violet-500 mb-2" />
              <div className="font-bold text-slate-900">{label}</div>
              <div className="text-xs text-slate-500 mt-1">{sub}</div>
            </div>
          ))}
        </div>
      )}

      {/* Progress bar while running */}
      {activeJobId && (
        <JobProgressBar
          jobId={activeJobId}
          onComplete={handleJobComplete}
        />
      )}

      {/* Results */}
      {activeJobId && (
        <DiscoveryResults modelNumber={modelNumber} jobId={activeJobId} />
      )}

      {discoverMutation.isError && (
        <div className="max-w-2xl mx-auto p-4 bg-red-50 border border-red-200 rounded-xl text-red-700 text-sm">
          Search failed. Please check if the backend is running.
        </div>
      )}
    </div>
  );
}

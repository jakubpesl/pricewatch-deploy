"use client";
import { useState, useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { ExternalLink, TrendingDown, Package, Star, Globe2, ChevronDown } from "lucide-react";
import type { ProductOut, ProductRetailerOut } from "@/types/api";

const COUNTRY_FLAGS: Record<string, string> = {
  CZ: "🇨🇿", SK: "🇸🇰", DE: "🇩🇪", AT: "🇦🇹", PL: "🇵🇱",
  FR: "🇫🇷", IT: "🇮🇹", GB: "🇬🇧", HU: "🇭🇺", RO: "🇷🇴",
  NL: "🇳🇱", BE: "🇧🇪", ES: "🇪🇸", SE: "🇸🇪", DK: "🇩🇰", FI: "🇫🇮",
};

interface Props {
  modelNumber: string;
  jobId: number;
}

type SortKey = "price_asc" | "price_desc" | "country";

export function DiscoveryResults({ modelNumber, jobId }: Props) {
  const [filterCountry, setFilterCountry] = useState("all");
  const [filterStock, setFilterStock] = useState(false);
  const [sortBy, setSortBy] = useState<SortKey>("price_asc");
  const [page, setPage] = useState(0);
  const PAGE_SIZE = 20;

  const { data: product, isLoading } = useQuery<ProductOut>({
    queryKey: ["product", modelNumber],
    queryFn: async () => {
      const res = await fetch(`/api/backend/v1/products/${encodeURIComponent(modelNumber)}`);
      if (!res.ok) throw new Error("Not found");
      return res.json();
    },
    enabled: !!modelNumber,
    refetchInterval: 5000,
  });

  const retailers = product?.retailers ?? [];
  const countries = useMemo(
    () => Array.from(new Set(retailers.map((r) => r.country_code))).sort(),
    [retailers]
  );

  const filtered = useMemo(() => {
    let list = [...retailers];
    if (filterCountry !== "all") list = list.filter((r) => r.country_code === filterCountry);
    if (filterStock) list = list.filter((r) => r.in_stock !== false);
    list.sort((a, b) => {
      if (sortBy === "price_asc") return (a.current_price ?? Infinity) - (b.current_price ?? Infinity);
      if (sortBy === "price_desc") return (b.current_price ?? -Infinity) - (a.current_price ?? -Infinity);
      return a.country_code.localeCompare(b.country_code);
    });
    return list;
  }, [retailers, filterCountry, filterStock, sortBy]);

  const paged = filtered.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE);
  const totalPages = Math.ceil(filtered.length / PAGE_SIZE);

  const cheapest = retailers.filter((r) => r.current_price).sort((a, b) => a.current_price! - b.current_price!)[0];

  if (isLoading) return null;
  if (!product) return null;

  return (
    <div className="space-y-6">
      {/* Summary row */}
      <div className="flex flex-wrap gap-4 items-center justify-between">
        <div>
          <h2 className="text-xl font-bold text-slate-900">{modelNumber}</h2>
          <p className="text-slate-500 text-sm">
            {retailers.length} stores in {countries.length} countries
          </p>
        </div>
        {cheapest && (
          <div className="card px-5 py-3 flex items-center gap-3">
            <TrendingDown className="w-5 h-5 text-emerald-500" />
            <div>
              <div className="text-xs text-slate-500">Cheapest</div>
              <div className="font-bold text-emerald-600">
                {cheapest.current_price?.toLocaleString()} {cheapest.currency}
              </div>
              <div className="text-xs text-slate-500">{cheapest.retailer_name} · {COUNTRY_FLAGS[cheapest.country_code]} {cheapest.country_code}</div>
            </div>
          </div>
        )}
      </div>

      {/* Country price summary cards */}
      <div className="flex gap-3 overflow-x-auto pb-2">
        {countries.map((cc) => {
          const countryRetailers = retailers.filter((r) => r.country_code === cc && r.current_price);
          const min = Math.min(...countryRetailers.map((r) => r.current_price!));
          const currency = countryRetailers[0]?.currency;
          return (
            <button
              key={cc}
              onClick={() => setFilterCountry(filterCountry === cc ? "all" : cc)}
              className={`flex-shrink-0 px-4 py-2 rounded-xl border text-sm transition-all ${
                filterCountry === cc
                  ? "bg-violet-50 border-violet-300 text-violet-800"
                  : "bg-white border-slate-200 text-slate-700 hover:border-violet-200"
              }`}
            >
              <span className="text-base">{COUNTRY_FLAGS[cc]}</span>{" "}
              <span className="font-semibold">{cc}</span>
              {!isNaN(min) && (
                <span className="text-xs text-slate-500 ml-1">
                  from {min.toLocaleString()} {currency}
                </span>
              )}
            </button>
          );
        })}
      </div>

      {/* Filters + sort bar */}
      <div className="flex flex-wrap gap-3 items-center">
        <label className="flex items-center gap-2 text-sm text-slate-600 cursor-pointer">
          <input
            type="checkbox"
            checked={filterStock}
            onChange={(e) => setFilterStock(e.target.checked)}
            className="accent-violet-600"
          />
          In stock only
        </label>
        <div className="ml-auto flex items-center gap-2">
          <span className="text-sm text-slate-500">Sort:</span>
          <select
            value={sortBy}
            onChange={(e) => setSortBy(e.target.value as SortKey)}
            className="text-sm border border-slate-200 rounded-lg px-3 py-1.5 bg-white outline-none focus:border-violet-400"
          >
            <option value="price_asc">Price: lowest first</option>
            <option value="price_desc">Price: highest first</option>
            <option value="country">By country</option>
          </select>
        </div>
        <div className="text-sm text-slate-400">{filtered.length} stores</div>
      </div>

      {/* Retailer table */}
      <div className="card overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead>
              <tr className="border-b border-slate-100 bg-slate-50">
                <th className="px-4 py-3 text-left text-xs font-semibold text-slate-500 uppercase tracking-wider">Store</th>
                <th className="px-4 py-3 text-left text-xs font-semibold text-slate-500 uppercase tracking-wider">Country</th>
                <th className="px-4 py-3 text-right text-xs font-semibold text-slate-500 uppercase tracking-wider">Price</th>
                <th className="px-4 py-3 text-center text-xs font-semibold text-slate-500 uppercase tracking-wider">Stock</th>
                <th className="px-4 py-3 text-left text-xs font-semibold text-slate-500 uppercase tracking-wider">Rating</th>
                <th className="px-4 py-3 text-left text-xs font-semibold text-slate-500 uppercase tracking-wider">Source</th>
                <th className="px-4 py-3"></th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-50">
              {paged.map((retailer) => (
                <RetailerRow key={retailer.id} retailer={retailer} cheapestPrice={cheapest?.current_price ?? undefined} />
              ))}
            </tbody>
          </table>
        </div>

        {/* Pagination */}
        {totalPages > 1 && (
          <div className="px-4 py-3 border-t border-slate-100 flex items-center justify-between">
            <button
              onClick={() => setPage((p) => Math.max(0, p - 1))}
              disabled={page === 0}
              className="px-3 py-1.5 text-sm border border-slate-200 rounded-lg disabled:opacity-40 hover:bg-slate-50"
            >
              ← Back
            </button>
            <span className="text-sm text-slate-500">{page + 1} / {totalPages}</span>
            <button
              onClick={() => setPage((p) => Math.min(totalPages - 1, p + 1))}
              disabled={page >= totalPages - 1}
              className="px-3 py-1.5 text-sm border border-slate-200 rounded-lg disabled:opacity-40 hover:bg-slate-50"
            >
              Next →
            </button>
          </div>
        )}
      </div>
    </div>
  );
}

function RetailerRow({ retailer, cheapestPrice }: { retailer: ProductRetailerOut; cheapestPrice: number | undefined }) {
  const discount = cheapestPrice && retailer.current_price && retailer.current_price > cheapestPrice
    ? ((retailer.current_price - cheapestPrice) / cheapestPrice * 100).toFixed(0)
    : null;

  return (
    <tr className="hover:bg-slate-50 transition-colors group">
      <td className="px-4 py-3">
        <div className="font-medium text-slate-900">{retailer.retailer_name || retailer.retailer_domain}</div>
        <div className="text-xs text-slate-400">{retailer.retailer_domain}</div>
      </td>
      <td className="px-4 py-3">
        <span className="text-base">{COUNTRY_FLAGS[retailer.country_code] ?? "🌐"}</span>{" "}
        <span className="text-sm text-slate-600">{retailer.country_code}</span>
      </td>
      <td className="px-4 py-3 text-right">
        {retailer.current_price ? (
          <div>
            <span className={`font-bold ${discount ? "text-slate-700" : "text-emerald-600"}`}>
              {retailer.current_price.toLocaleString()} {retailer.currency}
            </span>
            {discount && (
              <div className="text-xs text-slate-400">+{discount}% vs cheapest</div>
            )}
          </div>
        ) : (
          <span className="text-slate-400 text-sm">–</span>
        )}
      </td>
      <td className="px-4 py-3 text-center">
        {retailer.in_stock === true && <span className="text-xs px-2 py-0.5 bg-emerald-50 text-emerald-700 rounded-full">In stock</span>}
        {retailer.in_stock === false && <span className="text-xs px-2 py-0.5 bg-red-50 text-red-600 rounded-full">Out of stock</span>}
        {retailer.in_stock === null && <span className="text-xs text-slate-400">?</span>}
      </td>
      <td className="px-4 py-3">
        {retailer.rating && (
          <div className="flex items-center gap-1">
            <Star className="w-3.5 h-3.5 text-amber-400 fill-amber-400" />
            <span className="text-sm font-medium">{retailer.rating.toFixed(1)}</span>
            {retailer.review_count && (
              <span className="text-xs text-slate-400">({retailer.review_count})</span>
            )}
          </div>
        )}
      </td>
      <td className="px-4 py-3">
        <span className="text-xs text-slate-400 bg-slate-100 px-2 py-0.5 rounded-full">
          {retailer.source}
        </span>
      </td>
      <td className="px-4 py-3">
        <a
          href={retailer.product_url}
          target="_blank"
          rel="noopener noreferrer"
          className="opacity-0 group-hover:opacity-100 transition-opacity p-1.5 rounded-lg hover:bg-violet-50 hover:text-violet-600 text-slate-400"
        >
          <ExternalLink className="w-4 h-4" />
        </a>
      </td>
    </tr>
  );
}

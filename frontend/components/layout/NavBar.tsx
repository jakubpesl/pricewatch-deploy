import Link from "next/link";
import { TrendingDown } from "lucide-react";

export function NavBar() {
  return (
    <nav className="bg-white border-b border-slate-200 sticky top-0 z-40">
      <div className="max-w-7xl mx-auto px-4 h-14 flex items-center gap-6">
        <Link href="/" className="flex items-center gap-2 font-bold text-slate-900">
          <TrendingDown className="w-5 h-5 text-violet-600" />
          PriceWatch
        </Link>
        <div className="flex gap-1 text-sm">
          {[
            { href: "/", label: "Vyhledávání" },
            { href: "/monitors", label: "Monitoring" },
            { href: "/alerts", label: "Upozornění" },
          ].map(({ href, label }) => (
            <Link
              key={href}
              href={href}
              className="px-3 py-1.5 rounded-lg text-slate-600 hover:text-slate-900 hover:bg-slate-100 transition-colors"
            >
              {label}
            </Link>
          ))}
        </div>
      </div>
    </nav>
  );
}

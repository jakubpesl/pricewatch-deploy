import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";
import { Providers } from "./providers";
import { NavBar } from "@/components/layout/NavBar";

const inter = Inter({ subsets: ["latin"] });

export const metadata: Metadata = {
  title: "PriceWatch — Retail Price Monitor",
  description: "Track prices across every European retailer",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className={`${inter.className} bg-slate-50 min-h-screen`}>
        <Providers>
          <NavBar />
          <main className="max-w-7xl mx-auto px-4 py-8">{children}</main>
        </Providers>
      </body>
    </html>
  );
}

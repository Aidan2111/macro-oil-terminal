import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";
import { Nav } from "@/components/common/Nav";
import { Footer } from "@/components/common/Footer";
import { TickerTape } from "@/components/ticker/TickerTape";
import { ShortcutSheet } from "@/components/common/ShortcutSheet";
import { Providers } from "@/lib/providers";

const inter = Inter({
  subsets: ["latin"],
  variable: "--font-inter",
  display: "swap",
});

export const metadata: Metadata = {
  title: "Macro Oil Terminal",
  description:
    "Oil-spread dislocation research terminal — live quotes, trade theses, fleet tracking.",
  icons: {
    icon: "/favicon.ico",
  },
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className={inter.variable}>
      {/*
        overflow-x-hidden on body is the defensive cap — every page-level
        horizontal-scroll bug we surfaced traced back to a flex child
        whose intrinsic width (the ticker tape's w-max ul) was forcing
        the main panel to grow past the viewport. min-w-0 + overflow-hidden
        on the main panel below lets the flex item shrink below its
        content's natural size; this body-level cap is a belt to the
        suspenders so we never paint horizontal scroll at any viewport.
      */}
      <body className="min-h-screen bg-bg-1 text-text-primary font-sans overflow-x-hidden">
        <Providers>
          <a
            href="#main"
            className="sr-only focus:not-sr-only focus:fixed focus:top-2 focus:left-2 focus:z-50 focus:rounded-btn focus:bg-bg-3 focus:px-3 focus:py-2 focus:text-sm focus:text-text-primary focus:outline-none focus:ring-2 focus:ring-primary"
          >
            Skip to main content
          </a>
          <div className="flex flex-col md:flex-row min-h-screen">
            <Nav />
            <div className="flex-1 min-w-0 overflow-hidden flex flex-col md:ml-60">
              <TickerTape />
              <main id="main" className="flex-1 pb-20 md:pb-0">
                {children}
              </main>
              <Footer />
            </div>
          </div>
          <ShortcutSheet />
        </Providers>
      </body>
    </html>
  );
}

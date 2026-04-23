import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";
import { Nav } from "@/components/common/Nav";
import { Footer } from "@/components/common/Footer";
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
      <body className="min-h-screen bg-bg-1 text-text-primary font-sans">
        <Providers>
          <div className="flex flex-col lg:flex-row min-h-screen">
            <Nav />
            <div className="flex-1 flex flex-col lg:ml-56">
              <main className="flex-1 pb-20 lg:pb-0">{children}</main>
              <Footer />
            </div>
          </div>
        </Providers>
      </body>
    </html>
  );
}

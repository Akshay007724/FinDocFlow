import type { Metadata } from "next";
import { IBM_Plex_Sans, Fira_Code } from "next/font/google";
import "./globals.css";
import { Providers } from "@/components/providers";
import { Sidebar } from "@/components/shell/sidebar";
import { Topbar } from "@/components/shell/topbar";
import { CommandPalette } from "@/components/shell/command-palette";

const plexSans = IBM_Plex_Sans({
  subsets: ["latin"],
  weight: ["300", "400", "500", "600", "700"],
  variable: "--font-plex-sans",
  display: "swap",
});

const firaCode = Fira_Code({
  subsets: ["latin"],
  weight: ["400", "500", "600"],
  variable: "--font-fira-code",
  display: "swap",
});

export const metadata: Metadata = {
  title: "FinDocFlow · Multimodal Financial Document Intelligence",
  description: "Cross-page multimodal reasoning over SEC filings with THINK → ACT → VERIFY.",
  icons: { icon: "/favicon.ico" },
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`dark ${plexSans.variable} ${firaCode.variable}`} suppressHydrationWarning>
      <body className="min-h-dvh bg-background font-sans text-foreground antialiased">
        <Providers>
          <div className="flex min-h-dvh">
            <Sidebar />
            <div className="flex min-h-dvh flex-1 flex-col">
              <Topbar />
              <main
                id="main-content"
                tabIndex={-1}
                className="flex-1 overflow-auto px-4 py-5 md:px-8 md:py-7"
              >
                {children}
              </main>
            </div>
          </div>
          <CommandPalette />
        </Providers>
      </body>
    </html>
  );
}

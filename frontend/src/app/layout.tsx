import type { Metadata, Viewport } from "next";
import { Inter } from "next/font/google";
import "./globals.css";
import StoreProvider from "./StoreProvider";
import StyledComponentsRegistry from "./registry";
import AppShell from "../components/navigation/AppShell";
import { CockpitSyncProvider } from "../components/cockpit/CockpitSyncProvider";
import { SyncRefreshBridge } from "../components/SyncRefreshBridge";
import QueryProvider from "./QueryProvider";

const inter = Inter({ subsets: ["latin"] });

export const metadata: Metadata = {
  title: "Treningsanalyse",
  description: "Personlig treningscockpit for Garmin-data",
  applicationName: "Treningsanalyse",
  manifest: "/manifest.webmanifest",
  appleWebApp: {
    capable: true,
    statusBarStyle: "default",
    title: "Treningsanalyse",
  },
  icons: {
    icon: [{ url: "/icons/icon-192.svg", type: "image/svg+xml" }],
    apple: [{ url: "/icons/icon-192.svg" }],
  },
};

export const viewport: Viewport = {
  themeColor: "#0f172a",
  width: "device-width",
  initialScale: 1,
  maximumScale: 1,
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="no">
      <body className={inter.className}>
        <StyledComponentsRegistry>
          <QueryProvider>
            <StoreProvider>
              <CockpitSyncProvider>
                <SyncRefreshBridge />
                <AppShell>{children}</AppShell>
              </CockpitSyncProvider>
            </StoreProvider>
          </QueryProvider>
        </StyledComponentsRegistry>
      </body>
    </html>
  );
}

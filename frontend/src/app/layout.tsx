import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";
import StoreProvider from "./StoreProvider";
import StyledComponentsRegistry from "./registry";
import AppShell from "../components/AppShell";
import QueryProvider from "./QueryProvider";

const inter = Inter({ subsets: ["latin"] });

export const metadata: Metadata = {
  title: "Treningsanalyse",
  description: "Treningsbeslutninger basert på Garmin-data",
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
              <AppShell>{children}</AppShell>
            </StoreProvider>
          </QueryProvider>
        </StyledComponentsRegistry>
      </body>
    </html>
  );
}

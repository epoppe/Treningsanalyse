import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";
import StoreProvider from "./StoreProvider";
import StyledComponentsRegistry from "./registry";
import Navbar from "../components/Navbar";

const inter = Inter({ subsets: ["latin"] });

export const metadata: Metadata = {
  title: "Treningsapp",
  description: "Analyse av treningsdata fra Garmin",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <html lang="no">
      <body className={inter.className}>
        <StyledComponentsRegistry>
          <StoreProvider>
            <Navbar />
            <main>
              {children}
            </main>
          </StoreProvider>
        </StyledComponentsRegistry>
      </body>
    </html>
  );
}

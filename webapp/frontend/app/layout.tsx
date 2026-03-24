import type { Metadata } from "next";
import Sidebar from "@/components/Sidebar";
import SystemStatus from "@/components/SystemStatus";
import ResearchPanel from "@/components/ResearchPanel";
import "./globals.css";

export const metadata: Metadata = {
  title: "QS Finance",
  description: "Quantitative Strategy Trading Platform",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="bg-cyber-bg text-cyber-text antialiased">
        <div className="flex min-h-screen">
          <Sidebar />
          <main className="flex-1 ml-56 pb-10">
            {children}
          </main>
        </div>
        <ResearchPanel />
        <SystemStatus />
      </body>
    </html>
  );
}

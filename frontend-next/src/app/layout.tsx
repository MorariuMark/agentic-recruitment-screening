import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import "./globals.css";
import { QueryProvider } from "@/components/providers/query-provider";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "Atos Screening AI | Enterprise Recruitment Platform",
  description:
    "Autonomous B2B talent screening engine with high-volume CV parsing, asymmetric RAG verification, and auditable human-in-the-loop decision gating.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html
      lang="en"
      className={`${geistSans.variable} ${geistMono.variable} h-full antialiased dark`}
    >
      <body className="h-full bg-slate-950 text-slate-100 selection:bg-blue-600 selection:text-white">
        <QueryProvider>{children}</QueryProvider>
      </body>
    </html>
  );
}

import type { Metadata } from "next";
import { ClerkProvider } from "@clerk/nextjs";
import "./globals.css";

export const metadata: Metadata = {
  title: "x-video-engine",
  description: "Faceless short-video factory",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <ClerkProvider>
      <html lang="en">
        <body className="bg-zinc-950 text-zinc-100 antialiased">{children}</body>
      </html>
    </ClerkProvider>
  );
}

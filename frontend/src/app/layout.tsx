import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Prompt Inspector — Detection Playground",
  description:
    "Detect prompt injection attacks in real-time with the open-source Prompt Inspector.",
  icons: {
    icon: [
      { url: "/favicon.ico" },
      { url: "/logo-192x192.png", sizes: "192x192", type: "image/png" },
    ],
  },
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}

import type { Metadata, Viewport } from "next";
import { JSONLD } from "@/generated/jsonld";
import "./globals.css";

const FAVICON =
  "data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 64 64'><rect width='64' height='64' rx='14' fill='%230e1315'/><circle cx='32' cy='32' r='10' fill='%2337c6a6'/><circle cx='32' cy='32' r='17' fill='none' stroke='%2337c6a6' stroke-opacity='.45' stroke-width='3'/></svg>";

export const metadata: Metadata = {
  metadataBase: new URL("https://continuum-gray.vercel.app"),
  title: "Continuum, portable reasoning-state memory for AI",
  description:
    "Every AI forgets your reasoning when a chat ends. Continuum saves it and resumes it in any other AI, months later, exactly as you left it. Free to start.",
  openGraph: {
    title: "Continuum. Your AI forgets why. Continuum remembers.",
    description:
      "Portable reasoning-state memory. Animated walkthrough, per-tool problem map, pricing, and FAQ. Live MCP endpoint.",
    url: "https://continuum-gray.vercel.app",
    siteName: "Continuum",
    type: "website",
  },
  icons: { icon: FAVICON },
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  themeColor: [
    { media: "(prefers-color-scheme: dark)", color: "#0e1315" },
    { media: "(prefers-color-scheme: light)", color: "#eef2f0" },
  ],
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <head>
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link
          rel="preconnect"
          href="https://fonts.gstatic.com"
          crossOrigin="anonymous"
        />
        <link
          href="https://fonts.googleapis.com/css2?family=Fraunces:ital,opsz,wght@0,9..144,450..750;1,9..144,450..750&display=swap"
          rel="stylesheet"
        />
        <script
          type="application/ld+json"
          dangerouslySetInnerHTML={{ __html: JSONLD }}
        />
      </head>
      <body>{children}</body>
    </html>
  );
}

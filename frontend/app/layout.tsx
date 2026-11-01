import type { Metadata, Viewport } from "next";
import "./globals.css";
export const metadata: Metadata = {
  title: "SaveX · Home, in order",
  description: "Remember what you have and where it lives.",
  manifest: "/manifest.webmanifest",
  appleWebApp: { capable: true, title: "SaveX" },
};
export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  themeColor: "#161a1d",
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

import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Floorplan Workspace",
  description: "AI-assisted backend chip floorplanning workspace",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body className="h-screen overflow-hidden">{children}</body>
    </html>
  );
}

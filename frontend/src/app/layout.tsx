import type { Metadata } from "next";
import type { ReactNode } from "react";

import "./globals.css";

export const metadata: Metadata = {
  title: "AI Dashboard Agent",
  description: "Local real-estate dashboard builder",
};

export default function RootLayout({children}: Readonly<{children: ReactNode}>) {
  return (
    <html lang="vi">
      <body>{children}</body>
    </html>
  );
}


import type { Metadata } from "next";
import type { ReactNode } from "react";

import "./globals.css";

export const metadata: Metadata = {
  title: "Code Intelligence",
  description:
    "Local-first code intelligence — deterministic facts, optional AI enrichment.",
};

// Set the stored theme before first paint to avoid a flash.
const themeScript = `(function(){try{var t=localStorage.getItem('ci-theme');if(t==='light'||t==='dark'){document.documentElement.dataset.theme=t;}}catch(e){}})();`;

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en" suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: themeScript }} />
      </head>
      <body>{children}</body>
    </html>
  );
}

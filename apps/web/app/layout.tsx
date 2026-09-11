import type { ReactNode } from "react";
import { SessionProvider } from "@/lib/session";
import "./globals.css";

export const metadata = {
  title: "QFinance",
  description: "Investor workspace and investment community.",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body className="font-body">
        <SessionProvider>{children}</SessionProvider>
      </body>
    </html>
  );
}

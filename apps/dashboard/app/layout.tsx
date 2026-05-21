import type { Metadata } from "next";
import "./styles.css";

export const metadata: Metadata = {
  title: "Pentecostal Live",
  description: "Broadcast operations dashboard for church livestream teams"
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}


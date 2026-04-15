import type { Metadata } from 'next';
import { Geist, Geist_Mono } from 'next/font/google';
import './globals.css';
import QueryProvider from '@/lib/query-client';
import PostHogProvider from '@/components/PostHogProvider';
import TrackingDelegate from '@/components/TrackingDelegate';

const geistSans = Geist({
  variable: '--font-geist-sans',
  subsets: ['latin'],
});

const geistMono = Geist_Mono({
  variable: '--font-geist-mono',
  subsets: ['latin'],
});

export const metadata: Metadata = {
  title: 'myTrader - Personal Quantitative Trading Platform',
  description: 'Personal investment research and trading platform',
};

export const viewport = {
  width: 'device-width',
  initialScale: 1,
  maximumScale: 1,
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html
      lang="zh-CN"
      className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`}
    >
      <body className="min-h-full flex flex-col" style={{ background: 'var(--bg-canvas)', color: 'var(--text-primary)' }}>
        <PostHogProvider>
          <TrackingDelegate />
          <QueryProvider>{children}</QueryProvider>
        </PostHogProvider>
      </body>
    </html>
  );
}

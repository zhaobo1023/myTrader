import type { Metadata } from 'next';
import localFont from 'next/font/local';
import './globals.css';
import QueryProvider from '@/lib/query-client';
import PostHogProvider from '@/components/PostHogProvider';
import TrackingDelegate from '@/components/TrackingDelegate';

const geistSans = localFont({
  src: './fonts/GeistVF.woff',
  variable: '--font-geist-sans',
  weight: '100 900',
});

const geistMono = localFont({
  src: './fonts/GeistMonoVF.woff',
  variable: '--font-geist-mono',
  weight: '100 900',
});

export const metadata: Metadata = {
  title: 'myTrader - AI 量化投研平台',
  description: '智能选股 / AI 研报 / 因子分析 / 风险管理',
  openGraph: {
    title: 'myTrader - AI 量化投研平台',
    description: '智能选股 / AI 研报 / 因子分析 / 风险管理',
    siteName: 'myTrader',
    locale: 'zh_CN',
    type: 'website',
  },
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

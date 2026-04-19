import type { Metadata, Viewport } from 'next';
import { Outfit } from 'next/font/google';
import '@/styles/globals.css';
import { Providers } from './providers';

const outfit = Outfit({
  subsets: ['latin'],
  variable: '--font-outfit',
  display: 'swap',
});

export const metadata: Metadata = {
  metadataBase: new URL(
    process.env.NEXT_PUBLIC_SITE_URL ?? 'http://localhost:3000'
  ),
  title: {
    default: 'RAGfier — RAG-as-a-Service Platform',
    template: '%s · RAGfier',
  },
  description:
    'Operator dashboard for RAGfier — ingest documents, manage integrations, stream grounded answers, and audit every request.',
  applicationName: 'RAGfier',
  authors: [{ name: 'RAGfier' }],
  keywords: ['RAG', 'retrieval-augmented generation', 'LLM', 'vector search', 'observability'],
  robots: {
    index: false,
    follow: false,
    nocache: true,
  },
  openGraph: {
    title: 'RAGfier — RAG-as-a-Service Platform',
    description: 'Operator dashboard for RAGfier.',
    type: 'website',
    siteName: 'RAGfier',
  },
  formatDetection: {
    email: false,
    address: false,
    telephone: false,
  },
};

export const viewport: Viewport = {
  width: 'device-width',
  initialScale: 1,
  maximumScale: 5,
  colorScheme: 'light',
  themeColor: [
    { media: '(prefers-color-scheme: light)', color: '#FFFFFF' },
    { media: '(prefers-color-scheme: dark)', color: '#111827' },
  ],
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className={outfit.variable}>
      <body>
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}

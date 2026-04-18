import type { Metadata } from 'next';
import { Outfit } from 'next/font/google';
import '@/styles/globals.css';
import { Providers } from './providers';

const outfit = Outfit({
  subsets: ['latin'],
  variable: '--font-outfit',
  display: 'swap',
});

export const metadata: Metadata = {
  title: 'RAGfier',
  description: 'RAG-as-a-Service Platform',
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

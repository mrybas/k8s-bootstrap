import type { Metadata } from 'next';
import './globals.css';

export const metadata: Metadata = {
  title: 'K8s Bootstrap - GitOps Generator for Kubernetes',
  description: 'Generate GitOps bootstrap repositories for your Kubernetes clusters. Like vim-bootstrap, but for Kubernetes.',
  keywords: ['kubernetes', 'gitops', 'flux', 'helm', 'bootstrap', 'k8s'],
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body className="bg-base text-text antialiased">
        <div className="fixed inset-0 bg-mesh pointer-events-none" />
        <main className="relative z-10">
          {children}
        </main>
      </body>
    </html>
  );
}

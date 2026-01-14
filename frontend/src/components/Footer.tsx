'use client';

import { Terminal, Heart } from 'lucide-react';

export function Footer() {
  return (
    <footer className="py-12 px-4 border-t border-overlay/30">
      <div className="max-w-7xl mx-auto">
        <div className="flex flex-col md:flex-row items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            <div className="p-2 bg-surface rounded-lg">
              <Terminal className="w-4 h-4 text-lavender" />
            </div>
            <span className="text-subtext text-sm">
              k8s-bootstrap
            </span>
          </div>

          <div className="flex items-center gap-1 text-sm text-muted">
            Made with <Heart className="w-4 h-4 text-red mx-1" /> for the Kubernetes community
          </div>

          <div className="text-sm text-muted">
            AGPL-3.0
          </div>
        </div>
      </div>
    </footer>
  );
}

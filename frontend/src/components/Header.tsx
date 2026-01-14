'use client';

import Link from 'next/link';
import { motion } from 'framer-motion';
import { Github, BookOpen, Terminal } from 'lucide-react';

const GITHUB_URL = process.env.NEXT_PUBLIC_GITHUB_URL || 'https://github.com/mrybas/k8s-bootstrap';

export function Header() {
  return (
    <motion.header
      initial={{ opacity: 0, y: -20 }}
      animate={{ opacity: 1, y: 0 }}
      className="fixed top-0 left-0 right-0 z-50 bg-base/80 backdrop-blur-xl border-b border-overlay/30"
    >
      <div className="max-w-7xl mx-auto px-4 h-16 flex items-center justify-between">
        <Link href="/" className="flex items-center gap-3">
          <div className="p-2 bg-gradient-to-br from-lavender to-blue rounded-lg">
            <Terminal className="w-5 h-5 text-base" />
          </div>
          <span className="font-bold text-lg">
            <span className="text-lavender">k8s</span>
            <span className="text-text">-bootstrap</span>
          </span>
        </Link>

        <div className="flex items-center gap-6">
          <Link 
            href="/docs" 
            className="text-subtext hover:text-text transition-colors flex items-center gap-1.5"
          >
            <BookOpen className="w-4 h-4" />
            Docs
          </Link>
          <a 
            href={GITHUB_URL}
            target="_blank"
            rel="noopener noreferrer"
            className="text-subtext hover:text-text transition-colors flex items-center gap-1.5"
          >
            <Github className="w-4 h-4" />
            GitHub
          </a>
        </div>
      </div>
    </motion.header>
  );
}

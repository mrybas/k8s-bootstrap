'use client';

import { motion } from 'framer-motion';
import { ChevronDown, Sparkles, GitBranch, Box } from 'lucide-react';

export function Hero() {
  return (
    <section className="min-h-screen flex flex-col items-center justify-center px-4 pt-16 relative overflow-hidden">
      {/* Animated background elements */}
      <div className="absolute inset-0 overflow-hidden pointer-events-none">
        <motion.div
          animate={{ 
            rotate: 360,
            scale: [1, 1.1, 1],
          }}
          transition={{ 
            rotate: { duration: 60, repeat: Infinity, ease: 'linear' },
            scale: { duration: 8, repeat: Infinity, ease: 'easeInOut' },
          }}
          className="absolute -top-40 -right-40 w-96 h-96 bg-lavender/5 rounded-full blur-3xl"
        />
        <motion.div
          animate={{ 
            rotate: -360,
            scale: [1, 1.2, 1],
          }}
          transition={{ 
            rotate: { duration: 45, repeat: Infinity, ease: 'linear' },
            scale: { duration: 10, repeat: Infinity, ease: 'easeInOut' },
          }}
          className="absolute -bottom-40 -left-40 w-96 h-96 bg-mauve/5 rounded-full blur-3xl"
        />
      </div>

      <motion.div
        initial={{ opacity: 0, y: 30 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.8 }}
        className="text-center max-w-4xl relative z-10"
      >
        {/* Badge */}
        <motion.div
          initial={{ opacity: 0, scale: 0.9 }}
          animate={{ opacity: 1, scale: 1 }}
          transition={{ delay: 0.2 }}
          className="inline-flex items-center gap-2 px-4 py-2 bg-surface/50 rounded-full border border-overlay/50 mb-8"
        >
          <Sparkles className="w-4 h-4 text-yellow" />
          <span className="text-sm text-subtext">
            Like vim-bootstrap, but for Kubernetes
          </span>
        </motion.div>

        {/* Main heading */}
        <h1 className="text-5xl md:text-7xl font-bold mb-6 leading-tight">
          <span className="bg-gradient-to-r from-lavender via-blue to-sapphire bg-clip-text text-transparent">
            Bootstrap Your
          </span>
          <br />
          <span className="text-text">Kubernetes Cluster</span>
        </h1>

        {/* Subtitle */}
        <p className="text-xl text-subtext mb-8 max-w-2xl mx-auto leading-relaxed">
          Generate a complete <span className="text-teal">GitOps repository</span> with 
          Flux manifests and vendored Helm charts. 
          Select components, configure, download, and deploy.
        </p>

        {/* Feature pills */}
        <div className="flex flex-wrap justify-center gap-3 mb-12">
          <FeaturePill icon={<GitBranch className="w-4 h-4" />} text="Flux CD" />
          <FeaturePill icon={<Box className="w-4 h-4" />} text="Helm Charts" />
          <FeaturePill icon={<Sparkles className="w-4 h-4" />} text="Pure GitOps" />
        </div>

        {/* CTA Button */}
        <motion.a
          href="#generator"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ delay: 0.5 }}
          className="btn-primary inline-flex items-center gap-2 text-lg"
        >
          Start Building
          <ChevronDown className="w-5 h-5 animate-bounce" />
        </motion.a>
      </motion.div>

      {/* Code preview decoration */}
      <motion.div
        initial={{ opacity: 0, y: 50 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.7, duration: 0.8 }}
        className="mt-16 w-full max-w-3xl mx-auto"
      >
        <div className="bg-surface/50 backdrop-blur rounded-xl border border-overlay/50 overflow-hidden shadow-2xl">
          {/* Terminal header */}
          <div className="flex items-center gap-2 px-4 py-3 bg-overlay/30 border-b border-overlay/50">
            <div className="w-3 h-3 rounded-full bg-red/70" />
            <div className="w-3 h-3 rounded-full bg-yellow/70" />
            <div className="w-3 h-3 rounded-full bg-green/70" />
            <span className="ml-2 text-xs text-muted">bootstrap.sh</span>
          </div>
          
          {/* Terminal content */}
          <div className="p-4 font-mono text-sm">
            <div className="text-muted">
              <span className="text-green">$</span> ./bootstrap.sh
            </div>
            <div className="mt-2 text-subtext">
              <span className="text-blue">[INFO]</span> Installing Flux via Helm...
            </div>
            <div className="text-subtext">
              <span className="text-green">[SUCCESS]</span> Flux installed successfully
            </div>
            <div className="text-subtext">
              <span className="text-blue">[INFO]</span> Applying GitRepository...
            </div>
            <div className="text-subtext">
              <span className="text-green">[SUCCESS]</span> Bootstrap completed!
            </div>
            <div className="mt-2 text-text flex items-center gap-2">
              <span className="text-green">✓</span> All components synced via GitOps
            </div>
          </div>
        </div>
      </motion.div>
    </section>
  );
}

function FeaturePill({ icon, text }: { icon: React.ReactNode; text: string }) {
  return (
    <div className="flex items-center gap-2 px-4 py-2 bg-surface/30 rounded-full border border-overlay/30">
      <span className="text-lavender">{icon}</span>
      <span className="text-sm text-text">{text}</span>
    </div>
  );
}

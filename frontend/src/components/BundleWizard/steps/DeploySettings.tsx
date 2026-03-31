'use client';

import React from 'react';
import { GitBranch, Key, Shield, Terminal } from 'lucide-react';
import { WizardState } from '../types';

interface DeploySettingsProps {
  gitConfig: WizardState['gitConfig'];
  onConfigChange: (config: Partial<WizardState['gitConfig']>) => void;
}

const GIT_PROVIDERS = [
  { value: 'github', label: 'GitHub' },
  { value: 'gitlab', label: 'GitLab' },
  { value: 'gitea', label: 'Gitea' },
  { value: 'forgejo', label: 'Forgejo' },
];

export function DeploySettings({ gitConfig, onConfigChange }: DeploySettingsProps) {
  return (
    <div className="space-y-6">
      <div className="text-center">
        <h2 className="text-2xl font-bold text-text mb-2">Deploy to Cluster</h2>
        <p className="text-subtext">Configure Git repository and deployment options</p>
      </div>

      <div className="max-w-xl mx-auto space-y-8">
        {/* Git Repository */}
        <section className="space-y-4">
          <h3 className="text-sm font-semibold text-lavender uppercase tracking-wider flex items-center gap-2">
            <GitBranch className="w-4 h-4" />
            Git Repository
          </h3>

          <div className="space-y-4">
            {/* Provider */}
            <div className="space-y-1">
              <label className="text-sm font-medium text-text">Provider</label>
              <select
                value={gitConfig.provider}
                onChange={(e) => onConfigChange({ provider: e.target.value })}
                className="
                  w-full px-3 py-2 bg-surface border border-overlay rounded-lg 
                  text-text text-sm
                  focus:outline-none focus:ring-2 focus:ring-lavender/50
                "
              >
                {GIT_PROVIDERS.map(p => (
                  <option key={p.value} value={p.value}>{p.label}</option>
                ))}
              </select>
            </div>

            {/* Repository URL */}
            <div className="space-y-1">
              <label className="text-sm font-medium text-text">
                Repository URL <span className="text-red">*</span>
              </label>
              <input
                type="text"
                value={gitConfig.repoUrl}
                onChange={(e) => onConfigChange({ repoUrl: e.target.value })}
                placeholder="https://github.com/user/cluster-config.git"
                className="
                  w-full px-3 py-2 bg-surface border border-overlay rounded-lg 
                  text-text text-sm placeholder:text-subtext/50
                  focus:outline-none focus:ring-2 focus:ring-lavender/50
                "
              />
            </div>

            {/* Credentials */}
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1">
                <label className="text-sm font-medium text-text">Username</label>
                <input
                  type="text"
                  value={gitConfig.username}
                  onChange={(e) => onConfigChange({ username: e.target.value })}
                  placeholder="username"
                  className="
                    w-full px-3 py-2 bg-surface border border-overlay rounded-lg 
                    text-text text-sm placeholder:text-subtext/50
                    focus:outline-none focus:ring-2 focus:ring-lavender/50
                  "
                />
              </div>
              <div className="space-y-1">
                <label className="text-sm font-medium text-text">Password / Token</label>
                <input
                  type="password"
                  value={gitConfig.password}
                  onChange={(e) => onConfigChange({ password: e.target.value })}
                  placeholder="••••••••"
                  className="
                    w-full px-3 py-2 bg-surface border border-overlay rounded-lg 
                    text-text text-sm placeholder:text-subtext/50
                    focus:outline-none focus:ring-2 focus:ring-lavender/50
                  "
                />
              </div>
            </div>

            {/* Auto push */}
            <label className="flex items-center gap-2 cursor-pointer">
              <input
                type="checkbox"
                checked={gitConfig.autoPush}
                onChange={(e) => onConfigChange({ autoPush: e.target.checked })}
                className="w-4 h-4 rounded border-overlay bg-surface text-lavender focus:ring-lavender"
              />
              <span className="text-sm text-text">Push to Git automatically</span>
            </label>
          </div>
        </section>

        {/* Security */}
        <section className="space-y-4">
          <h3 className="text-sm font-semibold text-lavender uppercase tracking-wider flex items-center gap-2">
            <Shield className="w-4 h-4" />
            Security
          </h3>

          <label className="flex items-start gap-2 cursor-pointer p-3 bg-surface/50 rounded-lg border border-overlay/50">
            <input
              type="checkbox"
              checked={gitConfig.enableSops}
              onChange={(e) => onConfigChange({ enableSops: e.target.checked })}
              className="w-4 h-4 mt-0.5 rounded border-overlay bg-surface text-lavender focus:ring-lavender"
            />
            <div>
              <span className="text-sm text-text font-medium">Enable SOPS encryption</span>
              <p className="text-xs text-subtext mt-1">
                Encrypt sensitive values in Git using age/SOPS.
                Requires sops and age installed on deployment machine.
              </p>
            </div>
          </label>
        </section>

        {/* Kubeconfig */}
        <section className="space-y-4">
          <h3 className="text-sm font-semibold text-lavender uppercase tracking-wider flex items-center gap-2">
            <Terminal className="w-4 h-4" />
            Kubeconfig
          </h3>

          <div className="space-y-3">
            <label className="flex items-center gap-2 cursor-pointer">
              <input
                type="radio"
                name="kubeconfig"
                checked={gitConfig.useDefaultKubeconfig}
                onChange={() => onConfigChange({ useDefaultKubeconfig: true })}
                className="w-4 h-4 border-overlay bg-surface text-lavender focus:ring-lavender"
              />
              <span className="text-sm text-text">Use default (~/.kube/config)</span>
            </label>

            <label className="flex items-center gap-2 cursor-pointer">
              <input
                type="radio"
                name="kubeconfig"
                checked={!gitConfig.useDefaultKubeconfig}
                onChange={() => onConfigChange({ useDefaultKubeconfig: false })}
                className="w-4 h-4 border-overlay bg-surface text-lavender focus:ring-lavender"
              />
              <span className="text-sm text-text">Custom path</span>
            </label>

            {!gitConfig.useDefaultKubeconfig && (
              <input
                type="text"
                value={gitConfig.kubeconfigPath}
                onChange={(e) => onConfigChange({ kubeconfigPath: e.target.value })}
                placeholder="/path/to/kubeconfig"
                className="
                  w-full px-3 py-2 bg-surface border border-overlay rounded-lg 
                  text-text text-sm placeholder:text-subtext/50
                  focus:outline-none focus:ring-2 focus:ring-lavender/50 ml-6
                "
              />
            )}
          </div>
        </section>
      </div>
    </div>
  );
}

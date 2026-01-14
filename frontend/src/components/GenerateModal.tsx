'use client';

import { useState } from 'react';
import { motion } from 'framer-motion';
import { 
  X, Copy, Check, Loader2, 
  GitBranch, Server, FolderGit, Terminal,
  Zap, Clock, AlertCircle, Container, Lock, Globe
} from 'lucide-react';
import type { ComponentSelection, GitAuthConfig, GitPlatform } from '@/types';

interface ImportedConfig {
  clusterName?: string;
  repoUrl?: string;
  branch?: string;
}

interface GenerateModalProps {
  selections: ComponentSelection[];
  onClose: () => void;
  importedConfig?: ImportedConfig | null;
}

interface BootstrapResponse {
  token: string;
  curl_command: string;
  expires_in_minutes: number;
  one_time: boolean;
  devCurlCommand?: string | null;
}

interface UpdateResponse {
  token: string;
  curl_command: string;
  expires_in_minutes: number;
  one_time: boolean;
  files_count: number;
  charts_count: number;
  devCurlCommand?: string | null;
}

const GIT_PLATFORMS: { id: GitPlatform; name: string; defaultUrl?: string }[] = [
  // { id: 'github', name: 'GitHub', defaultUrl: 'https://github.com' },  // TODO: Enable after testing private repos
  { id: 'gitlab', name: 'GitLab' },
  { id: 'gitea', name: 'Gitea' },
];

// Helper to extract instance URL from git repo URL
const extractInstanceUrl = (repoUrl: string): string => {
  try {
    // Handle http(s) URLs
    if (repoUrl.startsWith('http')) {
      const url = new URL(repoUrl);
      return `${url.protocol}//${url.host}`;
    }
    // Handle SSH URLs like git@host:user/repo.git
    const sshMatch = repoUrl.match(/^git@([^:]+):/);
    if (sshMatch) {
      return `https://${sshMatch[1]}`;
    }
  } catch {
    // ignore
  }
  return '';
};

// Helper to detect platform from URL
const detectPlatform = (repoUrl: string): GitPlatform => {
  const lower = repoUrl.toLowerCase();
  if (lower.includes('github.com') || lower.includes('github')) return 'github';
  if (lower.includes('gitlab.com') || lower.includes('gitlab')) return 'gitlab';
  if (lower.includes('gitea')) return 'gitea';
  return 'github';
};

export function GenerateModal({ selections, onClose, importedConfig }: GenerateModalProps) {
  const isDevMode = process.env.NEXT_PUBLIC_DEV_MODE === 'true';
  const defaultRepoUrl = isDevMode 
    ? 'http://gitea:3000/dev/bootstrap-test.git' 
    : 'git@github.com:username/k8s-gitops.git';
  
  const [step, setStep] = useState<'config' | 'generating' | 'done'>('config');
  const [clusterName, setClusterName] = useState(importedConfig?.clusterName || 'my-cluster');
  const [repoUrl, setRepoUrl] = useState(importedConfig?.repoUrl || defaultRepoUrl);
  const [branch, setBranch] = useState(importedConfig?.branch || 'main');
  const [error, setError] = useState<string | null>(null);
  const [bootstrapResponse, setBootstrapResponse] = useState<BootstrapResponse | null>(null);
  const [copiedField, setCopiedField] = useState<string | null>(null);
  
  // Git authentication state - auto-enable in dev mode
  const [gitAuthEnabled, setGitAuthEnabled] = useState(isDevMode);
  const [gitPlatform, setGitPlatform] = useState<GitPlatform>('gitea');
  const [gitCustomUrl, setGitCustomUrl] = useState(isDevMode ? extractInstanceUrl(defaultRepoUrl) : '');
  
  // Skip git push - just prepare repository locally
  const [skipGitPush, setSkipGitPush] = useState(false);

  const handleGenerate = async () => {
    setStep('generating');
    setError(null);

    // Build git auth config if enabled
    const gitAuth: GitAuthConfig | undefined = gitAuthEnabled ? {
      enabled: true,
      platform: gitPlatform,
      customUrl: (gitPlatform !== 'github' && gitCustomUrl) ? gitCustomUrl : undefined,
    } : undefined;

    // Use update endpoint if we have imported config
    const isUpdate = Boolean(importedConfig);
    const endpoint = isUpdate ? '/api/update' : '/api/bootstrap';
    const scriptPath = isUpdate ? 'update' : 'bootstrap';

    try {
      const response = await fetch(endpoint, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          cluster_name: clusterName,
          repo_url: repoUrl,
          branch: branch,
          components: selections.map(s => ({
            id: s.id,
            enabled: s.enabled,
            values: s.values,
            raw_overrides: s.rawOverrides,
          })),
          git_auth: gitAuth,
          skip_git_push: skipGitPush,
        }),
      });

      if (!response.ok) {
        const data = await response.json();
        throw new Error(data.detail || 'Generation failed');
      }

      const data: BootstrapResponse = await response.json();
      
      // Construct curl command with current origin (frontend URL, not backend)
      const origin = window.location.origin;
      data.curl_command = `bash -c "$(curl -fsSL ${origin}/${scriptPath}/${data.token})"`;
      
      // For dev mode, also generate container-accessible URL
      const isDevModeLocal = process.env.NEXT_PUBLIC_DEV_MODE === 'true';
      data.devCurlCommand = isDevModeLocal 
        ? `bash -c "$(curl -fsSL http://frontend:3000/${scriptPath}/${data.token})"`
        : null;
      
      setBootstrapResponse(data);
      setStep('done');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unknown error');
      setStep('config');
    }
  };

  const copyToClipboard = (text: string, field: string) => {
    navigator.clipboard.writeText(text);
    setCopiedField(field);
    setTimeout(() => setCopiedField(null), 2000);
  };

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm"
      onClick={(e) => e.target === e.currentTarget && onClose()}
    >
      <motion.div
        initial={{ opacity: 0, scale: 0.95, y: 20 }}
        animate={{ opacity: 1, scale: 1, y: 0 }}
        exit={{ opacity: 0, scale: 0.95, y: 20 }}
        className="bg-base border border-overlay rounded-xl shadow-2xl w-full max-w-2xl overflow-hidden"
      >
        {/* Header */}
        <div className="flex items-center justify-between p-4 border-b border-overlay">
          <div className="flex items-center gap-3">
            <div className="p-2 bg-gradient-to-br from-lavender to-blue rounded-lg">
              <Terminal className="w-5 h-5 text-base" />
            </div>
            <div>
              <h3 className="font-semibold text-text">Generate Bootstrap Command</h3>
              <p className="text-xs text-muted">
                {selections.length} component{selections.length !== 1 ? 's' : ''} selected
              </p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="p-2 hover:bg-overlay rounded-lg transition-colors"
          >
            <X className="w-5 h-5 text-muted" />
          </button>
        </div>

        {/* Content */}
        <div className="p-6">
          {step === 'config' && (
            <div className="space-y-4">
              {/* Imported config notice */}
              {importedConfig && (
                <div className="flex items-start gap-3 p-3 bg-lavender/10 border border-lavender/30 rounded-lg">
                  <AlertCircle className="w-5 h-5 text-lavender mt-0.5 flex-shrink-0" />
                  <div className="text-sm">
                    <p className="font-medium text-text">Updating existing configuration</p>
                    <p className="text-muted mt-1">
                      Run <code className="px-1 py-0.5 bg-overlay rounded text-xs">./bootstrap.sh</code> from your existing <code className="px-1 py-0.5 bg-overlay rounded text-xs">{importedConfig.clusterName}</code> folder. 
                      Charts with unchanged versions will be skipped.
                    </p>
                  </div>
                </div>
              )}

              {/* Cluster Name */}
              <div>
                <label className="flex items-center gap-2 text-sm text-text mb-2">
                  <Server className="w-4 h-4 text-lavender" />
                  Cluster Name
                </label>
                <input
                  type="text"
                  value={clusterName}
                  onChange={(e) => setClusterName(e.target.value.toLowerCase().replace(/[^a-z0-9-]/g, '-'))}
                  className="input-field"
                  placeholder="my-cluster"
                />
                <p className="text-xs text-muted mt-1">
                  Used for directory names and resource identification
                </p>
              </div>

              {/* Repository URL */}
              <div>
                <label className="flex items-center gap-2 text-sm text-text mb-2">
                  <FolderGit className="w-4 h-4 text-lavender" />
                  Git Repository URL
                </label>
                <input
                  type="text"
                  value={repoUrl}
                  onChange={(e) => {
                    const newUrl = e.target.value;
                    setRepoUrl(newUrl);
                    // Auto-update instance URL if auth is enabled and platform is gitea/gitlab
                    if (gitAuthEnabled && gitPlatform !== 'github') {
                      setGitCustomUrl(extractInstanceUrl(newUrl));
                    }
                  }}
                  className="input-field"
                  placeholder="git@github.com:username/repo.git"
                />
                <p className="text-xs text-muted mt-1">
                  SSH (git@...) or HTTPS URL where you'll push the generated repo
                </p>
              </div>

              {/* Branch */}
              <div>
                <label className="flex items-center gap-2 text-sm text-text mb-2">
                  <GitBranch className="w-4 h-4 text-lavender" />
                  Branch
                </label>
                <input
                  type="text"
                  value={branch}
                  onChange={(e) => setBranch(e.target.value)}
                  className="input-field"
                  placeholder="main"
                />
              </div>

              {/* Private Repository Authentication */}
              <div className="border-t border-overlay/50 pt-4 mt-4">
                <div className="flex items-center justify-between mb-3">
                  <label className="flex items-center gap-2 text-sm text-text">
                    <Lock className="w-4 h-4 text-lavender" />
                    Private Repository Authentication
                  </label>
                  <button
                    type="button"
                    onClick={() => {
                      const newEnabled = !gitAuthEnabled;
                      setGitAuthEnabled(newEnabled);
                      // Auto-detect platform and extract instance URL when enabling auth
                      if (newEnabled && repoUrl) {
                        const detected = detectPlatform(repoUrl);
                        setGitPlatform(detected);
                        if (detected !== 'github') {
                          setGitCustomUrl(extractInstanceUrl(repoUrl));
                        }
                      }
                    }}
                    className={`relative w-11 h-6 rounded-full transition-colors ${
                      gitAuthEnabled ? 'bg-lavender' : 'bg-overlay'
                    }`}
                  >
                    <span
                      className={`absolute top-1 left-1 w-4 h-4 bg-white rounded-full transition-transform ${
                        gitAuthEnabled ? 'translate-x-5' : 'translate-x-0'
                      }`}
                    />
                  </button>
                </div>

                {gitAuthEnabled && (
                  <div className="space-y-3 pl-6 border-l-2 border-lavender/30">
                    {/* Platform selector */}
                    <div>
                      <label className="text-xs text-muted mb-1.5 block">Git Platform</label>
                      <div className="flex gap-2">
                        {GIT_PLATFORMS.map(platform => (
                          <button
                            key={platform.id}
                            type="button"
                            onClick={() => {
                              setGitPlatform(platform.id);
                              // Auto-extract instance URL when switching to gitlab/gitea
                              if (platform.id !== 'github' && repoUrl) {
                                setGitCustomUrl(extractInstanceUrl(repoUrl));
                              }
                            }}
                            className={`px-3 py-1.5 text-sm rounded-lg border transition-colors ${
                              gitPlatform === platform.id
                                ? 'bg-lavender/20 border-lavender text-lavender'
                                : 'border-overlay text-subtext hover:border-lavender/50'
                            }`}
                          >
                            {platform.name}
                          </button>
                        ))}
                      </div>
                    </div>

                    {/* Custom URL for GitLab/Gitea */}
                    {gitPlatform !== 'github' && (
                      <div>
                        <label className="flex items-center gap-2 text-xs text-muted mb-1.5">
                          <Globe className="w-3 h-3" />
                          {gitPlatform === 'gitlab' ? 'GitLab' : 'Gitea'} Instance URL
                        </label>
                        <input
                          type="text"
                          value={gitCustomUrl}
                          onChange={(e) => setGitCustomUrl(e.target.value)}
                          className="input-field text-sm"
                          placeholder={`https://${gitPlatform === 'gitlab' ? 'gitlab.company.com' : 'gitea.company.com'}`}
                        />
                      </div>
                    )}

                    {/* Requirements notice */}
                    <div className="p-3 bg-peach/10 border border-peach/30 rounded-lg text-xs">
                      <div className="flex items-start gap-2">
                        <AlertCircle className="w-4 h-4 text-peach flex-shrink-0 mt-0.5" />
                        <div className="text-subtext">
                          <p className="font-medium text-text mb-1">Required tools: sops + age</p>
                          <p>Private repo authentication requires <a href="https://github.com/getsops/sops#download" target="_blank" rel="noopener noreferrer" className="text-lavender hover:underline">sops</a> and <a href="https://github.com/FiloSottile/age#installation" target="_blank" rel="noopener noreferrer" className="text-lavender hover:underline">age</a> installed on your machine for credential encryption.</p>
                        </div>
                      </div>
                    </div>

                    {/* Info about credentials */}
                    <div className="p-3 bg-yellow/10 border border-yellow/30 rounded-lg text-xs">
                      <div className="flex items-start gap-2">
                        <AlertCircle className="w-4 h-4 text-yellow flex-shrink-0 mt-0.5" />
                        <div className="text-subtext">
                          <p className="font-medium text-text mb-1">Credentials will be requested during bootstrap</p>
                          <p>The bootstrap script will interactively prompt for your {gitPlatform === 'github' ? 'Personal Access Token' : gitPlatform === 'gitlab' ? 'GitLab token' : 'Gitea token'}. 
                          Credentials are encrypted with SOPS + age and never stored in plain text.</p>
                        </div>
                      </div>
                    </div>
                  </div>
                )}
              </div>

              {/* Skip Git Push - Preview Mode */}
              <div className="border-t border-overlay/50 pt-4 mt-4">
                <label className="flex items-center gap-3 cursor-pointer group">
                  <input
                    type="checkbox"
                    checked={skipGitPush}
                    onChange={(e) => setSkipGitPush(e.target.checked)}
                    className="w-4 h-4 rounded border-overlay bg-surface text-lavender focus:ring-lavender focus:ring-offset-0 cursor-pointer"
                  />
                  <div>
                    <span className="text-sm text-text group-hover:text-lavender transition-colors">
                      Skip Git push (preview mode)
                    </span>
                    <p className="text-xs text-muted mt-0.5">
                      Just generate files locally without pushing to Git or installing Flux. Useful for reviewing the generated structure.
                    </p>
                  </div>
                </label>
              </div>

              {/* Error message */}
              {error && (
                <div className="p-4 bg-red/10 border border-red/30 rounded-lg text-sm text-red flex items-start gap-2">
                  <AlertCircle className="w-4 h-4 mt-0.5 flex-shrink-0" />
                  {error}
                </div>
              )}

              {/* Selected components preview */}
              <div className="p-4 bg-surface/50 rounded-lg border border-overlay/50">
                <h4 className="text-sm font-medium text-text mb-2">Selected Components:</h4>
                <div className="flex flex-wrap gap-2">
                  {selections.map(s => (
                    <span 
                      key={s.id}
                      className="px-3 py-1 bg-overlay/50 rounded-full text-xs text-subtext"
                    >
                      {s.id}
                    </span>
                  ))}
                </div>
              </div>
            </div>
          )}

          {step === 'generating' && (
            <div className="py-12 text-center">
              <Loader2 className="w-12 h-12 text-lavender animate-spin mx-auto mb-4" />
              <h4 className="text-lg font-medium text-text mb-2">Generating Bootstrap...</h4>
              <p className="text-sm text-subtext">
                Creating GitOps repository with Flux manifests
              </p>
            </div>
          )}

          {step === 'done' && bootstrapResponse && (
            <div className="space-y-6">
              <div className="text-center py-4">
                <div className="w-16 h-16 bg-green/20 rounded-full flex items-center justify-center mx-auto mb-4">
                  <Check className="w-8 h-8 text-green" />
                </div>
                <h4 className="text-xl font-semibold text-text mb-2">Ready to Install!</h4>
                <p className="text-subtext">
                  Run this command to bootstrap your cluster
                </p>
              </div>

              {/* Main curl command */}
              <div className="space-y-2">
                <label className="text-sm font-medium text-text flex items-center gap-2">
                  <Zap className="w-4 h-4 text-yellow" />
                  {importedConfig ? 'Update Command (run from existing folder)' : 'Installation Command'}
                  {!importedConfig && bootstrapResponse.devCurlCommand && (
                    <span className="text-xs text-muted font-normal">(from browser/host)</span>
                  )}
                </label>
                <div className="relative group">
                  <pre className="code-block text-sm overflow-x-auto p-4 pr-12">
                    <code className="text-green">
                      {importedConfig 
                        ? `cd ${clusterName} && ${bootstrapResponse.curl_command}`
                        : bootstrapResponse.curl_command}
                    </code>
                  </pre>
                  <button
                    onClick={() => copyToClipboard(
                      importedConfig 
                        ? `cd ${clusterName} && ${bootstrapResponse.curl_command}`
                        : bootstrapResponse.curl_command, 
                      'curl'
                    )}
                    className="absolute top-3 right-3 p-2 bg-overlay hover:bg-overlay/80 rounded-lg transition-colors"
                    title="Copy command"
                  >
                    {copiedField === 'curl' ? (
                      <Check className="w-4 h-4 text-green" />
                    ) : (
                      <Copy className="w-4 h-4 text-muted" />
                    )}
                  </button>
                </div>
              </div>

              {/* Dev mode: Container URL */}
              {bootstrapResponse.devCurlCommand && (
                <div className="space-y-2">
                  <label className="text-sm font-medium text-text flex items-center gap-2">
                    <Container className="w-4 h-4 text-teal" />
                    Toolbox Command
                    <span className="text-xs text-muted font-normal">(from container / make dev-shell)</span>
                  </label>
                  <div className="relative group">
                    <pre className="code-block text-sm overflow-x-auto p-4 pr-12 border border-teal/30">
                      <code className="text-teal">
                        {importedConfig 
                          ? `cd /workspace/${clusterName} && ${bootstrapResponse.devCurlCommand}`
                          : bootstrapResponse.devCurlCommand}
                      </code>
                    </pre>
                    <button
                      onClick={() => copyToClipboard(
                        importedConfig 
                          ? `cd /workspace/${clusterName} && ${bootstrapResponse.devCurlCommand}`
                          : bootstrapResponse.devCurlCommand!, 
                        'dev-curl'
                      )}
                      className="absolute top-3 right-3 p-2 bg-overlay hover:bg-overlay/80 rounded-lg transition-colors"
                      title="Copy command"
                    >
                      {copiedField === 'dev-curl' ? (
                        <Check className="w-4 h-4 text-green" />
                      ) : (
                        <Copy className="w-4 h-4 text-muted" />
                      )}
                    </button>
                  </div>
                </div>
              )}

              {/* Info badges */}
              <div className="flex flex-wrap gap-3">
                <div className="flex items-center gap-2 px-3 py-2 bg-yellow/10 border border-yellow/30 rounded-lg text-sm">
                  <Clock className="w-4 h-4 text-yellow" />
                  <span className="text-text">
                    Expires in {bootstrapResponse.expires_in_minutes} minutes
                  </span>
                </div>
                {bootstrapResponse.one_time && (
                  <div className="flex items-center gap-2 px-3 py-2 bg-blue/10 border border-blue/30 rounded-lg text-sm">
                    <AlertCircle className="w-4 h-4 text-blue" />
                    <span className="text-text">One-time use link</span>
                  </div>
                )}
              </div>

              {/* What it does */}
              <div className="bg-surface/50 rounded-lg border border-overlay/50 overflow-hidden">
                <div className="p-4 border-b border-overlay/50">
                  <h5 className="font-medium text-text">
                    {importedConfig ? 'For updating existing cluster:' : 'What this command does:'}
                  </h5>
                </div>
                <div className="p-4 space-y-3">
                  {importedConfig ? (
                    <>
                      <StepItem number={1}>
                        Run <code className="px-1 py-0.5 bg-overlay rounded text-xs">cd {clusterName}</code> (your existing folder)
                      </StepItem>
                      <StepItem number={2}>
                        Syncs with remote Git repository (pull latest changes)
                      </StepItem>
                      <StepItem number={3}>
                        Updates only changed files (compares checksums)
                      </StepItem>
                      <StepItem number={4}>
                        Skips charts with unchanged versions
                      </StepItem>
                      <StepItem number={5}>
                        Commits, pushes, and triggers Flux reconciliation
                      </StepItem>
                    </>
                  ) : (
                    <>
                      <StepItem number={1}>
                        Creates directory <code className="px-1 py-0.5 bg-overlay rounded text-xs">./{clusterName}</code> with all files
                      </StepItem>
                      <StepItem number={2}>
                        Vendors Helm charts from upstream repositories
                      </StepItem>
                      <StepItem number={3}>
                        Initializes Git repository and pushes to <code className="px-1 py-0.5 bg-overlay rounded text-xs">{repoUrl.split('/').pop()?.replace('.git', '')}</code>
                      </StepItem>
                      <StepItem number={4}>
                        Installs Flux Operator and FluxInstance via Helm
                      </StepItem>
                      <StepItem number={5}>
                        Installs flux-instance — Flux syncs all components automatically
                      </StepItem>
                    </>
                  )}
                </div>
              </div>

              {/* Post-install commands */}
              <div className="space-y-2">
                <label className="text-sm font-medium text-text">After installation:</label>
                <CodeBlock 
                  code="kubectl get kustomizations,helmreleases -A"
                  onCopy={() => copyToClipboard('kubectl get kustomizations,helmreleases -A', 'watch')}
                  copied={copiedField === 'watch'}
                />
              </div>
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="flex items-center justify-end gap-3 p-4 border-t border-overlay bg-surface/30">
          {step === 'config' && (
            <>
              <button onClick={onClose} className="btn-secondary">
                Cancel
              </button>
              <button 
                onClick={handleGenerate} 
                className="btn-primary flex items-center gap-2"
                disabled={!clusterName || !repoUrl}
              >
                <Zap className="w-4 h-4" />
                Generate Command
              </button>
            </>
          )}

          {step === 'done' && (
            <button onClick={onClose} className="btn-primary">
              Done
            </button>
          )}
        </div>
      </motion.div>
    </motion.div>
  );
}

function StepItem({ number, children }: { number: number; children: React.ReactNode }) {
  return (
    <div className="flex items-start gap-3">
      <span className="w-6 h-6 bg-lavender/20 text-lavender rounded-full flex items-center justify-center text-xs font-medium flex-shrink-0">
        {number}
      </span>
      <span className="text-sm text-subtext">{children}</span>
    </div>
  );
}

function CodeBlock({ code, onCopy, copied }: { code: string; onCopy: () => void; copied: boolean }) {
  return (
    <div className="relative group">
      <pre className="code-block text-xs overflow-x-auto">
        <code className="text-subtext">{code}</code>
      </pre>
      <button
        onClick={onCopy}
        className="absolute top-2 right-2 p-1.5 bg-overlay rounded opacity-0 group-hover:opacity-100 transition-opacity"
        title="Copy"
      >
        {copied ? (
          <Check className="w-3 h-3 text-green" />
        ) : (
          <Copy className="w-3 h-3 text-muted" />
        )}
      </button>
    </div>
  );
}

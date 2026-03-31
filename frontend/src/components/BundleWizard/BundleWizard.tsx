'use client';

import React, { useState, useCallback, useEffect, useRef } from 'react';
import { X, ChevronLeft, ChevronRight, Rocket, Copy, Check, Upload } from 'lucide-react';
import yaml from 'js-yaml';
import { StepIndicator } from './StepIndicator';
import { 
  SelectBundle, 
  SelectComponents, 
  ConfigureSettings, 
  ReviewConfig, 
  DeploySettings 
} from './steps';
import { Bundle, WizardState, WIZARD_STEPS } from './types';

interface BundleWizardProps {
  isOpen: boolean;
  onClose: () => void;
}

// Use relative URL - Next.js rewrites /api/* to backend
const API_BASE = '';

export function BundleWizard({ isOpen, onClose }: BundleWizardProps) {
  const [bundles, setBundles] = useState<Bundle[]>([]);
  const [loading, setLoading] = useState(true);
  const [deploying, setDeploying] = useState(false);
  const [deployResult, setDeployResult] = useState<{ curlCommand: string; token: string } | null>(null);
  const [copied, setCopied] = useState(false);
  const [isUpdate, setIsUpdate] = useState(false);
  const [importedClusterName, setImportedClusterName] = useState<string>('');
  const fileInputRef = useRef<HTMLInputElement>(null);

  const [state, setState] = useState<WizardState>({
    currentStep: 0,
    selectedBundle: null,
    enabledComponents: new Set(),
    parameterValues: {},
    gitConfig: {
      provider: 'forgejo',
      repoUrl: '',
      username: '',
      password: '',
      autoPush: true,
      enableSops: false,
      kubeconfigPath: '',
      useDefaultKubeconfig: true,
    },
  });

  // Load bundles
  useEffect(() => {
    if (isOpen) {
      fetch(`${API_BASE}/api/bundles`)
        .then(res => res.json())
        .then(data => {
          setBundles(data);
          setLoading(false);
        })
        .catch(err => {
          console.error('Failed to load bundles:', err);
          setLoading(false);
        });
    }
  }, [isOpen]);

  // Import existing config from k8s-bootstrap.yaml
  const importConfig = useCallback((event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file || bundles.length === 0) return;

    const reader = new FileReader();
    reader.onload = (e) => {
      try {
        const config = yaml.load(e.target?.result as string) as Record<string, any>;
        let bc = config?.bundle_config;

        // Reconstruct bundle_config from selections if missing (legacy configs)
        if (!bc?.bundle_id && config?.selections?.length > 0) {
          const selectionIds = (config.selections as any[]).filter(s => s.enabled !== false).map(s => s.id);
          // Try to match a bundle by checking which bundle has the most matching components
          let bestBundle: (typeof bundles)[number] | null = null;
          let bestScore = 0;
          for (const b of bundles) {
            const bundleCompIds = new Set((b as any).components.map((c: any) => c.id));
            const score = selectionIds.filter(id => bundleCompIds.has(id)).length;
            if (score > bestScore) {
              bestScore = score;
              bestBundle = b;
            }
          }
          if (bestBundle && bestScore >= 3) {
            bc = {
              bundle_id: bestBundle.id,
              enabled_components: selectionIds,
              parameter_values: {},
            };
          }
        }

        if (!bc?.bundle_id) {
          alert('No bundle_config found in this file. Use the component picker for non-bundle configs.');
          return;
        }

        // Find matching bundle
        const bundle = bundles.find(b => b.id === bc.bundle_id);
        if (!bundle) {
          alert(`Bundle "${bc.bundle_id}" not found. Available: ${bundles.map(b => b.id).join(', ')}`);
          return;
        }

        // Restore state from selections values when available
        const enabledComponents = new Set<string>(bc.enabled_components || []);
        const parameterValues = bc.parameter_values || {};

        // If reconstructed from selections, also restore per-component values
        if (!config?.bundle_config && config?.selections) {
          for (const sel of config.selections as any[]) {
            if (sel.enabled !== false && sel.values && Object.keys(sel.values).length > 0) {
              // Component values will be applied during submit
            }
          }
        }

        const gitConfig = {
          provider: bc.git_config?.provider || 'forgejo',
          repoUrl: config.repo_url || '',
          username: bc.git_config?.username || '',
          password: '',
          autoPush: bc.git_config?.autoPush ?? true,
          enableSops: bc.git_config?.enableSops ?? false,
          kubeconfigPath: bc.git_config?.kubeconfigPath || '',
          useDefaultKubeconfig: bc.git_config?.useDefaultKubeconfig ?? true,
        };

        setState({
          currentStep: 1,
          selectedBundle: bundle,
          enabledComponents,
          parameterValues,
          gitConfig,
        });

        setIsUpdate(true);
        setImportedClusterName(config.cluster_name || '');
      } catch (err) {
        alert('Failed to parse config file: ' + (err as Error).message);
      }
    };
    reader.readAsText(file);
    // Reset input so same file can be re-imported
    event.target.value = '';
  }, [bundles]);

  // Initialize components when bundle is selected and go to next step
  const setSelectedBundle = useCallback((bundle: Bundle) => {
    const enabledComponents = new Set<string>();
    const parameterValues: Record<string, string | boolean | number> = {};

    // Enable default components
    bundle.components.forEach(comp => {
      if (comp.required || comp.default_enabled) {
        enabledComponents.add(comp.id);
      }
    });

    // Set default parameter values
    bundle.parameters.forEach(param => {
      if (param.default !== undefined) {
        parameterValues[param.id] = param.default;
      }
    });

    // Set bundle and go to step 1 (Components)
    setState(prev => ({
      ...prev,
      currentStep: 1,
      selectedBundle: bundle,
      enabledComponents,
      parameterValues,
    }));
  }, []);

  // Toggle component
  const toggleComponent = useCallback((componentId: string) => {
    setState(prev => {
      const newEnabled = new Set(prev.enabledComponents);
      if (newEnabled.has(componentId)) {
        newEnabled.delete(componentId);
      } else {
        newEnabled.add(componentId);
      }
      return { ...prev, enabledComponents: newEnabled };
    });
  }, []);

  // Set parameter value with auto component toggling
  const setParameterValue = useCallback((paramId: string, value: string | boolean | number) => {
    setState(prev => {
      const newParamValues = { ...prev.parameterValues, [paramId]: value };
      const newEnabled = new Set(prev.enabledComponents);
      
      // Handle storage_backend
      if (paramId === 'storage_backend') {
        if (value === 'longhorn') {
          newEnabled.add('longhorn');
          newEnabled.delete('piraeus-crds');
          newEnabled.delete('piraeus-operator');
          newEnabled.delete('linstor-cluster');
          newEnabled.delete('linstor-storage-pool');
        } else if (value === 'linstor') {
          newEnabled.delete('longhorn');
          newEnabled.add('piraeus-crds');
          newEnabled.add('piraeus-operator');
          newEnabled.add('linstor-cluster');
          newEnabled.add('linstor-storage-pool');
        }
      }
      
      // Handle environment (MetalLB)
      if (paramId === 'environment') {
        if (value === 'bare-metal') {
          newEnabled.add('metallb');
          newEnabled.add('metallb-config');
        } else {
          newEnabled.delete('metallb');
          newEnabled.delete('metallb-config');
        }
      }
      
      // Handle cni_mode (Cilium)
      if (paramId === 'cni_mode') {
        if (value === 'kube-ovn-cilium') {
          newEnabled.add('cilium');
          newEnabled.add('cilium-cni-chaining');
        } else {
          newEnabled.delete('cilium');
          newEnabled.delete('cilium-cni-chaining');
        }
      }
      
      // Handle ingress_controller
      if (paramId === 'ingress_controller') {
        // Remove all ingress controllers first
        newEnabled.delete('ingress-nginx');
        newEnabled.delete('ingress-traefik');
        
        // Add selected one
        if (value === 'nginx') {
          newEnabled.add('ingress-nginx');
        } else if (value === 'traefik') {
          newEnabled.add('ingress-traefik');
        }
      }
      
      // Handle enable_snapshots
      if (paramId === 'enable_snapshots') {
        if (value) {
          newEnabled.add('snapshot-controller');
        } else {
          newEnabled.delete('snapshot-controller');
        }
      }
      
      // Handle enable_backup
      if (paramId === 'enable_backup') {
        if (value) {
          newEnabled.add('velero');
        } else {
          newEnabled.delete('velero');
        }
      }
      
      // Handle tenant_datastore
      if (paramId === 'tenant_datastore') {
        // Kamaji always enabled for multi-tenancy
        newEnabled.add('kamaji');
        newEnabled.add('kamaji-crds');
        if (value === 'postgresql') {
          newEnabled.add('cloudnative-pg');
          newEnabled.add('cnpg-cluster');
          newEnabled.add('kamaji-datastore');
        } else if (value === 'etcd') {
          newEnabled.delete('cloudnative-pg');
          newEnabled.delete('cnpg-cluster');
          newEnabled.delete('kamaji-datastore');
        }
      }

      // Handle enable_capi
      if (paramId === 'enable_capi') {
        if (value) {
          newEnabled.add('capi-operator');
          newEnabled.add('capi-providers');
        } else {
          newEnabled.delete('capi-operator');
          newEnabled.delete('capi-providers');
          // Also reset infra provider toggle
          newParamValues['capi_infra_kubevirt'] = false;
        }
      }

      // Handle capi_infra_kubevirt (stored in capi-providers values)
      if (paramId === 'capi_infra_kubevirt') {
        // This is handled via component values, not enable/disable
        // The capi-providers chart template uses .Values.infrastructure.kubevirt.enabled
      }
      
      // Handle enable_minio
      if (paramId === 'enable_minio') {
        if (value) {
          newEnabled.add('minio');
        } else {
          newEnabled.delete('minio');
        }
      }
      
      // Handle enable_monitoring
      if (paramId === 'enable_monitoring') {
        if (value) {
          newEnabled.add('prometheus-operator-crds');
          newEnabled.add('victoria-metrics-crds');
          newEnabled.add('victoria-metrics-operator');
          newEnabled.add('victoria-metrics-single');
          newEnabled.add('alloy');
          newEnabled.add('kube-state-metrics');
          newEnabled.add('grafana-operator');
          newEnabled.add('grafana-instance');
        } else {
          newEnabled.delete('prometheus-operator-crds');
          newEnabled.delete('victoria-metrics-crds');
          newEnabled.delete('victoria-metrics-operator');
          newEnabled.delete('victoria-metrics-single');
          newEnabled.delete('alloy');
          newEnabled.delete('kube-state-metrics');
          newEnabled.delete('grafana-operator');
          newEnabled.delete('grafana-instance');
        }
      }
      
      return { ...prev, parameterValues: newParamValues, enabledComponents: newEnabled };
    });
  }, []);

  // Update git config
  const updateGitConfig = useCallback((config: Partial<WizardState['gitConfig']>) => {
    setState(prev => ({
      ...prev,
      gitConfig: { ...prev.gitConfig, ...config },
    }));
  }, []);

  // Navigation
  const nextStep = useCallback(() => {
    setState(prev => ({
      ...prev,
      currentStep: Math.min(prev.currentStep + 1, WIZARD_STEPS.length - 1),
    }));
  }, []);

  const prevStep = useCallback(() => {
    setState(prev => ({
      ...prev,
      currentStep: Math.max(prev.currentStep - 1, 0),
    }));
  }, []);

  const goToStep = useCallback((step: number) => {
    if (step < state.currentStep) {
      setState(prev => ({ ...prev, currentStep: step }));
    }
  }, [state.currentStep]);

  // Can proceed to next step?
  const canProceed = useCallback(() => {
    switch (state.currentStep) {
      case 0: // Bundle selection
        return state.selectedBundle !== null;
      case 1: // Components
        return true;
      case 2: // Configure
        const env = state.parameterValues['environment'];
        const ingressCtrl = state.parameterValues['ingress_controller'];
        const storageBackend = state.parameterValues['storage_backend'];
        const linstorMode = state.parameterValues['linstor_storage_mode'];
        
        // Ingress IP required for bare-metal with ingress
        if (env === 'bare-metal' && ingressCtrl !== 'none') {
          if (!state.parameterValues['ingress_ip']) return false;
        }
        
        // Linstor LVM requires devices
        if (storageBackend === 'linstor' && linstorMode === 'lvm') {
          if (!state.parameterValues['linstor_lvm_devices']) return false;
        }
        
        return true;
      case 3: // Review
        return true;
      case 4: // Deploy
        return Boolean(state.gitConfig.repoUrl);
      default:
        return true;
    }
  }, [state]);

  // Deploy
  const deploy = useCallback(async () => {
    if (!state.selectedBundle) return;

    setDeploying(true);

    try {
      const cniMode = state.parameterValues['cni_mode'] as string || 'kube-ovn-cilium';
      const storageBackend = state.parameterValues['storage_backend'] as string || 'longhorn';
      const storageReplicas = state.parameterValues['storage_replicas'] as string || '2';
      const enableHubble = state.parameterValues['enable_hubble'] as boolean ?? true;
      const enableHubbleIngress = state.parameterValues['enable_hubble_ingress'] as boolean ?? true;
      const enableLonghornIngress = state.parameterValues['enable_longhorn_ingress'] as boolean ?? true;
      const ingressController = state.parameterValues['ingress_controller'] as string || 'nginx';
      const ingressIp = state.parameterValues['ingress_ip'] as string || '';
      const baseDomain = state.parameterValues['base_domain'] as string || '';
      const domain = baseDomain || (ingressIp ? `${ingressIp}.nip.io` : '');
      
      // Custom hosts (or default generated)
      const longhornHost = state.parameterValues['longhorn_host'] as string || `longhorn.${domain}`;
      const hubbleHost = state.parameterValues['hubble_host'] as string || `hubble.${domain}`;
      const grafanaHost = state.parameterValues['grafana_host'] as string || `grafana.${domain}`;
      const vmuiHost = state.parameterValues['vmui_host'] as string || `vmui.${domain}`;
      
      // Monitoring settings
      const enableMonitoring = state.parameterValues['enable_monitoring'] as boolean || false;
      const metricsRetention = state.parameterValues['metrics_retention'] as string || '14d';
      const metricsStorageEnabled = state.parameterValues['metrics_storage_enabled'] as boolean ?? true;
      const metricsStorageSize = state.parameterValues['metrics_storage_size'] as string || '20Gi';
      const enableGrafanaIngress = state.parameterValues['enable_grafana_ingress'] as boolean ?? true;
      const enableVmuiIngress = state.parameterValues['enable_vmui_ingress'] as boolean ?? false;
      
      // Linstor settings
      const linstorMode = state.parameterValues['linstor_storage_mode'] as string || 'file_auto';
      const linstorPoolDir = state.parameterValues['linstor_pool_directory'] as string || '/var/lib/linstor-pools';
      const linstorPoolSize = state.parameterValues['linstor_pool_size'] as string || '100Gi';
      const linstorLvmDevices = state.parameterValues['linstor_lvm_devices'] as string || '';

      // Build components list
      const components = state.selectedBundle.components
        .filter(c => c.required || state.enabledComponents.has(c.id))
        .map(c => {
          const comp: Record<string, unknown> = { id: c.id, enabled: true };
          const values: Record<string, unknown> = {};
          
          // Special handling for Cilium chaining values
          if (c.id === 'cilium' && cniMode === 'kube-ovn-cilium') {
            Object.assign(values, {
              cni: {
                chainingMode: 'generic-veth',
                customConf: true,
                configMap: 'cni-configuration',
                exclusive: false,
              },
              ipam: { mode: 'kubernetes' },
              routingMode: 'native',
              enableIPv4Masquerade: false,
              enableIdentityMark: false,
              devices: 'eth+ ovn0 genev_sys_6081 vxlan_sys_4789',
              kubeProxyReplacement: 'false',
              hubble: {
                enabled: enableHubble,
                ui: {
                  enabled: enableHubble,
                  ingress: enableHubble && enableHubbleIngress && hubbleHost ? {
                    enabled: true,
                    hosts: [hubbleHost],
                    className: ingressController,
                  } : { enabled: false },
                },
              },
            });
          }
          
          // MetalLB config - ingress-specific pool
          if (c.id === 'metallb-config' && ingressIp) {
            const poolName = `ingress-${ingressController}`;
            Object.assign(values, {
              ipAddressPools: [{
                name: poolName,
                addresses: [`${ingressIp}/32`], // Single IP
              }],
              l2Advertisements: [{
                name: poolName,
                ipAddressPools: [poolName],
              }],
            });
          }
          
          // Ingress controller - use specific MetalLB pool
          if (c.id === 'ingress-nginx' && ingressIp) {
            Object.assign(values, {
              controller: {
                service: {
                  type: 'LoadBalancer',
                  annotations: {
                    'metallb.universe.tf/address-pool': 'ingress-nginx',
                  },
                },
              },
            });
          }
          
          if (c.id === 'ingress-traefik' && ingressIp) {
            Object.assign(values, {
              service: {
                type: 'LoadBalancer',
                annotations: {
                  'metallb.universe.tf/address-pool': 'ingress-traefik',
                },
              },
            });
          }
          
          // Longhorn values
          if (c.id === 'longhorn') {
            Object.assign(values, {
              defaultSettings: {
                defaultReplicaCount: storageReplicas,
              },
              ingress: enableLonghornIngress && longhornHost ? {
                enabled: true,
                host: longhornHost,
                ingressClassName: ingressController,
              } : { enabled: false },
            });
          }
          
          // Linstor storage pool values
          if (c.id === 'linstor-storage-pool') {
            const poolValues: Record<string, unknown> = {
              replicaCount: storageReplicas,
              storageMode: linstorMode,
            };
            
            if (linstorMode === 'file_auto' || linstorMode === 'file_limited') {
              poolValues.poolDirectory = linstorPoolDir;
              if (linstorMode === 'file_limited') {
                poolValues.poolSize = linstorPoolSize;
              }
            } else if (linstorMode === 'lvm') {
              poolValues.lvmDevices = linstorLvmDevices.split(',').map(d => d.trim()).filter(Boolean);
            }
            
            Object.assign(values, poolValues);
          }
          
          // Victoria Metrics Single values
          if (c.id === 'victoria-metrics-single' && enableMonitoring) {
            Object.assign(values, {
              retentionPeriod: metricsRetention,
              storage: {
                enabled: metricsStorageEnabled,
                size: metricsStorageSize,
              },
              serviceMonitor: { enabled: true },
              ingress: enableVmuiIngress && vmuiHost ? {
                enabled: true,
                host: vmuiHost,
                ingressClassName: ingressController,
              } : { enabled: false },
            });
          }
          
          // Enable ServiceMonitors for components when monitoring is on
          if (enableMonitoring) {
            // Manifest charts (kubevirt-operator, piraeus-operator)
            if (c.id === 'kubevirt-operator' || c.id === 'piraeus-operator') {
              values.serviceMonitor = { enabled: true };
            }
            // Kube-OVN wrapper chart ServiceMonitor
            if (c.id === 'kube-ovn') {
              values.serviceMonitor = { enabled: true };
            }
          }
          
          // Velero values - add kubevirt-velero-plugin
          if (c.id === 'velero') {
            Object.assign(values, {
              initContainers: [
                {
                  name: 'kubevirt-velero-plugin',
                  image: 'quay.io/kubevirt/kubevirt-velero-plugin:v0.7.0',
                  imagePullPolicy: 'IfNotPresent',
                  volumeMounts: [{ mountPath: '/target', name: 'plugins' }],
                },
              ],
            });
            if (enableMonitoring) {
              values.serviceMonitor = { enabled: true };
            }
          }
          
          // Grafana Instance values
          if (c.id === 'grafana-instance' && enableMonitoring) {
            Object.assign(values, {
              ingress: enableGrafanaIngress && grafanaHost ? {
                enabled: true,
                host: grafanaHost,
              } : { enabled: false },
              datasources: {
                victoriametrics: {
                  enabled: true,
                  url: 'http://vmsingle-vmsingle.victoria-metrics.svc:8429',
                },
              },
              dashboards: {
                nodeExporter: { enabled: true },
                kubernetesCluster: { enabled: true },
                kubevirtVMs: { enabled: true },
                ingressNginx: { enabled: state.enabledComponents.has('ingress-nginx') },
                kubeOvn: { enabled: state.enabledComponents.has('kube-ovn') },
              },
            });
          }
          
          if (Object.keys(values).length > 0) {
            comp.values = values;
          }
          
          return comp;
        });

      // Determine CNI bootstrap
      // Only bootstrap Cilium if:
      // 1. CNI mode is kube-ovn-cilium (chaining mode)
      // 2. Bootstrap is enabled by user
      const shouldBootstrapCni = 
        cniMode === 'kube-ovn-cilium' && 
        state.parameterValues['bootstrap_cni'] !== false &&
        state.selectedBundle.cni_bootstrap?.enabled;

      // Build bundle_config for saving wizard state in k8s-bootstrap.yaml
      const bundleConfig = {
        bundle_id: state.selectedBundle.id,
        parameter_values: state.parameterValues,
        enabled_components: Array.from(state.enabledComponents),
        git_config: {
          provider: state.gitConfig.provider,
          autoPush: state.gitConfig.autoPush,
          enableSops: state.gitConfig.enableSops,
          kubeconfigPath: state.gitConfig.kubeconfigPath,
          useDefaultKubeconfig: state.gitConfig.useDefaultKubeconfig,
          username: state.gitConfig.username,
        },
      };

      const clusterName = isUpdate && importedClusterName 
        ? importedClusterName 
        : 'kubevirt-cluster';

      // Build request
      const request = {
        cluster_name: clusterName,
        repo_url: state.gitConfig.repoUrl,
        branch: 'main',
        components,
        git_auth: state.gitConfig.username ? {
          username: state.gitConfig.username,
          password: state.gitConfig.password,
        } : undefined,
        skip_git_push: !state.gitConfig.autoPush,
        cni_bootstrap: shouldBootstrapCni ? state.selectedBundle.cni_bootstrap?.component : undefined,
        bundle_config: bundleConfig,
      };

      const endpoint = isUpdate ? '/api/update' : '/api/bootstrap';
      const scriptPath = isUpdate ? 'update' : 'bootstrap';

      const response = await fetch(`${API_BASE}${endpoint}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(request),
      });

      if (!response.ok) {
        throw new Error(await response.text());
      }

      const result = await response.json();
      
      // Build full curl command
      const kubeconfigArg = state.gitConfig.useDefaultKubeconfig 
        ? '' 
        : ` --kubeconfig ${state.gitConfig.kubeconfigPath}`;
      const curlCommand = isUpdate
        ? `cd ${clusterName} && curl -sSL ${window.location.origin}/${scriptPath}/${result.token} | bash -s --${kubeconfigArg}`
        : `curl -sSL ${window.location.origin}/${scriptPath}/${result.token} | bash -s --${kubeconfigArg}`;
      
      setDeployResult({ curlCommand, token: result.token });

    } catch (error) {
      console.error('Deploy failed:', error);
      alert('Deployment failed: ' + (error as Error).message);
    } finally {
      setDeploying(false);
    }
  }, [state, isUpdate, importedClusterName]);

  // Copy to clipboard
  const copyCommand = useCallback(async () => {
    if (!deployResult) return;
    
    try {
      await navigator.clipboard.writeText(deployResult.curlCommand);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // Fallback
      const textarea = document.createElement('textarea');
      textarea.value = deployResult.curlCommand;
      document.body.appendChild(textarea);
      textarea.select();
      document.execCommand('copy');
      document.body.removeChild(textarea);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  }, [deployResult]);

  // Reset on close
  const handleClose = useCallback(() => {
    setState({
      currentStep: 0,
      selectedBundle: null,
      enabledComponents: new Set(),
      parameterValues: {},
      gitConfig: {
        provider: 'forgejo',
        repoUrl: '',
        username: '',
        password: '',
        autoPush: true,
        enableSops: false,
        kubeconfigPath: '',
        useDefaultKubeconfig: true,
      },
    });
    setDeployResult(null);
    setIsUpdate(false);
    setImportedClusterName('');
    onClose();
  }, [onClose]);

  if (!isOpen) return null;

  // Extract first IP for domain generation
  const metallbIp = String(state.parameterValues['metallb_ip_range'] || '').match(/(\d+\.\d+\.\d+\.\d+)/)?.[1];

  return (
    <div className="fixed inset-0 bg-crust/80 backdrop-blur-sm flex items-center justify-center z-50 p-4">
      <div className="bg-base rounded-2xl shadow-2xl w-full max-w-3xl max-h-[90vh] flex flex-col border border-overlay">
        {/* Header */}
        <div className="flex items-center justify-between p-6 border-b border-overlay">
          <h2 className="text-xl font-bold text-text">
            {deployResult 
              ? (isUpdate ? '🔄 Update Ready!' : '🎉 Deployment Ready!') 
              : (isUpdate ? '🔄 Update Bundle' : 'Quick Start Bundle')}
          </h2>
          <button
            onClick={handleClose}
            className="p-2 hover:bg-surface rounded-lg transition-colors"
          >
            <X className="w-5 h-5 text-subtext" />
          </button>
        </div>

        {/* Hidden file input for config import */}
        <input
          ref={fileInputRef}
          type="file"
          accept=".yaml,.yml"
          onChange={importConfig}
          className="hidden"
        />

        {/* Content */}
        <div className="flex-1 overflow-y-auto p-6">
          {loading ? (
            <div className="flex items-center justify-center h-64">
              <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-lavender" />
            </div>
          ) : deployResult ? (
            // Success state
            <div className="space-y-6 text-center">
              <div className="text-6xl">🚀</div>
              <div>
                <h3 className="text-xl font-semibold text-text mb-2">Deployment Generated!</h3>
                <p className="text-subtext">Run this command in your terminal:</p>
              </div>
              
              <div className="bg-mantle rounded-lg p-4 text-left relative group">
                <code className="text-sm text-green break-all block pr-10">
                  {deployResult.curlCommand}
                </code>
                <button
                  onClick={copyCommand}
                  className="absolute top-3 right-3 p-2 bg-surface rounded hover:bg-overlay transition-colors"
                >
                  {copied ? (
                    <Check className="w-4 h-4 text-green" />
                  ) : (
                    <Copy className="w-4 h-4 text-subtext" />
                  )}
                </button>
              </div>

              {(() => {
                const ingressIp = state.parameterValues['ingress_ip'] as string || '';
                const baseDomain = state.parameterValues['base_domain'] as string || '';
                const domain = baseDomain || (ingressIp ? `${ingressIp}.nip.io` : '');
                const storageBackend = state.parameterValues['storage_backend'] as string || 'longhorn';
                const cniMode = state.parameterValues['cni_mode'] as string || 'kube-ovn-cilium';
                const enableMonitoring = state.parameterValues['enable_monitoring'] as boolean || false;
                const enableHubble = state.parameterValues['enable_hubble'] as boolean ?? true;
                const enableHubbleIngress = state.parameterValues['enable_hubble_ingress'] as boolean ?? true;
                const enableLonghornIngress = state.parameterValues['enable_longhorn_ingress'] as boolean ?? true;
                const enableGrafanaIngress = state.parameterValues['enable_grafana_ingress'] as boolean ?? true;
                const enableVmuiIngress = state.parameterValues['enable_vmui_ingress'] as boolean ?? false;
                
                const longhornHost = state.parameterValues['longhorn_host'] as string || `longhorn.${domain}`;
                const hubbleHost = state.parameterValues['hubble_host'] as string || `hubble.${domain}`;
                const grafanaHost = state.parameterValues['grafana_host'] as string || `grafana.${domain}`;
                const vmuiHost = state.parameterValues['vmui_host'] as string || `vmui.${domain}`;
                
                if (!domain) return null;
                
                return (
                  <div className="bg-surface/50 rounded-lg p-4 text-left">
                    <h4 className="text-sm font-medium text-text mb-2">After deployment, access:</h4>
                    <div className="space-y-1 text-sm">
                      {/* Storage UI */}
                      {storageBackend === 'longhorn' && enableLonghornIngress && (
                        <div className="flex justify-between">
                          <span className="text-subtext">Longhorn UI:</span>
                          <a href={`http://${longhornHost}`} target="_blank" rel="noopener noreferrer" className="text-lavender hover:underline">
                            http://{longhornHost}
                          </a>
                        </div>
                      )}
                      
                      {/* Hubble UI */}
                      {cniMode === 'kube-ovn-cilium' && enableHubble && enableHubbleIngress && (
                        <div className="flex justify-between">
                          <span className="text-subtext">Hubble UI:</span>
                          <a href={`http://${hubbleHost}`} target="_blank" rel="noopener noreferrer" className="text-lavender hover:underline">
                            http://{hubbleHost}
                          </a>
                        </div>
                      )}
                      
                      {/* Grafana */}
                      {enableMonitoring && enableGrafanaIngress && (
                        <div className="flex justify-between">
                          <span className="text-subtext">Grafana:</span>
                          <a href={`http://${grafanaHost}`} target="_blank" rel="noopener noreferrer" className="text-lavender hover:underline">
                            http://{grafanaHost}
                          </a>
                        </div>
                      )}
                      
                      {/* VMUI */}
                      {enableMonitoring && enableVmuiIngress && (
                        <div className="flex justify-between">
                          <span className="text-subtext">Victoria Metrics UI:</span>
                          <a href={`http://${vmuiHost}`} target="_blank" rel="noopener noreferrer" className="text-lavender hover:underline">
                            http://{vmuiHost}
                          </a>
                        </div>
                      )}
                      
                    </div>
                  </div>
                );
              })()}
            </div>
          ) : (
            <>
              {/* Step indicator */}
              <StepIndicator currentStep={state.currentStep} onStepClick={goToStep} />

              {/* Step content */}
              {state.currentStep === 0 && (
                <>
                  <SelectBundle 
                    bundles={bundles}
                    selectedBundle={state.selectedBundle}
                    onSelect={setSelectedBundle}
                  />
                  
                  {/* Import existing config */}
                  <div className="mt-6 text-center">
                    <div className="inline-flex items-center gap-2 text-xs text-subtext mb-2">
                      <div className="h-px w-8 bg-overlay" />
                      or update existing cluster
                      <div className="h-px w-8 bg-overlay" />
                    </div>
                    <div>
                      <button
                        onClick={() => fileInputRef.current?.click()}
                        className="inline-flex items-center gap-2 px-4 py-2 text-sm text-subtext hover:text-text bg-surface hover:bg-overlay rounded-lg transition-colors border border-overlay"
                      >
                        <Upload className="w-4 h-4" />
                        Import k8s-bootstrap.yaml
                      </button>
                    </div>
                  </div>
                </>
              )}

              {state.currentStep === 1 && state.selectedBundle && (
                <SelectComponents
                  bundle={state.selectedBundle}
                  enabledComponents={state.enabledComponents}
                  onToggle={toggleComponent}
                  parameterValues={state.parameterValues}
                  onParameterChange={setParameterValue}
                />
              )}

              {state.currentStep === 2 && state.selectedBundle && (
                <ConfigureSettings
                  bundle={state.selectedBundle}
                  parameterValues={state.parameterValues}
                  onParameterChange={setParameterValue}
                />
              )}

              {state.currentStep === 3 && state.selectedBundle && (
                <ReviewConfig
                  bundle={state.selectedBundle}
                  enabledComponents={state.enabledComponents}
                  parameterValues={state.parameterValues}
                />
              )}

              {state.currentStep === 4 && (
                <DeploySettings
                  gitConfig={state.gitConfig}
                  onConfigChange={updateGitConfig}
                />
              )}
            </>
          )}
        </div>

        {/* Footer */}
        {!deployResult && (
          <div className="flex items-center justify-between p-6 border-t border-overlay">
            <button
              onClick={state.currentStep === 0 ? handleClose : prevStep}
              className="flex items-center gap-2 px-4 py-2 text-subtext hover:text-text transition-colors"
            >
              <ChevronLeft className="w-4 h-4" />
              {state.currentStep === 0 ? 'Cancel' : 'Back'}
            </button>

            {state.currentStep === 0 ? (
              // No Next button on bundle selection - auto-proceeds on click
              <div />
            ) : state.currentStep < WIZARD_STEPS.length - 1 ? (
              <button
                onClick={nextStep}
                disabled={!canProceed()}
                className={`
                  flex items-center gap-2 px-6 py-2 rounded-lg font-medium transition-all
                  ${canProceed()
                    ? 'bg-lavender text-crust hover:bg-lavender/80'
                    : 'bg-surface text-subtext cursor-not-allowed'
                  }
                `}
              >
                Next
                <ChevronRight className="w-4 h-4" />
              </button>
            ) : (
              <button
                onClick={deploy}
                disabled={!canProceed() || deploying}
                className={`
                  flex items-center gap-2 px-6 py-2 rounded-lg font-medium transition-all
                  ${canProceed() && !deploying
                    ? 'bg-green text-crust hover:bg-green/80'
                    : 'bg-surface text-subtext cursor-not-allowed'
                  }
                `}
              >
                {deploying ? (
                  <>
                    <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-crust" />
                    {isUpdate ? 'Updating...' : 'Deploying...'}
                  </>
                ) : (
                  <>
                    <Rocket className="w-4 h-4" />
                    {isUpdate ? 'Update' : 'Deploy'}
                  </>
                )}
              </button>
            )}
          </div>
        )}

        {/* Close button for success state */}
        {deployResult && (
          <div className="flex justify-center p-6 border-t border-overlay">
            <button
              onClick={handleClose}
              className="px-6 py-2 bg-surface text-text rounded-lg hover:bg-overlay transition-colors"
            >
              Close
            </button>
          </div>
        )}
      </div>
    </div>
  );
}

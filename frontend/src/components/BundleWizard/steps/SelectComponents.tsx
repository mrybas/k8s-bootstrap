'use client';

import React from 'react';
import { Check, Lock, Info, Server, Cloud } from 'lucide-react';
import { Bundle, BundleComponent } from '../types';

interface SelectComponentsProps {
  bundle: Bundle;
  enabledComponents: Set<string>;
  onToggle: (componentId: string) => void;
  parameterValues: Record<string, string | boolean | number>;
  onParameterChange: (paramId: string, value: string | boolean | number) => void;
}

export function SelectComponents({ 
  bundle, 
  enabledComponents, 
  onToggle,
  parameterValues,
  onParameterChange 
}: SelectComponentsProps) {
  // Get current selections
  const environment = parameterValues['environment'] as string || 'bare-metal';
  const cniMode = parameterValues['cni_mode'] as string || 'kube-ovn-cilium';
  const ingressController = parameterValues['ingress_controller'] as string || 'nginx';
  const storageBackend = parameterValues['storage_backend'] as string || 'longhorn';
  const enableMonitoring = parameterValues['enable_monitoring'] as boolean || false;
  const tenantDatastore = parameterValues['tenant_datastore'] as string || 'postgresql';
  const enableMinio = parameterValues['enable_minio'] as boolean ?? true;
  const enableCapi = parameterValues['enable_capi'] as boolean ?? true;
  const capiInfraKubevirt = parameterValues['capi_infra_kubevirt'] as boolean ?? true;

  // Find parameters for selectors
  const envParam = bundle.parameters.find(p => p.id === 'environment');
  const cniModeParam = bundle.parameters.find(p => p.id === 'cni_mode');
  const ingressParam = bundle.parameters.find(p => p.id === 'ingress_controller');
  const storageParam = bundle.parameters.find(p => p.id === 'storage_backend');
  const monitoringParam = bundle.parameters.find(p => p.id === 'enable_monitoring');
  const tenantParam = bundle.parameters.find(p => p.id === 'tenant_datastore');
  const capiParam = bundle.parameters.find(p => p.id === 'enable_capi');
  const capiKubevirtParam = bundle.parameters.find(p => p.id === 'capi_infra_kubevirt');
  const minioParam = bundle.parameters.find(p => p.id === 'enable_minio');

  // Get optional visible components (not hidden, not required, not managed by selectors)
  const optionalComponents = bundle.components.filter(c => 
    !c.required && 
    !c.hidden && 
    !['longhorn', 'piraeus-operator', 'linstor-cluster', 'linstor-storage-pool',
      'ingress-nginx', 'ingress-traefik', 'metallb', 'metallb-config',
      'cilium', 'cilium-cni-chaining',
      'cloudnative-pg', 'cnpg-cluster', 'kamaji-crds', 'kamaji', 'kamaji-datastore',
      'capi-operator', 'capi-providers', 'minio',
      'prometheus-operator-crds', 'victoria-metrics-operator', 'victoria-metrics-single',
      'grafana-operator', 'grafana-instance'].includes(c.id)
  );

  return (
    <div className="space-y-6">
      <div className="text-center">
        <h2 className="text-2xl font-bold text-text mb-2">Customize Components</h2>
        <p className="text-subtext">Configure your stack based on your environment</p>
      </div>

      <div className="max-w-2xl mx-auto space-y-6">
        {/* Environment Selection */}
        {envParam && (
          <Section title="Environment" icon="🌍">
            <div className="grid grid-cols-2 gap-3">
              <SelectCard
                selected={environment === 'bare-metal'}
                onClick={() => onParameterChange('environment', 'bare-metal')}
                icon={<Server className="w-5 h-5" />}
                title="Bare-metal / On-prem"
                description="Includes MetalLB for LoadBalancer"
              />
              <SelectCard
                selected={environment === 'cloud'}
                onClick={() => {}} // Disabled for now
                icon={<Cloud className="w-5 h-5" />}
                title="Cloud (managed K8s)"
                description="Coming soon..."
                disabled={true}
              />
            </div>
          </Section>
        )}

        {/* CNI Configuration */}
        {cniModeParam && (
          <Section title="CNI Configuration" icon="🔗">
            <div className="space-y-2">
              {(cniModeParam.options as Array<{ value: string; label: string }>)?.map(opt => (
                <RadioCard
                  key={opt.value}
                  selected={cniMode === opt.value}
                  onClick={() => onParameterChange('cni_mode', opt.value)}
                  title={opt.label}
                  description={
                    opt.value === 'kube-ovn-cilium' 
                      ? 'Full features: VPCs, eBPF policies, Hubble observability'
                      : 'Use if Cilium already installed or only need Kube-OVN features'
                  }
                />
              ))}
            </div>
          </Section>
        )}

        {/* Ingress Controller */}
        {ingressParam && (
          <Section title="Ingress Controller" icon="🌐">
            <div className="grid grid-cols-3 gap-2">
              {(ingressParam.options as Array<{ value: string; label: string }>)?.map(opt => (
                <button
                  key={opt.value}
                  onClick={() => onParameterChange('ingress_controller', opt.value)}
                  className={`
                    p-3 rounded-lg border-2 text-center transition-all
                    ${ingressController === opt.value
                      ? 'border-lavender bg-lavender/10 text-lavender'
                      : 'border-overlay hover:border-lavender/50 text-subtext'
                    }
                  `}
                >
                  <span className="text-sm font-medium">{opt.label}</span>
                </button>
              ))}
            </div>
          </Section>
        )}

        {/* Storage Backend */}
        {storageParam && (
          <Section title="Storage Backend" icon="💾">
            <div className="grid grid-cols-2 gap-3">
              {(storageParam.options as Array<{ value: string; label: string }>)?.map(opt => (
                <SelectCard
                  key={opt.value}
                  selected={storageBackend === opt.value}
                  onClick={() => onParameterChange('storage_backend', opt.value)}
                  title={opt.label}
                  description={
                    opt.value === 'longhorn'
                      ? 'Simple setup, web UI included'
                      : 'High performance DRBD, requires extension'
                  }
                />
              ))}
            </div>
          </Section>
        )}

        {/* Multi-tenancy */}
        {tenantParam && (
          <Section title="Multi-tenancy" icon="🏢">
            <div className="space-y-3">
              <p className="text-xs text-subtext">
                Kamaji creates tenant Kubernetes API servers as lightweight Pods.
                Each tenant gets its own control plane with shared or dedicated DataStore.
              </p>
              <div className="space-y-2">
                {(tenantParam.options as Array<{ value: string; label: string }>)?.map(opt => (
                  <RadioCard
                    key={opt.value}
                    selected={tenantDatastore === opt.value}
                    onClick={() => onParameterChange('tenant_datastore', opt.value)}
                    title={opt.label}
                    description={
                      opt.value === 'postgresql'
                        ? 'CloudNativePG + kine — simple ops, shared HA PostgreSQL'
                        : 'Built-in etcd per tenant — higher performance, more resources'
                    }
                  />
                ))}
              </div>

              {/* Cluster API sub-section */}
              {capiParam && (
                <div className="mt-4 pt-3 border-t border-overlay/30">
                  <div
                    onClick={() => onParameterChange('enable_capi', !enableCapi)}
                    className={`
                      p-3 rounded-lg border-2 cursor-pointer transition-all
                      ${enableCapi
                        ? 'border-lavender bg-lavender/10'
                        : 'border-overlay hover:border-lavender/50'
                      }
                    `}
                  >
                    <div className="flex items-start gap-3">
                      <div className={`
                        w-5 h-5 rounded border-2 flex items-center justify-center mt-0.5 shrink-0
                        ${enableCapi ? 'bg-lavender border-lavender' : 'border-overlay'}
                      `}>
                        {enableCapi && <Check className="w-3 h-3 text-crust" />}
                      </div>
                      <div>
                        <span className={`font-medium ${enableCapi ? 'text-lavender' : 'text-text'}`}>
                          Cluster API (CAPI)
                        </span>
                        <p className="text-xs text-subtext mt-0.5">
                          Declarative lifecycle management — create, scale, upgrade, delete tenant clusters
                        </p>
                      </div>
                    </div>
                  </div>

                  {/* Infrastructure Providers */}
                  {enableCapi && capiKubevirtParam && (
                    <div className="mt-3 ml-6 space-y-2">
                      <p className="text-xs text-subtext font-medium uppercase tracking-wider">Infrastructure Providers</p>
                      <div
                        onClick={() => onParameterChange('capi_infra_kubevirt', !capiInfraKubevirt)}
                        className={`
                          p-3 rounded-lg border cursor-pointer transition-all
                          ${capiInfraKubevirt
                            ? 'border-lavender/50 bg-lavender/5'
                            : 'border-overlay hover:border-lavender/30'
                          }
                        `}
                      >
                        <div className="flex items-start gap-3">
                          <div className={`
                            w-4 h-4 rounded border-2 flex items-center justify-center mt-0.5 shrink-0
                            ${capiInfraKubevirt ? 'bg-lavender border-lavender' : 'border-overlay'}
                          `}>
                            {capiInfraKubevirt && <Check className="w-2.5 h-2.5 text-crust" />}
                          </div>
                          <div>
                            <span className={`text-sm font-medium ${capiInfraKubevirt ? 'text-lavender' : 'text-text'}`}>
                              KubeVirt VMs
                            </span>
                            <p className="text-xs text-subtext mt-0.5">
                              Tenant workers as VMs on shared physical nodes
                            </p>
                          </div>
                        </div>
                      </div>
                      <div className="p-3 rounded-lg border border-overlay/30 opacity-50 cursor-not-allowed">
                        <div className="flex items-start gap-3">
                          <div className="w-4 h-4 rounded border-2 border-overlay flex items-center justify-center mt-0.5 shrink-0" />
                          <div>
                            <div className="flex items-center gap-2">
                              <span className="text-sm font-medium text-subtext">Metal3 (bare-metal)</span>
                              <span className="text-[10px] px-1.5 py-0.5 rounded bg-overlay/50 text-subtext">coming soon</span>
                            </div>
                            <p className="text-xs text-subtext mt-0.5">
                              Tenant workers on dedicated bare-metal nodes via IPMI/BMC
                            </p>
                          </div>
                        </div>
                      </div>
                    </div>
                  )}
                </div>
              )}
            </div>
          </Section>
        )}

        {/* S3 Storage */}
        {minioParam && (
          <Section title="S3 Storage" icon="🪣">
            <div
              onClick={() => onParameterChange('enable_minio', !enableMinio)}
              className={`
                p-4 rounded-lg border-2 cursor-pointer transition-all
                ${enableMinio
                  ? 'border-lavender bg-lavender/10'
                  : 'border-overlay hover:border-lavender/50'
                }
              `}
            >
              <div className="flex items-start gap-3">
                <div className={`
                  w-5 h-5 rounded border-2 flex items-center justify-center mt-0.5 shrink-0
                  ${enableMinio ? 'bg-lavender border-lavender' : 'border-overlay'}
                `}>
                  {enableMinio && <Check className="w-3 h-3 text-crust" />}
                </div>
                <div>
                  <span className={`font-medium ${enableMinio ? 'text-lavender' : 'text-text'}`}>
                    MinIO S3-compatible Storage
                  </span>
                  <p className="text-xs text-subtext mt-1">
                    Object storage for Velero backups, Loki chunks, and artifacts
                  </p>
                </div>
              </div>
            </div>
          </Section>
        )}

        {/* Monitoring */}
        {monitoringParam && (
          <Section title="Monitoring" icon="📊">
            <div
              onClick={() => onParameterChange('enable_monitoring', !enableMonitoring)}
              className={`
                p-4 rounded-lg border-2 cursor-pointer transition-all
                ${enableMonitoring
                  ? 'border-lavender bg-lavender/10'
                  : 'border-overlay hover:border-lavender/50'
                }
              `}
            >
              <div className="flex items-start gap-3">
                <div className={`
                  w-5 h-5 rounded border-2 flex items-center justify-center mt-0.5 shrink-0
                  ${enableMonitoring ? 'bg-lavender border-lavender' : 'border-overlay'}
                `}>
                  {enableMonitoring && <Check className="w-3 h-3 text-crust" />}
                </div>
                <div>
                  <div className="flex items-center gap-2">
                    <span className={`font-medium ${enableMonitoring ? 'text-lavender' : 'text-text'}`}>
                      Victoria Metrics + Grafana
                    </span>
                  </div>
                  <p className="text-xs text-subtext mt-1">
                    Cluster monitoring with dashboards, metrics storage, and alerting
                  </p>
                  {enableMonitoring && (
                    <div className="mt-2 flex items-center gap-2 text-xs text-green">
                      <Info className="w-3 h-3" />
                      <span>Configure storage & retention in next step</span>
                    </div>
                  )}
                </div>
              </div>
            </div>
          </Section>
        )}

        {/* Optional Components */}
        {optionalComponents.length > 0 && (
          <Section title="Optional Components" icon="➕">
            <div className="space-y-2">
              {optionalComponents.map(comp => {
                const isEnabled = enabledComponents.has(comp.id);
                return (
                  <div
                    key={comp.id}
                    className={`
                      flex items-center justify-between p-3 rounded-lg cursor-pointer
                      transition-all duration-150
                      ${isEnabled ? 'bg-lavender/10 border border-lavender/30' : 'bg-surface/30 hover:bg-surface/50'}
                    `}
                    onClick={() => onToggle(comp.id)}
                  >
                    <div className="flex items-center gap-3">
                      <div className={`
                        w-5 h-5 rounded border-2 flex items-center justify-center
                        ${isEnabled ? 'bg-lavender border-lavender' : 'border-overlay'}
                      `}>
                        {isEnabled && <Check className="w-3 h-3 text-crust" />}
                      </div>
                      <div>
                        <span className="text-sm font-medium text-text">
                          {formatComponentName(comp.id)}
                        </span>
                        {comp.description && (
                          <p className="text-xs text-subtext">{comp.description}</p>
                        )}
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          </Section>
        )}

        {/* Summary of what will be installed */}
        <Section title="Summary" icon="📋">
          <div className="bg-surface/30 rounded-lg p-3 text-sm space-y-1">
            <SummaryItem label="CNI" value={cniMode === 'kube-ovn-cilium' ? 'Kube-OVN + Cilium' : 'Kube-OVN only'} />
            <SummaryItem label="Multi-NIC" value="Multus CNI" />
            <SummaryItem label="LoadBalancer" value={environment === 'bare-metal' ? 'MetalLB' : 'Cloud provider'} />
            <SummaryItem label="Ingress" value={ingressController === 'none' ? 'None' : ingressController.toUpperCase()} />
            <SummaryItem label="Storage" value={storageBackend === 'longhorn' ? 'Longhorn' : 'Linstor'} />
            <SummaryItem label="VMs" value="KubeVirt + CDI" />
            {tenantParam && (
              <>
                <SummaryItem 
                  label="Multi-tenancy" 
                  value={`Kamaji + ${tenantDatastore === 'postgresql' ? 'PostgreSQL (kine)' : 'etcd'}`} 
                />
                {enableCapi && (
                  <SummaryItem 
                    label="Cluster API" 
                    value={`CAPI${capiInfraKubevirt ? ' + KubeVirt provider' : ''}`} 
                  />
                )}
              </>
            )}
            {minioParam && (
              <SummaryItem label="S3 Storage" value={enableMinio ? 'MinIO' : 'None'} />
            )}
            <SummaryItem label="Monitoring" value={enableMonitoring ? 'Victoria Metrics + Grafana' : 'None'} />
          </div>
        </Section>
      </div>
    </div>
  );
}

// Helper components
function Section({ title, icon, children }: { title: string; icon: string; children: React.ReactNode }) {
  return (
    <div className="space-y-3">
      <h3 className="text-sm font-semibold text-lavender uppercase tracking-wider flex items-center gap-2">
        <span>{icon}</span>
        {title}
      </h3>
      {children}
    </div>
  );
}

function SelectCard({ 
  selected, 
  onClick, 
  icon, 
  title, 
  description,
  disabled = false,
}: { 
  selected: boolean; 
  onClick: () => void; 
  icon?: React.ReactNode;
  title: string; 
  description: string;
  disabled?: boolean;
}) {
  return (
    <button
      onClick={disabled ? undefined : onClick}
      disabled={disabled}
      className={`
        p-4 rounded-lg border-2 text-left transition-all w-full
        ${disabled
          ? 'border-overlay/30 bg-surface/20 opacity-50 cursor-not-allowed'
          : selected 
            ? 'border-lavender bg-lavender/10' 
            : 'border-overlay hover:border-lavender/50'
        }
      `}
    >
      <div className="flex items-start gap-3">
        <div className={`
          w-5 h-5 rounded-full border-2 flex items-center justify-center mt-0.5 shrink-0
          ${selected ? 'border-lavender bg-lavender' : 'border-overlay'}
        `}>
          {selected && <div className="w-2 h-2 bg-crust rounded-full" />}
        </div>
        <div>
          <div className="flex items-center gap-2">
            {icon && <span className={selected ? 'text-lavender' : 'text-subtext'}>{icon}</span>}
            <span className={`font-medium ${selected ? 'text-lavender' : 'text-text'}`}>
              {title}
            </span>
          </div>
          <p className="text-xs text-subtext mt-1">{description}</p>
        </div>
      </div>
    </button>
  );
}

function RadioCard({
  selected,
  onClick,
  title,
  description,
}: {
  selected: boolean;
  onClick: () => void;
  title: string;
  description: string;
}) {
  return (
    <button
      onClick={onClick}
      className={`
        w-full p-3 rounded-lg border-2 text-left transition-all
        ${selected 
          ? 'border-lavender bg-lavender/10' 
          : 'border-overlay hover:border-lavender/50'
        }
      `}
    >
      <div className="flex items-start gap-3">
        <div className={`
          w-4 h-4 rounded-full border-2 flex items-center justify-center mt-0.5 shrink-0
          ${selected ? 'border-lavender bg-lavender' : 'border-overlay'}
        `}>
          {selected && <div className="w-1.5 h-1.5 bg-crust rounded-full" />}
        </div>
        <div>
          <span className={`text-sm font-medium ${selected ? 'text-lavender' : 'text-text'}`}>
            {title}
          </span>
          <p className="text-xs text-subtext mt-0.5">{description}</p>
        </div>
      </div>
    </button>
  );
}

function SummaryItem({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex justify-between">
      <span className="text-subtext">{label}:</span>
      <span className="text-text font-medium">{value}</span>
    </div>
  );
}

function formatComponentName(id: string): string {
  return id.split('-').map(w => w.charAt(0).toUpperCase() + w.slice(1)).join(' ');
}

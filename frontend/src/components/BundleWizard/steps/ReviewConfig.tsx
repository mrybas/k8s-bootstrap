'use client';

import React from 'react';
import { AlertTriangle, Check, X } from 'lucide-react';
import { Bundle } from '../types';

interface ReviewConfigProps {
  bundle: Bundle;
  enabledComponents: Set<string>;
  parameterValues: Record<string, string | boolean | number>;
}

export function ReviewConfig({ bundle, enabledComponents, parameterValues }: ReviewConfigProps) {
  // Get selections
  const environment = parameterValues['environment'] as string || 'bare-metal';
  const cniMode = parameterValues['cni_mode'] as string || 'kube-ovn-cilium';
  const ingressController = parameterValues['ingress_controller'] as string || 'nginx';
  const storageBackend = parameterValues['storage_backend'] as string || 'longhorn';
  const storageReplicas = parameterValues['storage_replicas'] as string || '2';
  const enableHubble = parameterValues['enable_hubble'] as boolean ?? true;
  const enableSnapshots = parameterValues['enable_snapshots'] as boolean ?? true;
  
  // Ingress settings
  const ingressIp = parameterValues['ingress_ip'] as string || '';
  const baseDomain = parameterValues['base_domain'] as string || '';
  const domain = baseDomain || (ingressIp ? `${ingressIp}.nip.io` : '');
  const enableLonghornIngress = parameterValues['enable_longhorn_ingress'] as boolean ?? true;
  const enableHubbleIngress = parameterValues['enable_hubble_ingress'] as boolean ?? true;
  const longhornHost = parameterValues['longhorn_host'] as string || `longhorn.${domain}`;
  const hubbleHost = parameterValues['hubble_host'] as string || `hubble.${domain}`;
  
  // Linstor settings
  const linstorMode = parameterValues['linstor_storage_mode'] as string || 'file_auto';
  const linstorPoolDir = parameterValues['linstor_pool_directory'] as string || '/var/lib/linstor-pools';
  const linstorPoolSize = parameterValues['linstor_pool_size'] as string || '100Gi';
  const linstorLvmDevices = parameterValues['linstor_lvm_devices'] as string || '';
  
  // Monitoring settings
  const enableMonitoring = parameterValues['enable_monitoring'] as boolean ?? false;
  const metricsRetention = parameterValues['metrics_retention'] as string || '14d';
  const metricsStorageEnabled = parameterValues['metrics_storage_enabled'] as boolean ?? true;
  const metricsStorageSize = parameterValues['metrics_storage_size'] as string || '20Gi';
  const enableGrafanaIngress = parameterValues['enable_grafana_ingress'] as boolean ?? true;
  const enableVmuiIngress = parameterValues['enable_vmui_ingress'] as boolean ?? false;
  const enableVmagentIngress = parameterValues['enable_vmagent_ingress'] as boolean ?? false;
  const grafanaHost = parameterValues['grafana_host'] as string || `grafana.${domain}`;
  const vmuiHost = parameterValues['vmui_host'] as string || `vmui.${domain}`;
  const vmagentHost = parameterValues['vmagent_host'] as string || `vmagent.${domain}`;

  const StatusIcon = ({ enabled }: { enabled: boolean }) => (
    enabled 
      ? <Check className="w-3 h-3 text-green" />
      : <X className="w-3 h-3 text-red" />
  );

  return (
    <div className="space-y-6">
      <div className="text-center">
        <h2 className="text-2xl font-bold text-text mb-2">Review Configuration</h2>
        <p className="text-subtext">Verify your settings before deployment</p>
      </div>

      <div className="max-w-2xl mx-auto space-y-4">
        {/* Bundle Header */}
        <div className="bg-lavender/10 border border-lavender/30 rounded-xl p-4 flex items-center gap-4">
          <span className="text-4xl">{bundle.icon}</span>
          <div>
            <h3 className="font-bold text-text text-lg">{bundle.name}</h3>
            <p className="text-sm text-subtext">{bundle.description}</p>
          </div>
        </div>

        <div className="grid md:grid-cols-2 gap-4">
          {/* Environment */}
          <ConfigCard title="Environment" icon="🌍">
            <ConfigItem 
              label="Type" 
              value={environment === 'bare-metal' ? 'Bare-metal / On-prem' : 'Cloud (managed K8s)'} 
            />
          </ConfigCard>

          {/* Networking */}
          <ConfigCard title="Networking" icon="🔗">
            <ConfigItem 
              label="CNI" 
              value={cniMode === 'kube-ovn-cilium' ? 'Kube-OVN + Cilium' : 'Kube-OVN only'} 
            />
            <ConfigItem label="Multi-NIC" value="Multus CNI" />
            {environment === 'bare-metal' && (
              <ConfigItem label="LoadBalancer" value="MetalLB" />
            )}
          </ConfigCard>

          {/* Ingress */}
          {ingressController !== 'none' && (
            <ConfigCard title="Ingress" icon="🌐">
              <ConfigItem 
                label="Controller" 
                value={ingressController.toUpperCase()} 
              />
              {environment === 'bare-metal' && ingressIp && (
                <ConfigItem label="IP Address" value={ingressIp} />
              )}
              <ConfigItem label="Base Domain" value={domain || 'Not set'} />
            </ConfigCard>
          )}

          {/* Domains */}
          {ingressController !== 'none' && domain && (
            <ConfigCard title="Service URLs" icon="🔗">
              {storageBackend === 'longhorn' && (
                <ConfigItem 
                  label="Longhorn UI" 
                  value={enableLonghornIngress ? longhornHost : 'Disabled'}
                  enabled={enableLonghornIngress}
                />
              )}
              {cniMode === 'kube-ovn-cilium' && enableHubble && (
                <ConfigItem 
                  label="Hubble UI" 
                  value={enableHubbleIngress ? hubbleHost : 'Disabled'}
                  enabled={enableHubbleIngress}
                />
              )}
              {enableMonitoring && enableGrafanaIngress && (
                <ConfigItem 
                  label="Grafana" 
                  value={grafanaHost}
                  enabled={true}
                />
              )}
              {enableMonitoring && enableVmuiIngress && (
                <ConfigItem 
                  label="VMUI" 
                  value={vmuiHost}
                  enabled={true}
                />
              )}
              {enableMonitoring && enableVmagentIngress && (
                <ConfigItem 
                  label="VMAgent" 
                  value={vmagentHost}
                  enabled={true}
                />
              )}
            </ConfigCard>
          )}

          {/* Storage */}
          <ConfigCard title="Storage" icon="💾">
            <ConfigItem 
              label="Backend" 
              value={storageBackend === 'longhorn' ? 'Longhorn' : 'Linstor (DRBD)'} 
            />
            <ConfigItem 
              label="Replicas" 
              value={`${storageReplicas} (${Number(storageReplicas) >= 2 ? 'HA' : 'No HA'})`} 
            />
            <ConfigItem 
              label="Snapshots" 
              value={enableSnapshots ? 'Enabled' : 'Disabled'}
              enabled={enableSnapshots}
            />
            
            {storageBackend === 'linstor' && (
              <>
                <div className="border-t border-overlay/50 my-2" />
                <ConfigItem 
                  label="Linstor Mode" 
                  value={
                    linstorMode === 'file_auto' ? 'File Pool (auto)' :
                    linstorMode === 'file_limited' ? 'File Pool (limited)' :
                    'LVM (dedicated disks)'
                  } 
                />
                {(linstorMode === 'file_auto' || linstorMode === 'file_limited') && (
                  <ConfigItem label="Pool Directory" value={linstorPoolDir} />
                )}
                {linstorMode === 'file_limited' && (
                  <ConfigItem label="Pool Size" value={linstorPoolSize} />
                )}
                {linstorMode === 'lvm' && (
                  <ConfigItem label="LVM Devices" value={linstorLvmDevices || 'Not set'} />
                )}
              </>
            )}
          </ConfigCard>

          {/* Virtualization */}
          <ConfigCard title="Virtualization" icon="🖥️">
            <ConfigItem label="KubeVirt" value="Enabled" enabled={true} />
            <ConfigItem label="CDI" value="Enabled" enabled={true} />
          </ConfigCard>

          {/* Observability */}
          {cniMode === 'kube-ovn-cilium' && (
            <ConfigCard title="Observability" icon="📊">
              <ConfigItem 
                label="Hubble" 
                value={enableHubble ? 'Enabled' : 'Disabled'}
                enabled={enableHubble}
              />
            </ConfigCard>
          )}

          {/* Monitoring */}
          {enableMonitoring && (
            <ConfigCard title="Monitoring" icon="📈">
              <ConfigItem label="Backend" value="Victoria Metrics" enabled={true} />
              <ConfigItem label="Retention" value={metricsRetention} />
              <ConfigItem 
                label="Storage" 
                value={metricsStorageEnabled ? `${metricsStorageSize} (Persistent)` : 'Ephemeral ⚠️'}
                enabled={metricsStorageEnabled}
              />
              <ConfigItem label="Grafana" value="Enabled" enabled={true} />
              {ingressController !== 'none' && domain && (
                <>
                  <div className="border-t border-overlay/50 my-2" />
                  <ConfigItem 
                    label="Grafana UI" 
                    value={enableGrafanaIngress ? grafanaHost : 'Disabled'}
                    enabled={enableGrafanaIngress}
                  />
                  <ConfigItem 
                    label="VMUI" 
                    value={enableVmuiIngress ? vmuiHost : 'Disabled'}
                    enabled={enableVmuiIngress}
                  />
                </>
              )}
            </ConfigCard>
          )}
        </div>

        {/* Important Notes */}
        {bundle.notes && bundle.notes.length > 0 && (
          <div className="mt-6 space-y-3">
            <h4 className="text-sm font-semibold text-yellow flex items-center gap-2">
              <AlertTriangle className="w-4 h-4" />
              Important Notes
            </h4>
            <div className="grid gap-2">
              {bundle.notes.slice(0, 2).map((note, idx) => (
                <div 
                  key={idx}
                  className="bg-yellow/5 border border-yellow/20 rounded-lg p-3"
                >
                  <h5 className="font-medium text-sm text-text mb-1">{note.title}</h5>
                  <p className="text-xs text-subtext whitespace-pre-line">{note.content}</p>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

function ConfigCard({ 
  title, 
  icon, 
  children 
}: { 
  title: string; 
  icon: string; 
  children: React.ReactNode;
}) {
  return (
    <div className="bg-surface/30 rounded-lg p-4 border border-overlay/50">
      <h4 className="font-medium text-text flex items-center gap-2 mb-3 text-sm">
        <span>{icon}</span>
        {title}
      </h4>
      <div className="space-y-2 text-sm">
        {children}
      </div>
    </div>
  );
}

function ConfigItem({ 
  label, 
  value, 
  enabled 
}: { 
  label: string; 
  value: string; 
  enabled?: boolean;
}) {
  return (
    <div className="flex items-center justify-between gap-2">
      <span className="text-subtext flex items-center gap-1.5">
        {enabled !== undefined && (
          enabled 
            ? <Check className="w-3 h-3 text-green" />
            : <X className="w-3 h-3 text-red/50" />
        )}
        {label}
      </span>
      <span className={`text-text font-medium text-right ${enabled === false ? 'text-subtext line-through' : ''}`}>
        {value}
      </span>
    </div>
  );
}

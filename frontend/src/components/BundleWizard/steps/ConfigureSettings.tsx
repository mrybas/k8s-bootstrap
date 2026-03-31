'use client';

import React, { useMemo, useEffect } from 'react';
import { Info, Globe, HardDrive, Network } from 'lucide-react';
import { Bundle, BundleParameter } from '../types';

interface ConfigureSettingsProps {
  bundle: Bundle;
  parameterValues: Record<string, string | boolean | number>;
  onParameterChange: (paramId: string, value: string | boolean | number) => void;
}

// Evaluate show_if condition
function evaluateShowIf(showIf: string, values: Record<string, string | boolean | number>): boolean {
  // Handle complex conditions like: environment == "bare-metal" && ingress_controller != "none"
  const conditions = showIf.split('&&').map(c => c.trim());
  
  return conditions.every(condition => {
    const match = condition.match(/(\w+)\s*([!=]=)\s*"([^"]+)"/);
    if (!match) return true;
    
    const [, paramName, operator, expectedValue] = match;
    const actualValue = String(values[paramName] || '');
    
    if (operator === '==') {
      return actualValue === expectedValue;
    } else if (operator === '!=') {
      return actualValue !== expectedValue;
    }
    return true;
  });
}

export function ConfigureSettings({ 
  bundle, 
  parameterValues, 
  onParameterChange 
}: ConfigureSettingsProps) {
  // Get current selections
  const environment = parameterValues['environment'] as string || 'bare-metal';
  const cniMode = parameterValues['cni_mode'] as string || 'kube-ovn-cilium';
  const ingressController = parameterValues['ingress_controller'] as string || 'nginx';
  const storageBackend = parameterValues['storage_backend'] as string || 'longhorn';
  const linstorMode = parameterValues['linstor_storage_mode'] as string || 'file_auto';
  const ingressIp = parameterValues['ingress_ip'] as string || '';
  const baseDomain = parameterValues['base_domain'] as string || '';
  const enableMonitoring = parameterValues['enable_monitoring'] as boolean || false;
  const metricsStorageEnabled = parameterValues['metrics_storage_enabled'] as boolean ?? true;

  // Auto-generate base domain from IP
  const generatedDomain = useMemo(() => {
    if (baseDomain) return baseDomain;
    if (ingressIp) return `${ingressIp}.nip.io`;
    return '';
  }, [ingressIp, baseDomain]);

  // Auto-set base_domain when IP changes and domain is empty
  useEffect(() => {
    if (ingressIp && !baseDomain) {
      // Don't auto-set, just show preview
    }
  }, [ingressIp, baseDomain]);

  // Filter parameters for this step (exclude step 2 params)
  const configParams = useMemo(() => {
    return bundle.parameters.filter(param => {
      // Skip parameters shown on Step 2
      if (['environment', 'cni_mode', 'ingress_controller', 'storage_backend'].includes(param.id)) {
        return false;
      }
      
      // Check show_if condition
      if (param.show_if && !evaluateShowIf(param.show_if, parameterValues)) {
        return false;
      }

      return true;
    });
  }, [bundle.parameters, parameterValues]);

  // Group by category
  const networkingParams = configParams.filter(p => p.category === 'networking');
  const ingressParams = configParams.filter(p => p.category === 'ingress');
  const storageParams = configParams.filter(p => p.category === 'storage');
  const observabilityParams = configParams.filter(p => p.category === 'observability');

  return (
    <div className="space-y-6">
      <div className="text-center">
        <h2 className="text-2xl font-bold text-text mb-2">Configuration</h2>
        <p className="text-subtext">Configure settings for your selected components</p>
      </div>

      <div className="max-w-xl mx-auto space-y-8">
        {/* Networking Section */}
        {networkingParams.length > 0 && (
          <Section title="Networking" icon={<Network className="w-4 h-4" />}>
            {networkingParams.map(param => (
              <ParameterInput
                key={param.id}
                param={param}
                value={parameterValues[param.id]}
                onChange={(value) => onParameterChange(param.id, value)}
              />
            ))}
          </Section>
        )}

        {/* Ingress Section */}
        {ingressController !== 'none' && environment === 'bare-metal' && (
          <Section title="Ingress & Domains" icon={<Globe className="w-4 h-4" />}>
            {/* Ingress IP */}
            <div className="space-y-1">
              <label className="flex items-center gap-2 text-sm font-medium text-text">
                Ingress IP Address
                <span className="text-red">*</span>
                <Tooltip text="Single IP from your network for the ingress controller. MetalLB will reserve this IP exclusively for ingress." />
              </label>
              <input
                type="text"
                value={ingressIp}
                onChange={(e) => onParameterChange('ingress_ip', e.target.value)}
                placeholder="192.168.1.100"
                className="w-full px-3 py-2 bg-surface border border-overlay rounded-lg text-text text-sm placeholder:text-subtext/50 focus:outline-none focus:ring-2 focus:ring-lavender/50 focus:border-lavender"
              />
            </div>

            {/* Base Domain */}
            <div className="space-y-1">
              <label className="flex items-center gap-2 text-sm font-medium text-text">
                Base Domain
                <Tooltip text="Leave empty to auto-generate from IP using nip.io. Or enter your own domain." />
              </label>
              <input
                type="text"
                value={baseDomain}
                onChange={(e) => onParameterChange('base_domain', e.target.value)}
                placeholder={ingressIp ? `${ingressIp}.nip.io (auto)` : 'Enter IP first'}
                className="w-full px-3 py-2 bg-surface border border-overlay rounded-lg text-text text-sm placeholder:text-subtext/50 focus:outline-none focus:ring-2 focus:ring-lavender/50 focus:border-lavender"
              />
            </div>

            {/* Ingress Hosts - Editable */}
            {generatedDomain && (
              <div className="bg-surface/50 rounded-lg p-4 border border-overlay/50 space-y-3">
                <p className="text-xs text-subtext font-medium">Service Ingress Hosts:</p>
                
                {/* Longhorn Ingress */}
                {storageBackend === 'longhorn' && (
                  <IngressHostInput
                    id="longhorn_host"
                    label="Longhorn UI"
                    defaultHost={`longhorn.${generatedDomain}`}
                    value={parameterValues['longhorn_host'] as string}
                    enabled={parameterValues['enable_longhorn_ingress'] !== false}
                    onToggle={(enabled) => onParameterChange('enable_longhorn_ingress', enabled)}
                    onChange={(value) => onParameterChange('longhorn_host', value)}
                  />
                )}

                {/* Hubble Ingress */}
                {cniMode === 'kube-ovn-cilium' && parameterValues['enable_hubble'] !== false && (
                  <IngressHostInput
                    id="hubble_host"
                    label="Hubble UI"
                    defaultHost={`hubble.${generatedDomain}`}
                    value={parameterValues['hubble_host'] as string}
                    enabled={parameterValues['enable_hubble_ingress'] !== false}
                    onToggle={(enabled) => onParameterChange('enable_hubble_ingress', enabled)}
                    onChange={(value) => onParameterChange('hubble_host', value)}
                  />
                )}

                {/* Grafana Ingress */}
                {enableMonitoring && (
                  <IngressHostInput
                    id="grafana_host"
                    label="Grafana Dashboards"
                    defaultHost={`grafana.${generatedDomain}`}
                    value={parameterValues['grafana_host'] as string}
                    enabled={parameterValues['enable_grafana_ingress'] !== false}
                    onToggle={(enabled) => onParameterChange('enable_grafana_ingress', enabled)}
                    onChange={(value) => onParameterChange('grafana_host', value)}
                  />
                )}

                {/* VMUI Ingress */}
                {enableMonitoring && (
                  <IngressHostInput
                    id="vmui_host"
                    label="Victoria Metrics UI"
                    defaultHost={`vmui.${generatedDomain}`}
                    value={parameterValues['vmui_host'] as string}
                    enabled={parameterValues['enable_vmui_ingress'] === true}
                    onToggle={(enabled) => onParameterChange('enable_vmui_ingress', enabled)}
                    onChange={(value) => onParameterChange('vmui_host', value)}
                  />
                )}

                {/* VMAgent Ingress */}
                {enableMonitoring && (
                  <IngressHostInput
                    id="vmagent_host"
                    label="VMAgent UI (targets)"
                    defaultHost={`vmagent.${generatedDomain}`}
                    value={parameterValues['vmagent_host'] as string}
                    enabled={parameterValues['enable_vmagent_ingress'] === true}
                    onToggle={(enabled) => onParameterChange('enable_vmagent_ingress', enabled)}
                    onChange={(value) => onParameterChange('vmagent_host', value)}
                  />
                )}
              </div>
            )}
          </Section>
        )}

        {/* Storage Section */}
        {storageParams.length > 0 && (
          <Section title="Storage" icon={<HardDrive className="w-4 h-4" />}>
            {/* Storage Replicas - always show */}
            <ParameterInput
              param={bundle.parameters.find(p => p.id === 'storage_replicas')!}
              value={parameterValues['storage_replicas']}
              onChange={(value) => onParameterChange('storage_replicas', value)}
            />

            {/* Linstor specific settings */}
            {storageBackend === 'linstor' && (
              <>
                {/* Storage Mode */}
                <ParameterInput
                  param={bundle.parameters.find(p => p.id === 'linstor_storage_mode')!}
                  value={parameterValues['linstor_storage_mode']}
                  onChange={(value) => onParameterChange('linstor_storage_mode', value)}
                />

                {/* Pool Directory (for file modes) */}
                {linstorMode !== 'lvm' && (
                  <ParameterInput
                    param={bundle.parameters.find(p => p.id === 'linstor_pool_directory')!}
                    value={parameterValues['linstor_pool_directory']}
                    onChange={(value) => onParameterChange('linstor_pool_directory', value)}
                  />
                )}

                {/* Pool Size (for file_limited) */}
                {linstorMode === 'file_limited' && (
                  <ParameterInput
                    param={bundle.parameters.find(p => p.id === 'linstor_pool_size')!}
                    value={parameterValues['linstor_pool_size']}
                    onChange={(value) => onParameterChange('linstor_pool_size', value)}
                  />
                )}

                {/* LVM Devices (for lvm mode) */}
                {linstorMode === 'lvm' && (
                  <ParameterInput
                    param={bundle.parameters.find(p => p.id === 'linstor_lvm_devices')!}
                    value={parameterValues['linstor_lvm_devices']}
                    onChange={(value) => onParameterChange('linstor_lvm_devices', value)}
                  />
                )}
              </>
            )}

            {/* Snapshots toggle */}
            <ParameterInput
              param={bundle.parameters.find(p => p.id === 'enable_snapshots')!}
              value={parameterValues['enable_snapshots']}
              onChange={(value) => onParameterChange('enable_snapshots', value)}
            />
          </Section>
        )}

        {/* Observability Section */}
        {cniMode === 'kube-ovn-cilium' && (
          <Section title="Observability" icon={<Network className="w-4 h-4" />}>
            <ParameterInput
              param={bundle.parameters.find(p => p.id === 'enable_hubble')!}
              value={parameterValues['enable_hubble']}
              onChange={(value) => onParameterChange('enable_hubble', value)}
            />
          </Section>
        )}

        {/* Monitoring Section */}
        {enableMonitoring && (
          <Section title="Monitoring Settings" icon={<Info className="w-4 h-4" />}>
            {/* Metrics Retention */}
            <ParameterInput
              param={bundle.parameters.find(p => p.id === 'metrics_retention')!}
              value={parameterValues['metrics_retention']}
              onChange={(value) => onParameterChange('metrics_retention', value)}
            />

            {/* Persistent Storage Toggle */}
            <div className="space-y-2">
              <ParameterInput
                param={bundle.parameters.find(p => p.id === 'metrics_storage_enabled')!}
                value={parameterValues['metrics_storage_enabled']}
                onChange={(value) => onParameterChange('metrics_storage_enabled', value)}
              />

              {/* Warning if storage disabled */}
              {!metricsStorageEnabled && (
                <div className="flex items-start gap-2 p-3 bg-yellow/10 border border-yellow/30 rounded-lg">
                  <span className="text-yellow">⚠️</span>
                  <div className="text-xs text-yellow">
                    <p className="font-medium">Ephemeral Storage Warning</p>
                    <p className="mt-1 text-subtext">
                      Metrics will be lost when Victoria Metrics restarts. 
                      Not recommended for production use.
                    </p>
                  </div>
                </div>
              )}
            </div>

            {/* Storage Size (if enabled) */}
            {metricsStorageEnabled && (
              <ParameterInput
                param={bundle.parameters.find(p => p.id === 'metrics_storage_size')!}
                value={parameterValues['metrics_storage_size']}
                onChange={(value) => onParameterChange('metrics_storage_size', value)}
              />
            )}
          </Section>
        )}
      </div>
    </div>
  );
}

// Section component
function Section({ 
  title, 
  icon, 
  children 
}: { 
  title: string; 
  icon: React.ReactNode; 
  children: React.ReactNode;
}) {
  return (
    <section className="space-y-4">
      <h3 className="text-sm font-semibold text-lavender uppercase tracking-wider flex items-center gap-2">
        {icon}
        {title}
      </h3>
      <div className="space-y-4">
        {children}
      </div>
    </section>
  );
}

// Tooltip component
function Tooltip({ text }: { text: string }) {
  return (
    <div className="group relative">
      <Info className="w-3.5 h-3.5 text-subtext hover:text-lavender cursor-help" />
      <div className="absolute left-0 top-5 w-64 p-2 bg-mantle border border-overlay rounded-lg text-xs text-subtext shadow-lg opacity-0 invisible group-hover:opacity-100 group-hover:visible transition-all duration-200 z-10">
        {text}
      </div>
    </div>
  );
}

// Ingress host input with toggle
function IngressHostInput({
  id,
  label,
  defaultHost,
  value,
  enabled,
  onToggle,
  onChange,
}: {
  id: string;
  label: string;
  defaultHost: string;
  value: string | undefined;
  enabled: boolean;
  onToggle: (enabled: boolean) => void;
  onChange: (value: string) => void;
}) {
  const displayValue = value || defaultHost;
  
  return (
    <div className="space-y-1">
      <div className="flex items-center gap-2">
        <input
          type="checkbox"
          id={id}
          checked={enabled}
          onChange={(e) => onToggle(e.target.checked)}
          className="w-4 h-4 rounded border-overlay bg-surface text-lavender focus:ring-lavender"
        />
        <label htmlFor={id} className="text-sm text-text cursor-pointer font-medium">
          {label}
        </label>
      </div>
      {enabled && (
        <input
          type="text"
          value={displayValue}
          onChange={(e) => onChange(e.target.value)}
          placeholder={defaultHost}
          className="w-full px-3 py-1.5 bg-mantle border border-overlay rounded text-sm text-text placeholder:text-subtext/50 focus:outline-none focus:ring-1 focus:ring-lavender/50 focus:border-lavender"
        />
      )}
    </div>
  );
}

// Parameter input component
function ParameterInput({ 
  param, 
  value, 
  onChange 
}: { 
  param: BundleParameter | undefined; 
  value: string | boolean | number | undefined;
  onChange: (value: string | boolean | number) => void;
}) {
  if (!param) return null;

  const currentValue = value ?? param.default;

  return (
    <div className="space-y-1">
      <label className="flex items-center gap-2 text-sm font-medium text-text">
        {param.name}
        {param.required && <span className="text-red">*</span>}
        {param.description && <Tooltip text={param.description} />}
      </label>

      {param.type === 'string' && (
        <input
          type="text"
          value={String(currentValue || '')}
          onChange={(e) => onChange(e.target.value)}
          placeholder={(param as any).placeholder || String(param.default || '')}
          className="w-full px-3 py-2 bg-surface border border-overlay rounded-lg text-text text-sm placeholder:text-subtext/50 focus:outline-none focus:ring-2 focus:ring-lavender/50 focus:border-lavender"
        />
      )}

      {param.type === 'select' && param.options && (
        <select
          value={String(currentValue || '')}
          onChange={(e) => onChange(e.target.value)}
          className="w-full px-3 py-2 bg-surface border border-overlay rounded-lg text-text text-sm focus:outline-none focus:ring-2 focus:ring-lavender/50 focus:border-lavender"
        >
          {param.options.map((opt) => {
            const optValue = typeof opt === 'object' ? opt.value : opt;
            const optLabel = typeof opt === 'object' ? opt.label : opt;
            return (
              <option key={optValue} value={optValue}>{optLabel}</option>
            );
          })}
        </select>
      )}

      {param.type === 'boolean' && (
        <label className="flex items-center gap-2 cursor-pointer">
          <input
            type="checkbox"
            checked={Boolean(currentValue)}
            onChange={(e) => onChange(e.target.checked)}
            className="w-4 h-4 rounded border-overlay bg-surface text-lavender focus:ring-lavender"
          />
          <span className="text-sm text-subtext">Enabled</span>
        </label>
      )}
    </div>
  );
}

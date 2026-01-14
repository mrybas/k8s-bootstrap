'use client';

import { useState, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { X, Plus, Trash2, Edit2, Check, ChevronDown, ChevronRight, Code2 } from 'lucide-react';
import type { Component, ComponentInstance } from '@/types';

interface InstanceModalProps {
  isOpen: boolean;
  onClose: () => void;
  component: Component;
  instances: ComponentInstance[];
  onSave: (instances: ComponentInstance[]) => void;
  schema?: {
    jsonSchema: Record<string, any>;
    uiSchema: Record<string, any>;
    defaultValues: Record<string, any>;
  };
}

// Component-specific default values
const getDefaultInstanceValues = (componentId: string, namespace: string): Record<string, any> => {
  switch (componentId) {
    case 'grafana-instance':
      return {
        ingress: {
          enabled: false,
          host: '',
          tls: false,
          clusterIssuer: 'letsencrypt-production'
        },
        persistence: {
          enabled: false,
          size: '10Gi',
          storageClass: ''
        },
        resources: {
          requests: { cpu: '100m', memory: '128Mi' },
          limits: { cpu: '500m', memory: '512Mi' }
        },
        adminCredentials: {
          adminUser: 'admin',
          adminPassword: ''
        }
      };
    
    case 'victoria-metrics-single':
      return {
        server: {
          retentionPeriod: '14d',
          persistentVolume: {
            enabled: false,
            size: '50Gi',
            storageClass: ''
          },
          resources: {
            requests: { cpu: '250m', memory: '512Mi' },
            limits: { cpu: '1', memory: '2Gi' }
          }
        },
        ingress: {
          enabled: false,
          host: '',
          tls: false
        }
      };
    
    case 'rook-ceph-cluster':
      return {
        cephClusterSpec: {
          mon: { count: 3 },
          mgr: { count: 2 },
          dashboard: { enabled: true, ssl: true },
          storage: {
            useAllNodes: true,
            useAllDevices: true
          }
        },
        cephBlockPools: [{
          name: 'ceph-blockpool',
          spec: { replicated: { size: 3 } },
          storageClass: {
            enabled: true,
            name: 'ceph-block',
            isDefault: true
          }
        }]
      };
    
    default:
      return {
        resources: {
          requests: { cpu: '100m', memory: '128Mi' },
          limits: { cpu: '500m', memory: '512Mi' }
        }
      };
  }
};

// Component-specific form fields
const getComponentSections = (componentId: string): string[] => {
  switch (componentId) {
    case 'grafana-instance':
      return ['basic', 'credentials', 'ingress', 'persistence', 'resources', 'raw'];
    case 'victoria-metrics-single':
      return ['basic', 'retention', 'persistence', 'resources', 'ingress', 'raw'];
    case 'rook-ceph-cluster':
      return ['basic', 'cluster', 'storage', 'pools', 'raw'];
    default:
      return ['basic', 'resources', 'raw'];
  }
};

export function InstanceModal({
  isOpen,
  onClose,
  component,
  instances,
  onSave,
  schema
}: InstanceModalProps) {
  const [localInstances, setLocalInstances] = useState<ComponentInstance[]>(instances);
  const [editingIndex, setEditingIndex] = useState<number | null>(null);
  const [showAddForm, setShowAddForm] = useState(instances.length === 0);
  const [expandedSections, setExpandedSections] = useState<Set<string>>(new Set(['basic']));
  
  const defaultNamespace = component.defaultNamespace || component.id.replace('-instance', '').replace('-single', '').replace('-cluster', '');
  
  const [formData, setFormData] = useState<ComponentInstance>({
    name: '',
    namespace: defaultNamespace,
    values: getDefaultInstanceValues(component.id, defaultNamespace),
    rawOverrides: ''
  });

  useEffect(() => {
    if (isOpen) {
      setLocalInstances(instances);
      setEditingIndex(null);
      setShowAddForm(instances.length === 0);
      resetForm();
    }
  }, [isOpen, instances]);

  const resetForm = () => {
    setFormData({
      name: '',
      namespace: defaultNamespace,
      values: getDefaultInstanceValues(component.id, defaultNamespace),
      rawOverrides: ''
    });
    setExpandedSections(new Set(['basic']));
  };

  const toggleSection = (section: string) => {
    setExpandedSections(prev => {
      const next = new Set(prev);
      if (next.has(section)) next.delete(section);
      else next.add(section);
      return next;
    });
  };

  const updateFormValue = (path: string, value: any) => {
    setFormData(prev => {
      const newValues = JSON.parse(JSON.stringify(prev.values));
      const parts = path.split('.');
      let current: any = newValues;
      
      for (let i = 0; i < parts.length - 1; i++) {
        if (!current[parts[i]]) current[parts[i]] = {};
        current = current[parts[i]];
      }
      current[parts[parts.length - 1]] = value;
      
      return { ...prev, values: newValues };
    });
  };

  const handleAddOrUpdateInstance = () => {
    if (!formData.name.trim() || !formData.namespace.trim()) return;
    
    const isDuplicate = localInstances.some((i, idx) => 
      i.name === formData.name && idx !== editingIndex
    );
    if (isDuplicate) {
      alert('Instance name must be unique');
      return;
    }
    
    if (editingIndex !== null) {
      const updated = [...localInstances];
      updated[editingIndex] = { ...formData };
      setLocalInstances(updated);
    } else {
      setLocalInstances([...localInstances, { ...formData }]);
    }
    
    resetForm();
    setShowAddForm(false);
    setEditingIndex(null);
  };

  const handleEditInstance = (index: number) => {
    const instance = localInstances[index];
    setFormData({
      ...instance,
      values: { ...getDefaultInstanceValues(component.id, instance.namespace), ...instance.values }
    });
    setEditingIndex(index);
    setShowAddForm(true);
    setExpandedSections(new Set(['basic']));
  };

  const handleRemoveInstance = (index: number) => {
    setLocalInstances(localInstances.filter((_, i) => i !== index));
  };

  const handleSave = () => {
    onSave(localInstances);
    onClose();
  };

  if (!isOpen) return null;

  const isFormValid = formData.name.trim() && formData.namespace.trim();
  const sections = getComponentSections(component.id);

  return (
    <AnimatePresence>
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        className="fixed inset-0 bg-black/60 backdrop-blur-sm z-50 flex items-center justify-center p-4"
        onClick={onClose}
      >
        <motion.div
          initial={{ scale: 0.95, opacity: 0 }}
          animate={{ scale: 1, opacity: 1 }}
          exit={{ scale: 0.95, opacity: 0 }}
          className="bg-surface border border-overlay rounded-2xl shadow-2xl max-w-3xl w-full max-h-[85vh] overflow-hidden"
          onClick={(e) => e.stopPropagation()}
        >
          {/* Header */}
          <div className="flex items-center justify-between p-6 border-b border-overlay">
            <div>
              <h2 className="text-xl font-semibold text-text flex items-center gap-2">
                <span>{component.icon}</span>
                {component.name}
              </h2>
              <p className="text-sm text-subtext mt-1">
                Configure multiple deployments in different namespaces
              </p>
            </div>
            <button
              onClick={onClose}
              className="p-2 rounded-lg hover:bg-overlay transition-colors text-muted hover:text-text"
            >
              <X className="w-5 h-5" />
            </button>
          </div>

          {/* Content */}
          <div className="p-6 overflow-y-auto max-h-[60vh]">
            {/* Existing instances */}
            {localInstances.length > 0 && !showAddForm && (
              <div className="space-y-3 mb-6">
                <h3 className="text-sm font-medium text-subtext uppercase tracking-wide">
                  Configured Instances ({localInstances.length})
                </h3>
                {localInstances.map((instance, index) => (
                  <div
                    key={instance.name}
                    className="flex items-center justify-between p-4 rounded-lg bg-base border border-overlay hover:border-overlay/80"
                  >
                    <div className="flex-1">
                      <div className="font-medium text-text">{instance.name}</div>
                      <div className="text-sm text-muted flex flex-wrap gap-3 mt-1">
                        <span>namespace: <span className="text-mauve">{instance.namespace}</span></span>
                        {instance.values?.ingress?.enabled && (
                          <span>🌐 <span className="text-blue">{instance.values.ingress.host}</span></span>
                        )}
                        {instance.values?.persistence?.enabled && (
                          <span>💾 {instance.values.persistence.size}</span>
                        )}
                        {instance.values?.server?.persistentVolume?.enabled && (
                          <span>💾 {instance.values.server.persistentVolume.size}</span>
                        )}
                        {instance.values?.cephClusterSpec?.mon?.count && (
                          <span>🔧 {instance.values.cephClusterSpec.mon.count} MONs</span>
                        )}
                        {instance.rawOverrides && (
                          <span className="text-yellow">📝 Custom YAML</span>
                        )}
                      </div>
                    </div>
                    <div className="flex items-center gap-2">
                      <button
                        onClick={() => handleEditInstance(index)}
                        className="p-2 rounded-lg hover:bg-mauve/20 text-muted hover:text-mauve transition-colors"
                        title="Edit instance"
                      >
                        <Edit2 className="w-4 h-4" />
                      </button>
                      <button
                        onClick={() => handleRemoveInstance(index)}
                        className="p-2 rounded-lg hover:bg-red/20 text-muted hover:text-red transition-colors"
                        title="Remove instance"
                      >
                        <Trash2 className="w-4 h-4" />
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            )}

            {/* Add/Edit instance form */}
            {showAddForm ? (
              <div className="space-y-4">
                <div className="flex items-center justify-between">
                  <h3 className="text-sm font-medium text-text">
                    {editingIndex !== null ? 'Edit Instance' : 'Add New Instance'}
                  </h3>
                  {localInstances.length > 0 && (
                    <button
                      onClick={() => { setShowAddForm(false); setEditingIndex(null); resetForm(); }}
                      className="text-sm text-muted hover:text-text"
                    >
                      Cancel
                    </button>
                  )}
                </div>

                {/* Basic Settings - always shown */}
                {sections.includes('basic') && (
                  <CollapsibleSection 
                    title="Basic Settings" 
                    section="basic"
                    expanded={expandedSections.has('basic')}
                    onToggle={() => toggleSection('basic')}
                    required
                  >
                    <div className="grid grid-cols-2 gap-4">
                      <div>
                        <label className="block text-sm text-subtext mb-1">Instance Name *</label>
                        <input
                          type="text"
                          value={formData.name}
                          onChange={(e) => setFormData({ ...formData, name: e.target.value.toLowerCase().replace(/[^a-z0-9-]/g, '') })}
                          placeholder="e.g., production"
                          className="w-full px-3 py-2 rounded-lg bg-base border border-overlay text-text placeholder:text-muted focus:border-mauve focus:outline-none"
                        />
                      </div>
                      <div>
                        <label className="block text-sm text-subtext mb-1">Namespace *</label>
                        <input
                          type="text"
                          value={formData.namespace}
                          onChange={(e) => setFormData({ ...formData, namespace: e.target.value.toLowerCase().replace(/[^a-z0-9-]/g, '') })}
                          placeholder={defaultNamespace}
                          className="w-full px-3 py-2 rounded-lg bg-base border border-overlay text-text placeholder:text-muted focus:border-mauve focus:outline-none"
                        />
                      </div>
                    </div>
                  </CollapsibleSection>
                )}

                {/* Grafana: Credentials */}
                {sections.includes('credentials') && (
                  <CollapsibleSection 
                    title="Admin Credentials" 
                    section="credentials"
                    expanded={expandedSections.has('credentials')}
                    onToggle={() => toggleSection('credentials')}
                  >
                    <div className="grid grid-cols-2 gap-4">
                      <div>
                        <label className="block text-sm text-subtext mb-1">Admin User</label>
                        <input
                          type="text"
                          value={formData.values?.adminCredentials?.adminUser || 'admin'}
                          onChange={(e) => updateFormValue('adminCredentials.adminUser', e.target.value)}
                          className="w-full px-3 py-2 rounded-lg bg-base border border-overlay text-text focus:border-mauve focus:outline-none"
                        />
                      </div>
                      <div>
                        <label className="block text-sm text-subtext mb-1">Admin Password</label>
                        <input
                          type="password"
                          value={formData.values?.adminCredentials?.adminPassword || ''}
                          onChange={(e) => updateFormValue('adminCredentials.adminPassword', e.target.value)}
                          placeholder="Leave empty for auto-generated"
                          className="w-full px-3 py-2 rounded-lg bg-base border border-overlay text-text placeholder:text-muted focus:border-mauve focus:outline-none"
                        />
                      </div>
                    </div>
                  </CollapsibleSection>
                )}

                {/* VictoriaMetrics: Retention */}
                {sections.includes('retention') && (
                  <CollapsibleSection 
                    title="Retention Settings" 
                    section="retention"
                    expanded={expandedSections.has('retention')}
                    onToggle={() => toggleSection('retention')}
                    badge={formData.values?.server?.retentionPeriod}
                  >
                    <div>
                      <label className="block text-sm text-subtext mb-1">Retention Period</label>
                      <input
                        type="text"
                        value={formData.values?.server?.retentionPeriod || '14d'}
                        onChange={(e) => updateFormValue('server.retentionPeriod', e.target.value)}
                        placeholder="14d, 30d, 90d, 1y"
                        className="w-full px-3 py-2 rounded-lg bg-base border border-overlay text-text placeholder:text-muted focus:border-mauve focus:outline-none"
                      />
                      <p className="text-xs text-muted mt-1">Examples: 14d (14 days), 4w (4 weeks), 3m (3 months), 1y (1 year)</p>
                    </div>
                  </CollapsibleSection>
                )}

                {/* Ceph: Cluster Config */}
                {sections.includes('cluster') && (
                  <CollapsibleSection 
                    title="Cluster Configuration" 
                    section="cluster"
                    expanded={expandedSections.has('cluster')}
                    onToggle={() => toggleSection('cluster')}
                  >
                    <div className="grid grid-cols-2 gap-4">
                      <div>
                        <label className="block text-sm text-subtext mb-1">Monitor Count</label>
                        <input
                          type="number"
                          min={1}
                          value={formData.values?.cephClusterSpec?.mon?.count || 3}
                          onChange={(e) => updateFormValue('cephClusterSpec.mon.count', parseInt(e.target.value))}
                          className="w-full px-3 py-2 rounded-lg bg-base border border-overlay text-text focus:border-mauve focus:outline-none"
                        />
                        <p className="text-xs text-muted mt-1">Odd number recommended (1, 3, 5)</p>
                      </div>
                      <div>
                        <label className="block text-sm text-subtext mb-1">Manager Count</label>
                        <input
                          type="number"
                          min={1}
                          value={formData.values?.cephClusterSpec?.mgr?.count || 2}
                          onChange={(e) => updateFormValue('cephClusterSpec.mgr.count', parseInt(e.target.value))}
                          className="w-full px-3 py-2 rounded-lg bg-base border border-overlay text-text focus:border-mauve focus:outline-none"
                        />
                      </div>
                      <label className="flex items-center gap-3 cursor-pointer">
                        <input
                          type="checkbox"
                          checked={formData.values?.cephClusterSpec?.dashboard?.enabled ?? true}
                          onChange={(e) => updateFormValue('cephClusterSpec.dashboard.enabled', e.target.checked)}
                          className="w-4 h-4 rounded border-overlay text-mauve focus:ring-mauve"
                        />
                        <span className="text-sm text-text">Enable Dashboard</span>
                      </label>
                      <label className="flex items-center gap-3 cursor-pointer">
                        <input
                          type="checkbox"
                          checked={formData.values?.cephClusterSpec?.dashboard?.ssl ?? true}
                          onChange={(e) => updateFormValue('cephClusterSpec.dashboard.ssl', e.target.checked)}
                          className="w-4 h-4 rounded border-overlay text-mauve focus:ring-mauve"
                        />
                        <span className="text-sm text-text">Dashboard SSL</span>
                      </label>
                    </div>
                  </CollapsibleSection>
                )}

                {/* Ceph: Storage */}
                {sections.includes('storage') && (
                  <CollapsibleSection 
                    title="Storage Configuration" 
                    section="storage"
                    expanded={expandedSections.has('storage')}
                    onToggle={() => toggleSection('storage')}
                  >
                    <div className="space-y-3">
                      <label className="flex items-center gap-3 cursor-pointer">
                        <input
                          type="checkbox"
                          checked={formData.values?.cephClusterSpec?.storage?.useAllNodes ?? true}
                          onChange={(e) => updateFormValue('cephClusterSpec.storage.useAllNodes', e.target.checked)}
                          className="w-4 h-4 rounded border-overlay text-mauve focus:ring-mauve"
                        />
                        <div>
                          <span className="text-sm text-text">Use All Nodes</span>
                          <p className="text-xs text-muted">Automatically use all nodes for storage</p>
                        </div>
                      </label>
                      <label className="flex items-center gap-3 cursor-pointer">
                        <input
                          type="checkbox"
                          checked={formData.values?.cephClusterSpec?.storage?.useAllDevices ?? true}
                          onChange={(e) => updateFormValue('cephClusterSpec.storage.useAllDevices', e.target.checked)}
                          className="w-4 h-4 rounded border-overlay text-mauve focus:ring-mauve"
                        />
                        <div>
                          <span className="text-sm text-text">Use All Devices</span>
                          <p className="text-xs text-muted">Automatically use all available devices</p>
                        </div>
                      </label>
                    </div>
                  </CollapsibleSection>
                )}

                {/* Ceph: Block Pools */}
                {sections.includes('pools') && (
                  <CollapsibleSection 
                    title="Block Pool" 
                    section="pools"
                    expanded={expandedSections.has('pools')}
                    onToggle={() => toggleSection('pools')}
                    badge={formData.values?.cephBlockPools?.[0]?.storageClass?.name}
                  >
                    <div className="grid grid-cols-2 gap-4">
                      <div>
                        <label className="block text-sm text-subtext mb-1">Pool Name</label>
                        <input
                          type="text"
                          value={formData.values?.cephBlockPools?.[0]?.name || 'ceph-blockpool'}
                          onChange={(e) => {
                            const pools = [...(formData.values?.cephBlockPools || [])];
                            if (!pools[0]) pools[0] = { name: '', spec: { replicated: { size: 3 } }, storageClass: {} };
                            pools[0].name = e.target.value;
                            setFormData({ ...formData, values: { ...formData.values, cephBlockPools: pools } });
                          }}
                          className="w-full px-3 py-2 rounded-lg bg-base border border-overlay text-text focus:border-mauve focus:outline-none"
                        />
                      </div>
                      <div>
                        <label className="block text-sm text-subtext mb-1">Replication Size</label>
                        <input
                          type="number"
                          min={1}
                          value={formData.values?.cephBlockPools?.[0]?.spec?.replicated?.size || 3}
                          onChange={(e) => {
                            const pools = [...(formData.values?.cephBlockPools || [])];
                            if (!pools[0]) pools[0] = { name: 'ceph-blockpool', spec: { replicated: { size: 3 } }, storageClass: {} };
                            if (!pools[0].spec) pools[0].spec = { replicated: { size: 3 } };
                            if (!pools[0].spec.replicated) pools[0].spec.replicated = { size: 3 };
                            pools[0].spec.replicated.size = parseInt(e.target.value);
                            setFormData({ ...formData, values: { ...formData.values, cephBlockPools: pools } });
                          }}
                          className="w-full px-3 py-2 rounded-lg bg-base border border-overlay text-text focus:border-mauve focus:outline-none"
                        />
                      </div>
                      <div>
                        <label className="block text-sm text-subtext mb-1">StorageClass Name</label>
                        <input
                          type="text"
                          value={formData.values?.cephBlockPools?.[0]?.storageClass?.name || 'ceph-block'}
                          onChange={(e) => {
                            const pools = [...(formData.values?.cephBlockPools || [])];
                            if (!pools[0]) pools[0] = { name: 'ceph-blockpool', spec: { replicated: { size: 3 } }, storageClass: {} };
                            if (!pools[0].storageClass) pools[0].storageClass = {};
                            pools[0].storageClass.name = e.target.value;
                            setFormData({ ...formData, values: { ...formData.values, cephBlockPools: pools } });
                          }}
                          className="w-full px-3 py-2 rounded-lg bg-base border border-overlay text-text focus:border-mauve focus:outline-none"
                        />
                      </div>
                      <label className="flex items-center gap-3 cursor-pointer pt-6">
                        <input
                          type="checkbox"
                          checked={formData.values?.cephBlockPools?.[0]?.storageClass?.isDefault ?? true}
                          onChange={(e) => {
                            const pools = [...(formData.values?.cephBlockPools || [])];
                            if (!pools[0]) pools[0] = { name: 'ceph-blockpool', spec: { replicated: { size: 3 } }, storageClass: {} };
                            if (!pools[0].storageClass) pools[0].storageClass = {};
                            pools[0].storageClass.isDefault = e.target.checked;
                            setFormData({ ...formData, values: { ...formData.values, cephBlockPools: pools } });
                          }}
                          className="w-4 h-4 rounded border-overlay text-mauve focus:ring-mauve"
                        />
                        <span className="text-sm text-text">Set as Default</span>
                      </label>
                    </div>
                  </CollapsibleSection>
                )}

                {/* Ingress Settings */}
                {sections.includes('ingress') && (
                  <CollapsibleSection 
                    title="Ingress" 
                    section="ingress"
                    expanded={expandedSections.has('ingress')}
                    onToggle={() => toggleSection('ingress')}
                    badge={formData.values?.ingress?.enabled ? 'Enabled' : undefined}
                  >
                    <div className="space-y-4">
                      <label className="flex items-center gap-3 cursor-pointer">
                        <input
                          type="checkbox"
                          checked={formData.values?.ingress?.enabled || false}
                          onChange={(e) => updateFormValue('ingress.enabled', e.target.checked)}
                          className="w-4 h-4 rounded border-overlay text-mauve focus:ring-mauve"
                        />
                        <span className="text-sm text-text">Enable Ingress</span>
                      </label>
                      
                      {formData.values?.ingress?.enabled && (
                        <div className="grid grid-cols-2 gap-4 pl-7">
                          <div className="col-span-2">
                            <label className="block text-sm text-subtext mb-1">Hostname</label>
                            <input
                              type="text"
                              value={formData.values?.ingress?.host || ''}
                              onChange={(e) => updateFormValue('ingress.host', e.target.value)}
                              placeholder="grafana.example.com"
                              className="w-full px-3 py-2 rounded-lg bg-base border border-overlay text-text placeholder:text-muted focus:border-mauve focus:outline-none"
                            />
                          </div>
                          <label className="flex items-center gap-3 cursor-pointer">
                            <input
                              type="checkbox"
                              checked={formData.values?.ingress?.tls || false}
                              onChange={(e) => updateFormValue('ingress.tls', e.target.checked)}
                              className="w-4 h-4 rounded border-overlay text-mauve focus:ring-mauve"
                            />
                            <span className="text-sm text-text">Enable TLS</span>
                          </label>
                          {formData.values?.ingress?.tls && (
                            <div>
                              <label className="block text-sm text-subtext mb-1">ClusterIssuer</label>
                              <input
                                type="text"
                                value={formData.values?.ingress?.clusterIssuer || ''}
                                onChange={(e) => updateFormValue('ingress.clusterIssuer', e.target.value)}
                                placeholder="letsencrypt-production"
                                className="w-full px-3 py-2 rounded-lg bg-base border border-overlay text-text placeholder:text-muted focus:border-mauve focus:outline-none"
                              />
                            </div>
                          )}
                        </div>
                      )}
                    </div>
                  </CollapsibleSection>
                )}

                {/* Persistence Settings (for VM & Grafana) */}
                {sections.includes('persistence') && component.id !== 'rook-ceph-cluster' && (
                  <CollapsibleSection 
                    title="Persistence" 
                    section="persistence"
                    expanded={expandedSections.has('persistence')}
                    onToggle={() => toggleSection('persistence')}
                    badge={
                      component.id === 'victoria-metrics-single'
                        ? formData.values?.server?.persistentVolume?.enabled ? formData.values.server.persistentVolume.size : undefined
                        : formData.values?.persistence?.enabled ? formData.values.persistence.size : undefined
                    }
                  >
                    <div className="space-y-4">
                      <label className="flex items-center gap-3 cursor-pointer">
                        <input
                          type="checkbox"
                          checked={
                            component.id === 'victoria-metrics-single'
                              ? formData.values?.server?.persistentVolume?.enabled || false
                              : formData.values?.persistence?.enabled || false
                          }
                          onChange={(e) => {
                            if (component.id === 'victoria-metrics-single') {
                              updateFormValue('server.persistentVolume.enabled', e.target.checked);
                            } else {
                              updateFormValue('persistence.enabled', e.target.checked);
                            }
                          }}
                          className="w-4 h-4 rounded border-overlay text-mauve focus:ring-mauve"
                        />
                        <span className="text-sm text-text">Enable Persistent Storage</span>
                      </label>
                      
                      {(component.id === 'victoria-metrics-single' 
                        ? formData.values?.server?.persistentVolume?.enabled 
                        : formData.values?.persistence?.enabled) && (
                        <div className="grid grid-cols-2 gap-4 pl-7">
                          <div>
                            <label className="block text-sm text-subtext mb-1">Storage Size</label>
                            <input
                              type="text"
                              value={
                                component.id === 'victoria-metrics-single'
                                  ? formData.values?.server?.persistentVolume?.size || '50Gi'
                                  : formData.values?.persistence?.size || '10Gi'
                              }
                              onChange={(e) => {
                                if (component.id === 'victoria-metrics-single') {
                                  updateFormValue('server.persistentVolume.size', e.target.value);
                                } else {
                                  updateFormValue('persistence.size', e.target.value);
                                }
                              }}
                              placeholder="10Gi"
                              className="w-full px-3 py-2 rounded-lg bg-base border border-overlay text-text placeholder:text-muted focus:border-mauve focus:outline-none"
                            />
                          </div>
                          <div>
                            <label className="block text-sm text-subtext mb-1">Storage Class</label>
                            <input
                              type="text"
                              value={
                                component.id === 'victoria-metrics-single'
                                  ? formData.values?.server?.persistentVolume?.storageClass || ''
                                  : formData.values?.persistence?.storageClass || ''
                              }
                              onChange={(e) => {
                                if (component.id === 'victoria-metrics-single') {
                                  updateFormValue('server.persistentVolume.storageClass', e.target.value);
                                } else {
                                  updateFormValue('persistence.storageClass', e.target.value);
                                }
                              }}
                              placeholder="Leave empty for default"
                              className="w-full px-3 py-2 rounded-lg bg-base border border-overlay text-text placeholder:text-muted focus:border-mauve focus:outline-none"
                            />
                          </div>
                        </div>
                      )}
                    </div>
                  </CollapsibleSection>
                )}

                {/* Resources Settings */}
                {sections.includes('resources') && (
                  <CollapsibleSection 
                    title="Resources" 
                    section="resources"
                    expanded={expandedSections.has('resources')}
                    onToggle={() => toggleSection('resources')}
                  >
                    <div className="grid grid-cols-2 gap-4">
                      <div>
                        <h4 className="text-xs font-medium text-subtext uppercase mb-2">Requests</h4>
                        <div className="space-y-2">
                          <div>
                            <label className="block text-xs text-muted mb-1">CPU</label>
                            <input
                              type="text"
                              value={
                                component.id === 'victoria-metrics-single'
                                  ? formData.values?.server?.resources?.requests?.cpu || '250m'
                                  : formData.values?.resources?.requests?.cpu || '100m'
                              }
                              onChange={(e) => {
                                if (component.id === 'victoria-metrics-single') {
                                  updateFormValue('server.resources.requests.cpu', e.target.value);
                                } else {
                                  updateFormValue('resources.requests.cpu', e.target.value);
                                }
                              }}
                              className="w-full px-3 py-1.5 rounded-lg bg-base border border-overlay text-text text-sm focus:border-mauve focus:outline-none"
                            />
                          </div>
                          <div>
                            <label className="block text-xs text-muted mb-1">Memory</label>
                            <input
                              type="text"
                              value={
                                component.id === 'victoria-metrics-single'
                                  ? formData.values?.server?.resources?.requests?.memory || '512Mi'
                                  : formData.values?.resources?.requests?.memory || '128Mi'
                              }
                              onChange={(e) => {
                                if (component.id === 'victoria-metrics-single') {
                                  updateFormValue('server.resources.requests.memory', e.target.value);
                                } else {
                                  updateFormValue('resources.requests.memory', e.target.value);
                                }
                              }}
                              className="w-full px-3 py-1.5 rounded-lg bg-base border border-overlay text-text text-sm focus:border-mauve focus:outline-none"
                            />
                          </div>
                        </div>
                      </div>
                      <div>
                        <h4 className="text-xs font-medium text-subtext uppercase mb-2">Limits</h4>
                        <div className="space-y-2">
                          <div>
                            <label className="block text-xs text-muted mb-1">CPU</label>
                            <input
                              type="text"
                              value={
                                component.id === 'victoria-metrics-single'
                                  ? formData.values?.server?.resources?.limits?.cpu || '1'
                                  : formData.values?.resources?.limits?.cpu || '500m'
                              }
                              onChange={(e) => {
                                if (component.id === 'victoria-metrics-single') {
                                  updateFormValue('server.resources.limits.cpu', e.target.value);
                                } else {
                                  updateFormValue('resources.limits.cpu', e.target.value);
                                }
                              }}
                              className="w-full px-3 py-1.5 rounded-lg bg-base border border-overlay text-text text-sm focus:border-mauve focus:outline-none"
                            />
                          </div>
                          <div>
                            <label className="block text-xs text-muted mb-1">Memory</label>
                            <input
                              type="text"
                              value={
                                component.id === 'victoria-metrics-single'
                                  ? formData.values?.server?.resources?.limits?.memory || '2Gi'
                                  : formData.values?.resources?.limits?.memory || '512Mi'
                              }
                              onChange={(e) => {
                                if (component.id === 'victoria-metrics-single') {
                                  updateFormValue('server.resources.limits.memory', e.target.value);
                                } else {
                                  updateFormValue('resources.limits.memory', e.target.value);
                                }
                              }}
                              className="w-full px-3 py-1.5 rounded-lg bg-base border border-overlay text-text text-sm focus:border-mauve focus:outline-none"
                            />
                          </div>
                        </div>
                      </div>
                    </div>
                  </CollapsibleSection>
                )}

                {/* Raw YAML Overrides */}
                {sections.includes('raw') && (
                  <CollapsibleSection 
                    title="Raw YAML Overrides" 
                    section="raw"
                    expanded={expandedSections.has('raw')}
                    onToggle={() => toggleSection('raw')}
                    badge={formData.rawOverrides ? 'Custom' : undefined}
                    icon={<Code2 className="w-4 h-4" />}
                  >
                    <div>
                      <p className="text-xs text-muted mb-2">
                        Advanced: Paste raw YAML values to override any settings. This will be merged with the form values above.
                      </p>
                      <textarea
                        value={formData.rawOverrides}
                        onChange={(e) => setFormData({ ...formData, rawOverrides: e.target.value })}
                        placeholder={`# Example:\nreplicas: 2\nresources:\n  limits:\n    memory: 1Gi`}
                        className="w-full h-40 px-3 py-2 rounded-lg bg-base border border-overlay text-text placeholder:text-muted focus:border-mauve focus:outline-none font-mono text-sm"
                        spellCheck={false}
                      />
                    </div>
                  </CollapsibleSection>
                )}

                {/* Action buttons */}
                <div className="flex items-center gap-2 pt-4">
                  <button
                    onClick={handleAddOrUpdateInstance}
                    disabled={!isFormValid}
                    className="flex items-center gap-2 px-4 py-2 rounded-lg bg-mauve text-base font-medium hover:bg-mauve/80 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                  >
                    {editingIndex !== null ? (
                      <>
                        <Check className="w-4 h-4" />
                        Update Instance
                      </>
                    ) : (
                      <>
                        <Plus className="w-4 h-4" />
                        Add Instance
                      </>
                    )}
                  </button>
                </div>
              </div>
            ) : (
              <button
                onClick={() => { setShowAddForm(true); resetForm(); }}
                className="w-full p-4 rounded-lg border-2 border-dashed border-overlay hover:border-mauve text-subtext hover:text-mauve transition-colors flex items-center justify-center gap-2"
              >
                <Plus className="w-5 h-5" />
                Add Instance
              </button>
            )}
          </div>

          {/* Footer */}
          <div className="flex items-center justify-between p-6 border-t border-overlay bg-base/50">
            <p className="text-sm text-muted">
              {localInstances.length === 0 
                ? 'Add at least one instance to deploy this component'
                : `${localInstances.length} instance${localInstances.length !== 1 ? 's' : ''} will be deployed`
              }
            </p>
            <div className="flex items-center gap-3">
              <button
                onClick={onClose}
                className="px-4 py-2 rounded-lg text-subtext hover:text-text transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={handleSave}
                className="flex items-center gap-2 px-6 py-2 rounded-lg bg-green text-base font-medium hover:bg-green/80 transition-colors"
              >
                <Check className="w-4 h-4" />
                Save Instances
              </button>
            </div>
          </div>
        </motion.div>
      </motion.div>
    </AnimatePresence>
  );
}

// Collapsible section component
function CollapsibleSection({ 
  title, 
  section, 
  expanded, 
  onToggle, 
  children,
  required,
  badge,
  icon
}: { 
  title: string; 
  section: string;
  expanded: boolean; 
  onToggle: () => void;
  children: React.ReactNode;
  required?: boolean;
  badge?: string;
  icon?: React.ReactNode;
}) {
  return (
    <div className="rounded-lg border border-overlay overflow-hidden">
      <button
        onClick={onToggle}
        className="w-full flex items-center justify-between p-3 bg-base hover:bg-overlay/50 transition-colors"
      >
        <div className="flex items-center gap-2">
          {expanded ? <ChevronDown className="w-4 h-4 text-muted" /> : <ChevronRight className="w-4 h-4 text-muted" />}
          {icon}
          <span className="text-sm font-medium text-text">{title}</span>
          {required && <span className="text-xs text-peach">*</span>}
          {badge && <span className="text-xs px-2 py-0.5 rounded bg-mauve/20 text-mauve">{badge}</span>}
        </div>
      </button>
      {expanded && (
        <div className="p-4 border-t border-overlay bg-surface">
          {children}
        </div>
      )}
    </div>
  );
}

'use client';

import { useState, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { 
  Boxes, Shield, Globe, BarChart3, Settings, 
  ChevronRight, ChevronDown, Download, Github, Terminal,
  Sparkles, Check, X, Loader2, FileCode,
  Upload
} from 'lucide-react';
import yaml from 'js-yaml';
import { ComponentCard } from '@/components/ComponentCard';
import { ConfigModal } from '@/components/ConfigModal';
import { GenerateModal } from '@/components/GenerateModal';
import { InstanceModal } from '@/components/InstanceModal';
import { Header } from '@/components/Header';
import { Hero } from '@/components/Hero';
import { Footer } from '@/components/Footer';
import type { Category, Component, ComponentSelection, ComponentInstance, SavedConfig } from '@/types';

const categoryIcons: Record<string, React.ReactNode> = {
  system: <Settings className="w-5 h-5" />,
  security: <Shield className="w-5 h-5" />,
  ingress: <Globe className="w-5 h-5" />,
  observability: <BarChart3 className="w-5 h-5" />,
  storage: <Boxes className="w-5 h-5" />,
};

export default function Home() {
  const [categories, setCategories] = useState<Category[]>([]);
  const [selections, setSelections] = useState<Map<string, ComponentSelection>>(new Map());
  const [configuring, setConfiguring] = useState<Component | null>(null);
  const [showGenerate, setShowGenerate] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [importMessage, setImportMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null);
  const [collapsedCategories, setCollapsedCategories] = useState<Set<string>>(new Set());
  const [importedConfig, setImportedConfig] = useState<{ clusterName?: string; repoUrl?: string; branch?: string } | null>(null);
  const [managingInstances, setManagingInstances] = useState<Component | null>(null);

  useEffect(() => {
    fetchCategories();
  }, []);

  // Import configuration from file (k8s-bootstrap.yaml from generated repo)
  const importConfig = (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file) return;

    const reader = new FileReader();
    reader.onload = (e) => {
      try {
        const content = e.target?.result as string;
        let config: SavedConfig;
        
        // Try YAML first, then JSON
        try {
          config = yaml.load(content) as SavedConfig;
        } catch {
          config = JSON.parse(content);
        }

        if (!config.selections || !Array.isArray(config.selections)) {
          throw new Error('Invalid config format: missing selections');
        }

        // Apply selections
        setSelections(prev => {
          const newMap = new Map(prev);
          // First disable all
          newMap.forEach((v, k) => {
            newMap.set(k, { ...v, enabled: false, values: {}, rawOverrides: '' });
          });
          // Then enable and configure from import
          config.selections.forEach(s => {
            if (newMap.has(s.id)) {
              newMap.set(s.id, {
                id: s.id,
                enabled: true,
                values: s.values || {},
                rawOverrides: s.rawOverrides || '',
              });
            }
          });
          return newMap;
        });

        // Store imported config metadata (repo_url, cluster_name, branch)
        setImportedConfig({
          clusterName: config.cluster_name,
          repoUrl: config.repo_url,
          branch: config.branch,
        });

        setImportMessage({ 
          type: 'success', 
          text: `Imported ${config.selections.length} component(s) from "${config.cluster_name || 'config'}"` 
        });
      } catch (err) {
        setImportMessage({ 
          type: 'error', 
          text: `Import failed: ${err instanceof Error ? err.message : 'Invalid format'}` 
        });
      }
      setTimeout(() => setImportMessage(null), 5000);
    };
    reader.readAsText(file);
    // Reset input so same file can be imported again
    event.target.value = '';
  };

  const fetchCategories = async () => {
    try {
      const res = await fetch('/api/categories');
      if (!res.ok) throw new Error('Failed to fetch categories');
      const data = await res.json();
      setCategories(data);
      
      // Initialize selections with defaults (all disabled initially)
      const initial = new Map<string, ComponentSelection>();
      data.forEach((cat: Category) => {
        cat.components.forEach((comp: Component) => {
          initial.set(comp.id, {
            id: comp.id,
            enabled: false,
            values: {},
            rawOverrides: '',
          });
        });
      });
      setSelections(initial);
    } catch (err) {
      setError('Failed to load components. Is the API running?');
    } finally {
      setLoading(false);
    }
  };

  // Build a map of operator -> instances for quick lookup
  const getInstancesForOperator = (operatorId: string): string[] => {
    const instances: string[] = [];
    categories.forEach(cat => {
      cat.components.forEach(comp => {
        if (comp.isInstance && comp.instanceOf === operatorId) {
          instances.push(comp.id);
        }
      });
    });
    return instances;
  };

  const toggleComponent = (id: string) => {
    setSelections(prev => {
      const newMap = new Map(prev);
      const current = newMap.get(id);
      if (current) {
        const newEnabled = !current.enabled;
        newMap.set(id, { ...current, enabled: newEnabled });
        
        // If disabling an operator, also disable its instances
        if (!newEnabled) {
          const instances = getInstancesForOperator(id);
          instances.forEach(instanceId => {
            const instanceSelection = newMap.get(instanceId);
            if (instanceSelection?.enabled) {
              newMap.set(instanceId, { ...instanceSelection, enabled: false });
            }
          });
        }
      }
      return newMap;
    });
  };

  const updateComponentValues = (id: string, values: Record<string, any>, rawOverrides: string) => {
    setSelections(prev => {
      const newMap = new Map(prev);
      const current = newMap.get(id);
      if (current) {
        newMap.set(id, { ...current, values, rawOverrides });
      }
      return newMap;
    });
    setConfiguring(null);
  };

  const updateComponentInstances = (id: string, instances: ComponentInstance[]) => {
    setSelections(prev => {
      const newMap = new Map(prev);
      const current = newMap.get(id);
      if (current) {
        // Enable if has instances, disable if no instances
        newMap.set(id, { ...current, enabled: instances.length > 0, instances });
      }
      return newMap;
    });
    setManagingInstances(null);
  };

  const getSelectedCount = () => {
    let count = 0;
    selections.forEach(s => { 
      if (s.enabled) {
        // Count instances for multi-instance components
        if (s.instances && s.instances.length > 0) {
          count += s.instances.length;
        } else {
          count++;
        }
      }
    });
    return count;
  };

  const getSelectedComponents = () => {
    const selected: ComponentSelection[] = [];
    selections.forEach(s => { if (s.enabled) selected.push(s); });
    return selected;
  };

  // Count selected components in a category
  const getSelectedInCategory = (category: Category): number => {
    return category.components.filter(comp => 
      selections.get(comp.id)?.enabled
    ).length;
  };

  // Toggle category collapse
  const toggleCategoryCollapse = (categoryId: string) => {
    setCollapsedCategories(prev => {
      const newSet = new Set(prev);
      if (newSet.has(categoryId)) {
        newSet.delete(categoryId);
      } else {
        newSet.add(categoryId);
      }
      return newSet;
    });
  };

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="text-center">
          <Loader2 className="w-12 h-12 text-lavender animate-spin mx-auto mb-4" />
          <p className="text-subtext">Loading components...</p>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="text-center max-w-md">
          <X className="w-12 h-12 text-red mx-auto mb-4" />
          <h2 className="text-xl font-semibold mb-2">Connection Error</h2>
          <p className="text-subtext mb-4">{error}</p>
          <button 
            onClick={() => window.location.reload()}
            className="btn-primary"
          >
            Retry
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen">
      <Header />
      <Hero />
      
      {/* Main Generator Section */}
      <section id="generator" className="py-20 px-4">
        <div className="max-w-7xl mx-auto">
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true }}
            className="text-center mb-12"
          >
            <h2 className="text-3xl md:text-4xl font-bold mb-4">
              <span className="bg-gradient-to-r from-lavender via-blue to-sapphire bg-clip-text text-transparent">
                Select Your Components
              </span>
            </h2>
            <p className="text-subtext max-w-2xl mx-auto mb-6">
              Choose the components you need. Click configure to customize settings.
              We'll generate a complete GitOps repository with Flux manifests.
            </p>
            
            {/* Load previous config */}
            <div className="flex justify-center">
              <label className="btn-secondary flex items-center gap-2 cursor-pointer">
                <Upload className="w-4 h-4" />
                Load Previous Config
                <input
                  type="file"
                  accept=".yaml,.yml,.json"
                  onChange={importConfig}
                  className="hidden"
                />
              </label>
            </div>

            {/* Import message */}
            {importMessage && (
              <motion.div
                initial={{ opacity: 0, y: -10 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0 }}
                className={`mt-4 px-4 py-2 rounded-lg text-sm inline-flex items-center gap-2 ${
                  importMessage.type === 'success' 
                    ? 'bg-green/10 text-green border border-green/30' 
                    : 'bg-red/10 text-red border border-red/30'
                }`}
              >
                {importMessage.type === 'success' ? <Check className="w-4 h-4" /> : <X className="w-4 h-4" />}
                {importMessage.text}
              </motion.div>
            )}
          </motion.div>

          {/* Categories */}
          <div className="space-y-8">
            {categories.map((category, catIndex) => {
              const isCollapsed = collapsedCategories.has(category.id);
              const selectedInCategory = getSelectedInCategory(category);
              
              return (
                <motion.div
                  key={category.id}
                  initial={{ opacity: 0, y: 20 }}
                  whileInView={{ opacity: 1, y: 0 }}
                  viewport={{ once: true }}
                  transition={{ delay: catIndex * 0.1 }}
                  className="bg-surface/30 rounded-xl border border-overlay/30 overflow-hidden"
                >
                  {/* Category Header - Clickable */}
                  <button
                    onClick={() => toggleCategoryCollapse(category.id)}
                    className="w-full flex items-center justify-between gap-3 p-4 hover:bg-surface/50 transition-colors"
                  >
                    <div className="flex items-center gap-3">
                      <div className="p-2 bg-surface rounded-lg text-lavender">
                        {categoryIcons[category.id] || <Boxes className="w-5 h-5" />}
                      </div>
                      <div className="text-left">
                        <h3 className="text-xl font-semibold text-text">{category.name}</h3>
                        <p className="text-sm text-muted">{category.description}</p>
                      </div>
                    </div>
                    
                    <div className="flex items-center gap-3">
                      {/* Selected count badge */}
                      {selectedInCategory > 0 && (
                        <span className="bg-green/20 text-green border border-green/40 px-2.5 py-1 rounded-full text-sm font-medium flex items-center gap-1.5">
                          <Check className="w-3.5 h-3.5" />
                          {selectedInCategory}
                        </span>
                      )}
                      {/* Component count */}
                      <span className="text-muted text-sm">
                        {category.components.length} components
                      </span>
                      {/* Chevron */}
                      <motion.div
                        animate={{ rotate: isCollapsed ? 0 : 90 }}
                        transition={{ duration: 0.2 }}
                      >
                        <ChevronRight className="w-5 h-5 text-muted" />
                      </motion.div>
                    </div>
                  </button>

                  {/* Components Grid - Collapsible */}
                  <AnimatePresence initial={false}>
                    {!isCollapsed && (
                      <motion.div
                        initial={{ height: 0, opacity: 0 }}
                        animate={{ height: 'auto', opacity: 1 }}
                        exit={{ height: 0, opacity: 0 }}
                        transition={{ duration: 0.3, ease: 'easeInOut' }}
                        className="overflow-hidden"
                      >
                        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4 p-4 pt-4 items-stretch">
                          {(() => {
                            // Group dependent components under their required components
                            const operators = category.components.filter(c => 
                              category.components.some(inst => inst.requiresOperator === c.id)
                            );
                            // All components that require another component (multi-instance or not)
                            const dependents = category.components.filter(c => c.requiresOperator);
                            const standalone = category.components.filter(c => 
                              !operators.includes(c) && !c.requiresOperator
                            );
                            
                            let compIndex = 0;
                            const items: React.ReactNode[] = [];

                            // First, render standalone components
                            standalone.forEach(component => {
                              const selection = selections.get(component.id);
                              items.push(
                                <ComponentCard
                                  key={component.id}
                                  component={component}
                                  selected={selection?.enabled || false}
                                  onToggle={() => toggleComponent(component.id)}
                                  onConfigure={() => setConfiguring(component)}
                                  onManageInstances={() => setManagingInstances(component)}
                                  instances={selection?.instances || []}
                                  delay={compIndex++ * 0.05}
                                  isOperatorSelected={true}
                                />
                              );
                            });

                            // Then, render operators with their instances grouped below
                            operators.forEach(operator => {
                              const operatorSelection = selections.get(operator.id);
                              const isOpSelected = operatorSelection?.enabled || false;
                              
                              // Operator card
                              items.push(
                                <ComponentCard
                                  key={operator.id}
                                  component={operator}
                                  selected={isOpSelected}
                                  onToggle={() => toggleComponent(operator.id)}
                                  onConfigure={() => setConfiguring(operator)}
                                  onManageInstances={() => setManagingInstances(operator)}
                                  instances={operatorSelection?.instances || []}
                                  delay={compIndex++ * 0.05}
                                  isOperatorSelected={true}
                                />
                              );
                              
                              // Dependent cards (grouped under their required component)
                              const deps = dependents.filter(c => c.requiresOperator === operator.id);
                              deps.forEach(dep => {
                                const depSelection = selections.get(dep.id);
                                items.push(
                                  <div key={dep.id} className="relative">
                                    {/* Connector line */}
                                    <div className="absolute -left-2 top-0 bottom-0 w-0.5 bg-overlay hidden md:block" />
                                    <ComponentCard
                                      component={dep}
                                      selected={depSelection?.enabled || false}
                                      onToggle={() => toggleComponent(dep.id)}
                                      onConfigure={() => setConfiguring(dep)}
                                      onManageInstances={() => setManagingInstances(dep)}
                                      instances={depSelection?.instances || []}
                                      delay={compIndex++ * 0.05}
                                      isOperatorSelected={isOpSelected}
                                    />
                                  </div>
                                );
                              });
                            });

                            return items;
                          })()}
                        </div>
                      </motion.div>
                    )}
                  </AnimatePresence>
                </motion.div>
              );
            })}
          </div>

          {/* Generate Button */}
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            className="fixed bottom-8 left-1/2 -translate-x-1/2 z-50"
          >
            <AnimatePresence>
              {getSelectedCount() > 0 && (
                <motion.button
                  initial={{ opacity: 0, y: 20, scale: 0.9 }}
                  animate={{ opacity: 1, y: 0, scale: 1 }}
                  exit={{ opacity: 0, y: 20, scale: 0.9 }}
                  onClick={() => setShowGenerate(true)}
                  className="btn-primary flex items-center gap-3 shadow-2xl shadow-lavender/30"
                >
                  <Sparkles className="w-5 h-5" />
                  <span>Generate Bootstrap Package</span>
                  <span className="bg-white/20 px-2 py-0.5 rounded-full text-sm">
                    {getSelectedCount()} selected
                  </span>
                </motion.button>
              )}
            </AnimatePresence>
          </motion.div>
        </div>
      </section>

      {/* Features Section */}
      <section className="py-20 px-4 bg-surface/30">
        <div className="max-w-7xl mx-auto">
          <div className="grid grid-cols-1 md:grid-cols-3 gap-8">
            <FeatureCard
              icon={<FileCode className="w-8 h-8" />}
              title="GitOps Ready"
              description="Complete repository structure with Flux manifests, ready to push and sync."
            />
            <FeatureCard
              icon={<Terminal className="w-8 h-8" />}
              title="One-Click Bootstrap"
              description="Single bash script installs Flux and configures your cluster."
            />
            <FeatureCard
              icon={<Github className="w-8 h-8" />}
              title="Vendored Charts"
              description="All Helm charts are included in your repo. No external dependencies."
            />
          </div>
        </div>
      </section>

      <Footer />

      {/* Configuration Modal */}
      <AnimatePresence>
        {configuring && (
          <ConfigModal
            component={configuring}
            currentValues={selections.get(configuring.id)?.values || {}}
            currentOverrides={selections.get(configuring.id)?.rawOverrides || ''}
            onSave={(values, overrides) => updateComponentValues(configuring.id, values, overrides)}
            onClose={() => setConfiguring(null)}
          />
        )}
      </AnimatePresence>

      {/* Instance Management Modal */}
      <AnimatePresence>
        {managingInstances && (
          <InstanceModal
            isOpen={!!managingInstances}
            onClose={() => setManagingInstances(null)}
            component={managingInstances}
            instances={selections.get(managingInstances.id)?.instances || []}
            onSave={(instances) => updateComponentInstances(managingInstances.id, instances)}
          />
        )}
      </AnimatePresence>

      {/* Generate Modal */}
      <AnimatePresence>
        {showGenerate && (
          <GenerateModal
            selections={getSelectedComponents()}
            onClose={() => setShowGenerate(false)}
            importedConfig={importedConfig}
          />
        )}
      </AnimatePresence>
    </div>
  );
}

function FeatureCard({ icon, title, description }: { 
  icon: React.ReactNode; 
  title: string; 
  description: string;
}) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true }}
      className="p-6 bg-surface/50 rounded-xl border border-overlay/50 hover:border-lavender/30 transition-colors"
    >
      <div className="text-lavender mb-4">{icon}</div>
      <h3 className="text-lg font-semibold mb-2">{title}</h3>
      <p className="text-subtext text-sm">{description}</p>
    </motion.div>
  );
}

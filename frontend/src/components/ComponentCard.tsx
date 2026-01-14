'use client';

import { motion } from 'framer-motion';
import { Settings, Check, ExternalLink, Boxes, Package, Layers, Plus } from 'lucide-react';
import type { Component, ComponentInstance } from '@/types';

interface ComponentCardProps {
  component: Component;
  selected: boolean;
  onToggle: () => void;
  onConfigure: () => void;
  onManageInstances?: () => void;
  instances?: ComponentInstance[];
  delay?: number;
  isOperatorSelected?: boolean; // For instances - whether their operator is selected
}

export function ComponentCard({ 
  component, 
  selected, 
  onToggle, 
  onConfigure,
  onManageInstances,
  instances = [],
  delay = 0,
  isOperatorSelected = true 
}: ComponentCardProps) {
  // Component cannot be selected without its required operator/component
  const isDisabled = Boolean((component.isInstance || component.multiInstance || component.requiresOperator) && !isOperatorSelected);
  const isMultiInstance = component.multiInstance;
  const instanceCount = instances.length;
  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay }}
      className={`
        component-card relative p-5 rounded-xl border backdrop-blur-sm h-full flex flex-col
        ${isMultiInstance && component.requiresOperator ? 'ml-4 md:ml-6' : ''}
        ${selected 
          ? 'bg-surface/80 border-green/50 shadow-lg shadow-green/10' 
          : isDisabled
            ? 'bg-surface/20 border-overlay/30 opacity-60'
            : 'bg-surface/40 border-overlay/50 hover:border-overlay'
        }
      `}
    >
      {/* Selection indicator */}
      {selected && (
        <motion.div
          initial={{ scale: 0 }}
          animate={{ scale: 1 }}
          className="absolute -top-2 -right-2 w-6 h-6 bg-green rounded-full flex items-center justify-center shadow-lg shadow-green/30"
        >
          <Check className="w-3 h-3 text-base" />
        </motion.div>
      )}

      {/* Header */}
      <div className="flex items-start justify-between mb-3">
        <div className="flex items-center gap-3">
          <span className="text-2xl">{component.icon || '📦'}</span>
          <div>
            <div className="flex items-center gap-2">
              <h4 className="font-semibold text-text">{component.name}</h4>
              {component.docsUrl && (
                <a 
                  href={component.docsUrl} 
                  target="_blank" 
                  rel="noopener noreferrer"
                  className="text-muted hover:text-lavender transition-colors"
                  title="Documentation"
                  onClick={(e) => e.stopPropagation()}
                >
                  <ExternalLink className="w-3.5 h-3.5" />
                </a>
              )}
            </div>
            <div className="flex items-center gap-2 flex-wrap">
              {component.version && (
                <span className="text-xs text-muted">v{component.version}</span>
              )}
              {/* Operator/Instance/Multi-Instance badges */}
              {component.isOperator && (
                <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-medium bg-blue/20 text-blue border border-blue/30">
                  <Boxes className="w-2.5 h-2.5" />
                  Operator
                </span>
              )}
              {component.isInstance && (
                <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-medium bg-teal/20 text-teal border border-teal/30">
                  <Package className="w-2.5 h-2.5" />
                  Instance
                </span>
              )}
              {isMultiInstance && (
                <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-medium bg-mauve/20 text-mauve border border-mauve/30">
                  <Layers className="w-2.5 h-2.5" />
                  Multi-Instance
                </span>
              )}
            </div>
          </div>
        </div>
      </div>

      {/* Description - grows to fill space */}
      <div className="flex-grow">
        <p className="text-sm text-subtext line-clamp-2 mb-2">
          {component.description}
        </p>

        {/* Instance hint */}
        {component.isOperator && component.suggestsInstances && component.suggestsInstances.length > 0 && (
          <p className="text-xs text-muted italic">
            💡 After selecting, you can also add instances
          </p>
        )}

        {/* Instance dependency hint */}
        {component.isInstance && component.instanceOf && (
          <p className={`text-xs italic ${isDisabled ? 'text-peach' : 'text-muted'}`}>
            {isDisabled 
              ? `🔒 Select ${component.instanceOf} first` 
              : `⚡ Requires ${component.instanceOf}`
            }
          </p>
        )}

        {/* Multi-instance hint */}
        {isMultiInstance && (
          <p className={`text-xs italic min-h-[1.25rem] ${isDisabled ? 'text-peach' : 'text-muted'}`}>
            {isDisabled && component.requiresOperator
              ? `🔒 Select ${component.requiresOperator} first`
              : '🔄 Multi-instance component'
            }
          </p>
        )}

        {/* Dependency hint for non-multi-instance components with requiresOperator */}
        {!isMultiInstance && component.requiresOperator && (
          <p className={`text-xs italic min-h-[1.25rem] ${isDisabled ? 'text-peach' : 'text-muted'}`}>
            {isDisabled 
              ? `🔒 Select ${component.requiresOperator} first`
              : `✓ Requires ${component.requiresOperator}`
            }
          </p>
        )}
      </div>

      {/* Actions - always at bottom */}
      <div className="flex items-center gap-2 mt-4">
        {isMultiInstance ? (
          /* Multi-instance: show instance count and manage button */
          <>
            <button
              onClick={isDisabled ? undefined : onManageInstances}
              disabled={isDisabled}
              className={`
                flex-1 py-2 px-4 rounded-lg text-sm font-medium transition-all flex items-center justify-center gap-2
                ${isDisabled
                  ? 'bg-overlay/30 text-muted cursor-not-allowed border border-transparent opacity-50'
                  : instanceCount > 0 
                    ? 'bg-mauve/20 text-mauve border border-mauve/40 hover:bg-mauve/30' 
                    : 'bg-overlay/50 text-subtext hover:bg-overlay hover:text-text border border-transparent'
                }
              `}
            >
              {isDisabled ? (
                'Requires Operator'
              ) : instanceCount > 0 ? (
                <>
                  <Layers className="w-4 h-4" />
                  {instanceCount} Instance{instanceCount !== 1 ? 's' : ''}
                </>
              ) : (
                <>
                  <Plus className="w-4 h-4" />
                  Add Instance
                </>
              )}
            </button>
          </>
        ) : (
          /* Single instance: standard toggle */
          <button
            onClick={isDisabled ? undefined : onToggle}
            disabled={isDisabled}
            className={`
              flex-1 py-2 px-4 rounded-lg text-sm font-medium transition-all flex items-center justify-center gap-2
              ${isDisabled
                ? 'bg-overlay/30 text-muted cursor-not-allowed border border-transparent opacity-50'
                : selected 
                  ? 'bg-green/20 text-green border border-green/40 hover:bg-green/30' 
                  : 'bg-overlay/50 text-subtext hover:bg-overlay hover:text-text border border-transparent'
              }
            `}
          >
            {selected && <Check className="w-4 h-4" />}
            {isDisabled ? 'Requires Operator' : selected ? 'Selected' : 'Select'}
          </button>
        )}
        
        {component.hasConfig && !isMultiInstance && (
          <button
            onClick={onConfigure}
            className="p-2 rounded-lg bg-overlay/50 text-subtext hover:bg-overlay hover:text-text transition-all"
            title="Configure"
          >
            <Settings className="w-4 h-4" />
          </button>
        )}
      </div>
    </motion.div>
  );
}

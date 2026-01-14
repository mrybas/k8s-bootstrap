'use client';

import { useState, useEffect } from 'react';
import { motion } from 'framer-motion';
import { X, Save, Code, Loader2 } from 'lucide-react';
import type { Component, ComponentSchema } from '@/types';
import yaml from 'js-yaml';

interface ConfigModalProps {
  component: Component;
  currentValues: Record<string, any>;
  currentOverrides: string;
  onSave: (values: Record<string, any>, rawOverrides: string) => void;
  onClose: () => void;
}

export function ConfigModal({ 
  component, 
  currentValues, 
  currentOverrides,
  onSave, 
  onClose 
}: ConfigModalProps) {
  const [schema, setSchema] = useState<ComponentSchema | null>(null);
  const [values, setValues] = useState<Record<string, any>>(currentValues);
  const [rawOverrides, setRawOverrides] = useState(currentOverrides);
  const [showRaw, setShowRaw] = useState(false);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchSchema();
  }, [component.id]);

  const fetchSchema = async () => {
    try {
      const res = await fetch(`/api/components/${component.id}/schema`);
      if (res.ok) {
        const data = await res.json();
        setSchema(data);
        // Merge defaults with current values
        setValues({ ...data.defaultValues, ...currentValues });
      }
    } catch (err) {
      console.error('Failed to fetch schema:', err);
    } finally {
      setLoading(false);
    }
  };

  const updateValue = (path: string, value: any) => {
    setValues(prev => {
      const newValues = { ...prev };
      const parts = path.split('.');
      let current: any = newValues;
      
      for (let i = 0; i < parts.length - 1; i++) {
        if (!(parts[i] in current)) {
          current[parts[i]] = {};
        }
        current = current[parts[i]];
      }
      
      current[parts[parts.length - 1]] = value;
      return newValues;
    });
  };

  const getValue = (path: string): any => {
    const parts = path.split('.');
    let current: any = values;
    
    for (const part of parts) {
      if (current === undefined || current === null) return undefined;
      current = current[part];
    }
    
    return current;
  };

  const renderField = (
    name: string, 
    fieldSchema: any, 
    path: string = name,
    uiSchema: any = {}
  ): React.ReactNode => {
    const value = getValue(path);
    const fieldUi = uiSchema[name] || {};

    if (fieldSchema.type === 'object' && fieldSchema.properties) {
      const isCollapsed = fieldUi['ui:collapsed'];
      
      return (
        <div key={path} className="mb-4">
          <details open={!isCollapsed}>
            <summary className="cursor-pointer text-sm font-medium text-text mb-2 hover:text-lavender">
              {fieldSchema.title || name}
            </summary>
            <div className="ml-4 pl-4 border-l border-overlay/50 space-y-3">
              {Object.entries(fieldSchema.properties).map(([key, subSchema]: [string, any]) =>
                renderField(key, subSchema, `${path}.${key}`, fieldUi)
              )}
            </div>
          </details>
        </div>
      );
    }

    if (fieldSchema.type === 'boolean') {
      return (
        <label key={path} className="flex items-center gap-3 mb-3 cursor-pointer group">
          <input
            type="checkbox"
            checked={value ?? fieldSchema.default ?? false}
            onChange={(e) => updateValue(path, e.target.checked)}
            className="w-5 h-5"
          />
          <div>
            <span className="text-sm text-text group-hover:text-lavender transition-colors">
              {fieldSchema.title || name}
            </span>
            {fieldSchema.description && (
              <p className="text-xs text-muted">{fieldSchema.description}</p>
            )}
          </div>
        </label>
      );
    }

    if (fieldSchema.type === 'integer' || fieldSchema.type === 'number') {
      return (
        <div key={path} className="mb-3">
          <label className="block text-sm text-text mb-1">
            {fieldSchema.title || name}
          </label>
          <input
            type="number"
            value={value ?? fieldSchema.default ?? ''}
            onChange={(e) => updateValue(path, parseInt(e.target.value) || 0)}
            min={fieldSchema.minimum}
            max={fieldSchema.maximum}
            className="input-field"
          />
          {fieldSchema.description && (
            <p className="text-xs text-muted mt-1">{fieldSchema.description}</p>
          )}
        </div>
      );
    }

    if (fieldSchema.enum) {
      return (
        <div key={path} className="mb-3">
          <label className="block text-sm text-text mb-1">
            {fieldSchema.title || name}
          </label>
          <select
            value={value ?? fieldSchema.default ?? ''}
            onChange={(e) => updateValue(path, e.target.value)}
            className="input-field"
          >
            {fieldSchema.enum.map((opt: string) => (
              <option key={opt} value={opt}>{opt}</option>
            ))}
          </select>
          {fieldSchema.description && (
            <p className="text-xs text-muted mt-1">{fieldSchema.description}</p>
          )}
        </div>
      );
    }

    if (fieldSchema.type === 'array') {
      const arrayValue = (value || []) as any[];
      
      return (
        <div key={path} className="mb-3">
          <label className="block text-sm text-text mb-1">
            {fieldSchema.title || name}
          </label>
          {arrayValue.map((item, index) => (
            <div key={index} className="flex gap-2 mb-2">
              <input
                type="text"
                value={typeof item === 'object' ? item.name || '' : item}
                onChange={(e) => {
                  const newArray = [...arrayValue];
                  newArray[index] = typeof item === 'object' 
                    ? { ...item, name: e.target.value }
                    : e.target.value;
                  updateValue(path, newArray);
                }}
                className="input-field flex-1"
              />
              <button
                onClick={() => {
                  const newArray = arrayValue.filter((_, i) => i !== index);
                  updateValue(path, newArray);
                }}
                className="p-2 text-red hover:bg-red/10 rounded-lg"
              >
                <X className="w-4 h-4" />
              </button>
            </div>
          ))}
          <button
            onClick={() => updateValue(path, [...arrayValue, ''])}
            className="text-sm text-lavender hover:text-blue"
          >
            + Add item
          </button>
        </div>
      );
    }

    // Default string input
    const isPassword = fieldUi['ui:widget'] === 'password';
    
    return (
      <div key={path} className="mb-3">
        <label className="block text-sm text-text mb-1">
          {fieldSchema.title || name}
        </label>
        <input
          type={isPassword ? 'password' : 'text'}
          value={value ?? fieldSchema.default ?? ''}
          onChange={(e) => updateValue(path, e.target.value)}
          placeholder={fieldUi['ui:placeholder']}
          className="input-field"
        />
        {(fieldSchema.description || fieldUi['ui:help']) && (
          <p className="text-xs text-muted mt-1">
            {fieldSchema.description || fieldUi['ui:help']}
          </p>
        )}
      </div>
    );
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
        className="bg-base border border-overlay rounded-xl shadow-2xl w-full max-w-2xl max-h-[85vh] overflow-hidden"
      >
        {/* Header */}
        <div className="flex items-center justify-between p-4 border-b border-overlay">
          <div className="flex items-center gap-3">
            <span className="text-2xl">{component.icon || '⚙️'}</span>
            <div>
              <h3 className="font-semibold text-text">Configure {component.name}</h3>
              <p className="text-xs text-muted">Customize component settings</p>
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
        <div className="p-4 overflow-y-auto max-h-[60vh]">
          {loading ? (
            <div className="flex items-center justify-center py-12">
              <Loader2 className="w-8 h-8 text-lavender animate-spin" />
            </div>
          ) : (
            <>
              {/* Tab buttons */}
              <div className="flex gap-2 mb-4">
                <button
                  onClick={() => setShowRaw(false)}
                  className={`px-4 py-2 rounded-lg text-sm transition-colors ${
                    !showRaw 
                      ? 'bg-lavender/20 text-lavender' 
                      : 'bg-overlay/50 text-subtext hover:text-text'
                  }`}
                >
                  Form
                </button>
                <button
                  onClick={() => setShowRaw(true)}
                  className={`px-4 py-2 rounded-lg text-sm transition-colors flex items-center gap-2 ${
                    showRaw 
                      ? 'bg-lavender/20 text-lavender' 
                      : 'bg-overlay/50 text-subtext hover:text-text'
                  }`}
                >
                  <Code className="w-4 h-4" />
                  Raw YAML
                </button>
              </div>

              {!showRaw ? (
                <div className="space-y-4">
                  {schema?.jsonSchema?.properties && 
                    Object.entries(schema.jsonSchema.properties).map(([name, fieldSchema]) =>
                      renderField(name, fieldSchema, name, schema.uiSchema || {})
                    )
                  }
                </div>
              ) : (
                <div>
                  <p className="text-sm text-muted mb-2">
                    Add raw YAML overrides (merged on top of form values):
                  </p>
                  <textarea
                    value={rawOverrides}
                    onChange={(e) => setRawOverrides(e.target.value)}
                    className="input-field font-mono text-sm h-64 resize-none"
                    placeholder={`# Example:\nprometheus:\n  prometheusSpec:\n    retention: 30d`}
                  />
                </div>
              )}
            </>
          )}
        </div>

        {/* Footer */}
        <div className="flex items-center justify-end gap-3 p-4 border-t border-overlay bg-surface/30">
          <button
            onClick={onClose}
            className="btn-secondary"
          >
            Cancel
          </button>
          <button
            onClick={() => onSave(values, rawOverrides)}
            className="btn-primary flex items-center gap-2"
          >
            <Save className="w-4 h-4" />
            Save Configuration
          </button>
        </div>
      </motion.div>
    </motion.div>
  );
}

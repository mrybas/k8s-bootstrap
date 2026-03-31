'use client';

import React from 'react';
import { Bundle } from '../types';

interface SelectBundleProps {
  bundles: Bundle[];
  selectedBundle: Bundle | null;
  onSelect: (bundle: Bundle) => void;
}

export function SelectBundle({ bundles, selectedBundle, onSelect }: SelectBundleProps) {
  const showHidden = typeof window !== 'undefined' && localStorage.getItem('show_hidden_bundles') === 'true';
  const visibleBundles = bundles.filter(b => !b.hidden || showHidden);

  const handleSelect = (bundle: Bundle) => {
    onSelect(bundle);
  };

  return (
    <div className="space-y-6">
      <div className="text-center">
        <h2 className="text-2xl font-bold text-text mb-2">Choose Your Stack</h2>
        <p className="text-subtext">Select a pre-configured bundle to get started</p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4 max-w-2xl mx-auto">
        {visibleBundles.map(bundle => {
          const isSelected = selectedBundle?.id === bundle.id;
          
          return (
            <button
              key={bundle.id}
              onClick={() => handleSelect(bundle)}
              className={`
                relative p-6 rounded-xl border-2 text-left
                transition-all duration-200 group
                ${isSelected 
                  ? 'border-lavender bg-lavender/10 ring-4 ring-lavender/20' 
                  : 'border-overlay hover:border-lavender/50 hover:bg-surface/50'
                }
              `}
            >
              {/* Selection indicator */}
              {isSelected && (
                <div className="absolute top-3 right-3 w-6 h-6 bg-lavender rounded-full flex items-center justify-center">
                  <svg className="w-4 h-4 text-crust" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={3} d="M5 13l4 4L19 7" />
                  </svg>
                </div>
              )}

              {/* Icon */}
              <div className="text-4xl mb-3">{bundle.icon}</div>

              {/* Title */}
              <h3 className={`text-lg font-semibold mb-1 ${isSelected ? 'text-lavender' : 'text-text'}`}>
                {bundle.name}
              </h3>

              {/* Description */}
              <p className="text-sm text-subtext line-clamp-2">
                {bundle.description}
              </p>

              {/* Component count */}
              <div className="mt-3 flex items-center gap-2 text-xs text-subtext">
                <span className="px-2 py-1 bg-surface rounded">
                  {bundle.components.filter(c => c.required).length} required
                </span>
                <span className="px-2 py-1 bg-surface rounded">
                  {bundle.components.filter(c => !c.required).length} optional
                </span>
              </div>
            </button>
          );
        })}

        {/* Empty state or "More coming soon" */}
        {visibleBundles.length < 4 && (
          <div className="p-6 rounded-xl border-2 border-dashed border-overlay/50 flex flex-col items-center justify-center text-center opacity-50">
            <div className="text-3xl mb-2">🔜</div>
            <p className="text-sm text-subtext">More bundles coming soon</p>
          </div>
        )}
      </div>
    </div>
  );
}

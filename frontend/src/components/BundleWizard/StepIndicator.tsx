'use client';

import React from 'react';
import { Check } from 'lucide-react';
import { WIZARD_STEPS } from './types';

interface StepIndicatorProps {
  currentStep: number;
  onStepClick?: (step: number) => void;
}

export function StepIndicator({ currentStep, onStepClick }: StepIndicatorProps) {
  return (
    <div className="flex items-center justify-center mb-8">
      {WIZARD_STEPS.map((step, index) => {
        const isCompleted = index < currentStep;
        const isCurrent = index === currentStep;
        const isClickable = index < currentStep && onStepClick;

        return (
          <React.Fragment key={step.id}>
            {/* Step circle */}
            <button
              onClick={() => isClickable && onStepClick(index)}
              disabled={!isClickable}
              className={`
                flex items-center justify-center w-10 h-10 rounded-full
                transition-all duration-300 font-medium text-sm
                ${isCompleted 
                  ? 'bg-green text-crust cursor-pointer hover:bg-green/80' 
                  : isCurrent 
                    ? 'bg-lavender text-crust ring-4 ring-lavender/30' 
                    : 'bg-surface text-subtext border border-overlay'
                }
                ${isClickable ? 'cursor-pointer' : 'cursor-default'}
              `}
            >
              {isCompleted ? (
                <Check className="w-5 h-5" />
              ) : (
                <span>{step.icon}</span>
              )}
            </button>

            {/* Step label */}
            <span className={`
              ml-2 text-sm font-medium hidden sm:inline
              ${isCurrent ? 'text-lavender' : isCompleted ? 'text-green' : 'text-subtext'}
            `}>
              {step.title}
            </span>

            {/* Connector line */}
            {index < WIZARD_STEPS.length - 1 && (
              <div className={`
                w-8 sm:w-16 h-0.5 mx-2 sm:mx-4 rounded
                ${index < currentStep ? 'bg-green' : 'bg-overlay'}
              `} />
            )}
          </React.Fragment>
        );
      })}
    </div>
  );
}

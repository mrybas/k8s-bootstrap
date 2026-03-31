// Bundle Wizard Types

export interface WizardStep {
  id: string;
  title: string;
  icon: string;
}

export const WIZARD_STEPS: WizardStep[] = [
  { id: 'bundle', title: 'Bundle', icon: '📦' },
  { id: 'components', title: 'Components', icon: '🧩' },
  { id: 'configure', title: 'Configure', icon: '⚙️' },
  { id: 'review', title: 'Review', icon: '📋' },
  { id: 'deploy', title: 'Deploy', icon: '🚀' },
];

export interface BundleComponent {
  id: string;
  required?: boolean;
  default_enabled?: boolean;
  description?: string;
  exclusive_group?: string;
  depends_on_bundle?: string;
  values?: Record<string, unknown>;
  hidden?: boolean;
}

export interface BundleParameter {
  id: string;
  name: string;
  description?: string;
  type: 'string' | 'boolean' | 'select' | 'number';
  options?: Array<string | { value: string; label: string }>;
  default?: string | boolean | number;
  required?: boolean;
  applies_to?: string;
  path?: string;
  show_if?: string;
  category?: string;
}

export interface ParameterCategory {
  id: string;
  name: string;
  description?: string;
  order: number;
}

export interface BundleNote {
  title: string;
  content: string;
}

export interface Bundle {
  id: string;
  name: string;
  description: string;
  icon: string;
  category: string;
  components: BundleComponent[];
  parameters: BundleParameter[];
  parameter_categories?: ParameterCategory[];
  notes: BundleNote[];
  hidden?: boolean;
  cni_bootstrap?: {
    enabled: boolean;
    component: string;
  };
}

export interface WizardState {
  currentStep: number;
  selectedBundle: Bundle | null;
  enabledComponents: Set<string>;
  parameterValues: Record<string, string | boolean | number>;
  gitConfig: {
    provider: string;
    repoUrl: string;
    username: string;
    password: string;
    autoPush: boolean;
    enableSops: boolean;
    kubeconfigPath: string;
    useDefaultKubeconfig: boolean;
  };
}

export interface WizardContextType {
  state: WizardState;
  bundles: Bundle[];
  setSelectedBundle: (bundle: Bundle) => void;
  toggleComponent: (componentId: string) => void;
  setParameterValue: (paramId: string, value: string | boolean | number) => void;
  updateGitConfig: (config: Partial<WizardState['gitConfig']>) => void;
  nextStep: () => void;
  prevStep: () => void;
  goToStep: (step: number) => void;
  canProceed: () => boolean;
  deploy: () => Promise<void>;
}

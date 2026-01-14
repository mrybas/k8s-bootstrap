export interface Component {
  id: string;
  name: string;
  description: string;
  icon?: string;
  version?: string;
  hasConfig: boolean;
  docsUrl?: string;
  // Operator pattern
  isOperator?: boolean;
  operatorFor?: string;
  suggestsInstances?: string[];
  suggestsComponents?: string[];
  // Instance pattern
  isInstance?: boolean;
  instanceOf?: string;
  // Multi-instance pattern (can deploy multiple times in different namespaces)
  multiInstance?: boolean;
  defaultNamespace?: string;
  requiresOperator?: string;
}

export interface Category {
  id: string;
  name: string;
  description: string;
  components: Component[];
}

// Instance for multi-instance components
export interface ComponentInstance {
  name: string;
  namespace: string;
  values: Record<string, any>;
  rawOverrides: string;  // Raw YAML overrides
}

export interface ComponentSelection {
  id: string;
  enabled: boolean;
  values: Record<string, any>;
  rawOverrides: string;
  // For multi-instance components
  instances?: ComponentInstance[];
}

export interface ComponentSchema {
  jsonSchema: Record<string, any>;
  uiSchema: Record<string, any>;
  defaultValues: Record<string, any>;
}

export type GitPlatform = 'github' | 'gitlab' | 'gitea';

export interface GitAuthConfig {
  enabled: boolean;
  platform: GitPlatform;
  customUrl?: string;  // For self-hosted GitLab/Gitea
}

export interface GenerateRequest {
  clusterName: string;
  repoUrl: string;
  branch: string;
  components: ComponentSelection[];
  gitAuth?: GitAuthConfig;
}

export interface TreeNode {
  name: string;
  type: 'file' | 'directory';
  children?: TreeNode[];
}

export interface DependencyResolution {
  requested: string[];
  auto_included: string[];
  crds: string[];
  always_included: string[];
  total: string[];
}

export interface SavedConfig {
  version: string;
  created_at: string;
  cluster_name?: string;
  repo_url?: string;
  branch?: string;
  selections: ComponentSelection[];
  gitAuth?: GitAuthConfig;
}

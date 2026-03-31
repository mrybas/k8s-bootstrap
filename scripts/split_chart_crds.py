#!/usr/bin/env python3
"""
Split CRDs from Helm chart templates into crds/ directory.
This ensures CRDs are installed before other resources.
"""
import os
import re
from pathlib import Path

def split_yaml_documents(content: str) -> list:
    """Split YAML content by document separators."""
    docs = []
    current = []
    for line in content.split('\n'):
        if line.strip() == '---':
            if current:
                docs.append('\n'.join(current))
            current = ['---']
        else:
            current.append(line)
    if current:
        docs.append('\n'.join(current))
    return docs

def is_crd(doc: str) -> bool:
    """Check if a YAML document is a CRD."""
    return 'kind: CustomResourceDefinition' in doc

def process_chart(chart_path: Path):
    """Process a chart directory, moving CRDs to crds/."""
    templates_path = chart_path / 'templates'
    crds_path = chart_path / 'crds'
    
    if not templates_path.exists():
        return
    
    # Find operator.yaml (contains CRDs)
    operator_file = templates_path / 'operator.yaml'
    if not operator_file.exists():
        return
    
    print(f"Processing {chart_path.name}...")
    
    content = operator_file.read_text()
    docs = split_yaml_documents(content)
    
    crd_docs = []
    other_docs = []
    
    for doc in docs:
        if is_crd(doc):
            crd_docs.append(doc)
        else:
            other_docs.append(doc)
    
    if not crd_docs:
        print(f"  No CRDs found in {operator_file}")
        return
    
    # Create crds directory
    crds_path.mkdir(exist_ok=True)
    
    # Write CRDs to crds/
    crd_content = '\n'.join(crd_docs)
    crd_file = crds_path / 'crds.yaml'
    crd_file.write_text(crd_content)
    print(f"  Wrote {len(crd_docs)} CRD(s) to {crd_file}")
    
    # Write remaining resources back to operator.yaml
    other_content = '\n'.join(other_docs)
    operator_file.write_text(other_content)
    print(f"  Updated {operator_file} with {len(other_docs)} documents")

def main():
    charts_dir = Path(__file__).parent.parent / 'backend' / 'definitions' / 'charts'
    
    for chart_dir in charts_dir.iterdir():
        if chart_dir.is_dir():
            process_chart(chart_dir)

if __name__ == '__main__':
    main()

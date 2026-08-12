#!/usr/bin/env python3
"""
Re-vendor bundled manifest charts from upstream releases.

`update-chart-versions.py` only bumps `upstream.version` for components that
consume a real Helm repository. Components with `chartType: manifest|custom`
carry a *vendored copy* of the upstream YAML under
`backend/definitions/charts/<id>/`, so bumping the version field in the
component definition alone changes nothing that actually gets deployed.

This script refreshes those vendored copies:

  kubevirt-crds + kubevirt-operator   <- kubevirt release  (operator manifest,
                                         CRDs split out into the -crds chart)
  cdi-crds      + kubevirt-cdi        <- CDI release       (same split)
  gateway-api-crd                     <- gateway-api standard-install
  cert-manager-crds                   <- cert-manager release CRDs
  multus-cni                          <- image tag in the bundled daemonset

Namespace rewriting: upstream ships in `kubevirt` / `cdi`; the stack deploys
into `o0-kubevirt` / `o0-cdi` (the namespaces chart owns those). The upstream
`Namespace` object is dropped so Helm does not fight the namespaces release
over ownership, and every `namespace:` reference is rewritten.

Usage:
    python3 scripts/revendor-manifest-charts.py --check
    python3 scripts/revendor-manifest-charts.py --update
"""
import argparse
import re
import sys
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
CHARTS = REPO / "backend" / "definitions" / "charts"
COMPONENTS = REPO / "backend" / "definitions" / "components"

# Versions to vendor. Keep in sync with the component definitions.
TARGETS = {
    "kubevirt": "v1.9.0",
    "cdi": "v1.66.0",
    "gateway-api": "v1.6.1",
    "cert-manager": "v1.21.1",
    "multus": "v4.3.0",
}


def fetch(url: str) -> str:
    print(f"  fetching {url}")
    with urllib.request.urlopen(url, timeout=60) as r:
        return r.read().decode()


def split_docs(text: str):
    """Split a multi-document YAML stream, keeping raw text per document."""
    docs, cur = [], []
    for line in text.splitlines():
        if line.strip() == "---":
            if any(l.strip() for l in cur):
                docs.append("\n".join(cur).strip("\n"))
            cur = []
            continue
        cur.append(line)
    if any(l.strip() for l in cur):
        docs.append("\n".join(cur).strip("\n"))
    return docs


def doc_kind(doc: str) -> str:
    m = re.search(r"^kind:\s*(\S+)", doc, re.M)
    return m.group(1) if m else ""


def write(path: Path, content: str, update: bool) -> bool:
    old = path.read_text() if path.exists() else ""
    if old == content:
        print(f"  = {path.relative_to(REPO)} (unchanged)")
        return False
    if update:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
        print(f"  ✅ {path.relative_to(REPO)}")
    else:
        print(f"  ⬆️  {path.relative_to(REPO)} (would rewrite, {len(old)} -> {len(content)} bytes)")
    return True


def bump_chart_yaml(chart: str, version: str, update: bool):
    """Set version/appVersion (and any embedded release URL) in Chart.yaml."""
    path = CHARTS / chart / "Chart.yaml"
    text = path.read_text()
    bare = version.lstrip("v")
    text = re.sub(r"^version:.*$", f"version: {bare}", text, flags=re.M)
    text = re.sub(r"^appVersion:.*$", f'appVersion: "{version}"', text, flags=re.M)
    text = re.sub(r"/releases/tag/v[\d.]+", f"/releases/tag/{version}", text)
    write(path, text, update)


def vendor_operator(project: str, version: str, urls: dict, ns_from: str, ns_to: str,
                    operator_chart: str, crds_chart: str, update: bool) -> bool:
    """Split an upstream operator manifest into a CRDs chart + operator chart."""
    print(f"\n== {project} {version}")
    raw = fetch(urls["operator"])

    crds, rest = [], []
    for doc in split_docs(raw):
        kind = doc_kind(doc)
        if kind == "CustomResourceDefinition":
            crds.append(doc)
        elif kind == "Namespace":
            # Owned by the namespaces chart — dropping it avoids Helm
            # ownership conflicts and the stray empty `kubevirt`/`cdi` ns.
            continue
        else:
            rest.append(doc)

    if not crds:
        print(f"  ERROR: no CRDs found in {urls['operator']}", file=sys.stderr)
        return False

    ns_re = re.compile(rf"^(\s*namespace:\s*){ns_from}\s*$", re.M)
    operator_yaml = "---\n" + "\n---\n".join(rest) + "\n"
    operator_yaml = ns_re.sub(rf"\g<1>{ns_to}", operator_yaml)
    crds_yaml = "---\n" + "\n---\n".join(crds) + "\n"

    changed = write(CHARTS / crds_chart / "templates" / "crds.yaml", crds_yaml, update)
    changed |= write(CHARTS / operator_chart / "templates" / "operator.yaml", operator_yaml, update)
    bump_chart_yaml(crds_chart, version, update)
    bump_chart_yaml(operator_chart, version, update)
    print(f"  {len(crds)} CRD(s), {len(rest)} other object(s), ns {ns_from} -> {ns_to}")
    return changed


def vendor_gateway_api(version: str, update: bool):
    print(f"\n== gateway-api {version}")
    raw = fetch(
        f"https://github.com/kubernetes-sigs/gateway-api/releases/download/{version}/standard-install.yaml"
    )
    crd_dir = CHARTS / "gateway-api-crd" / "crds"
    written = set()
    for doc in split_docs(raw):
        if doc_kind(doc) != "CustomResourceDefinition":
            continue
        name = re.search(r"^\s*name:\s*(\S+)", doc, re.M).group(1)
        path = crd_dir / f"{name}.yaml"
        write(path, doc + "\n", update)
        written.add(path.name)
    if update:
        for stale in crd_dir.glob("*.yaml"):
            if stale.name not in written:
                print(f"  🗑  removing stale {stale.name}")
                stale.unlink()
    bump_chart_yaml("gateway-api-crd", version, update)


def vendor_cert_manager_crds(version: str, update: bool):
    print(f"\n== cert-manager CRDs {version}")
    raw = fetch(
        f"https://github.com/cert-manager/cert-manager/releases/download/{version}/cert-manager.crds.yaml"
    )
    write(CHARTS / "cert-manager-crds" / "crds" / "cert-manager.crds.yaml", raw, update)
    bump_chart_yaml("cert-manager-crds", version, update)


def vendor_multus(version: str, update: bool):
    print(f"\n== multus {version}")
    path = CHARTS / "multus-cni" / "templates" / "daemonset.yaml"
    text = path.read_text()
    text = re.sub(r'default "v[\d.]+-thick"', f'default "{version}-thick"', text)
    write(path, text, update)
    bump_chart_yaml("multus-cni", version, update)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--update", action="store_true", help="write changes (default: dry run)")
    ap.add_argument("--check", action="store_true", help="dry run (default)")
    args = ap.parse_args()
    update = args.update

    kv = TARGETS["kubevirt"]
    vendor_operator(
        "kubevirt", kv,
        {"operator": f"https://github.com/kubevirt/kubevirt/releases/download/{kv}/kubevirt-operator.yaml"},
        "kubevirt", "o0-kubevirt", "kubevirt-operator", "kubevirt-crds", update,
    )

    cdi = TARGETS["cdi"]
    vendor_operator(
        "cdi", cdi,
        {"operator": f"https://github.com/kubevirt/containerized-data-importer/releases/download/{cdi}/cdi-operator.yaml"},
        "cdi", "o0-cdi", "kubevirt-cdi", "cdi-crds", update,
    )

    vendor_gateway_api(TARGETS["gateway-api"], update)
    vendor_cert_manager_crds(TARGETS["cert-manager"], update)
    vendor_multus(TARGETS["multus"], update)

    print("\nDone." if update else "\nDry run — re-run with --update to write.")


if __name__ == "__main__":
    main()

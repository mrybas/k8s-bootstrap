# Multi-Tenancy Architecture Guide

Comprehensive documentation of multi-tenancy approaches tested, implemented, and planned
for the k8s-bootstrap + kubevirt_ui platform.

Last updated: 2026-03-12

## Table of Contents

1. [Architecture Overview](#1-architecture-overview)
2. [Current Implementation (Dual-NIC TCP + VPC)](#2-current-implementation)
3. [VPC Networking with kube-ovn](#3-vpc-networking-with-kube-ovn)
4. [VLAN Infrastructure (ProviderNetwork)](#4-vlan-infrastructure)
5. [OVN NAT (EIP + SNAT)](#5-ovn-nat-eip--snat)
6. [VpcDns (DNS for VPC pods)](#6-vpcdns)
7. [ACL Rules](#7-acl-rules)
8. [Kamaji TenantControlPlane (TCP)](#8-kamaji-tenantcontrolplane)
9. [Worker VM Provisioning](#9-worker-vm-provisioning)
10. [Flux Addon Deployment to Tenant Clusters](#10-flux-addon-deployment)
11. [Alternative Approaches Explored](#11-alternative-approaches-explored)
12. [Bugs Found and Fixed](#12-bugs-found-and-fixed)
13. [Known Limitations](#13-known-limitations)
14. [Future Directions](#14-future-directions)
15. [YAML Reference](#15-yaml-reference)

---

## 1. Architecture Overview

### What we build

A multi-tenant Kubernetes platform where each tenant gets:
- An isolated **virtual Kubernetes cluster** (Kamaji TenantControlPlane)
- **KubeVirt VMs** as worker nodes
- **VPC network isolation** (kube-ovn custom VPC)
- **Automated addon deployment** via Flux CD (Calico CNI, namespaces, etc.)
- **Self-service UI** (kubevirt_ui) for creating/managing tenants

### Component Stack

| Component | Role | Version |
|-----------|------|---------|
| kube-ovn | Primary CNI, VPC isolation, OVN/OVS | v1.15.3 |
| Cilium | Network policies, Hubble observability | v1.19.0 |
| Multus | Secondary network interfaces (dual-NIC) | - |
| Kamaji | Virtual control planes (TCP pods) | - |
| CAPI | Cluster API for declarative cluster management | v1.9.4 |
| CAPK | KubeVirt infrastructure provider for CAPI | v0.11.2 |
| KubeVirt | VM orchestration on Kubernetes | - |
| Flux CD | GitOps addon deployment to tenant clusters | v2 |
| MetalLB | Load balancer (Ingress VIP) | - |
| ingress-nginx | Ingress controller (ssl-passthrough for TCP) | - |
| LINSTOR | Storage (DRBD replication) | - |

### Network Topology

```
Physical Network: 192.168.196.0/24 (management)
VLAN 111:         192.168.203.0/24 (data/NAT, via MikroTik gateway .254)

Management Cluster:
├── ovn-default:  10.16.0.0/16  (default overlay, all system pods)
├── join:         100.64.0.0/16 (node-to-node)
├── Service CIDR: 10.96.0.0/12
└── VPC per tenant:
    └── vpc-{name}-default: 10.{200+n}.0.0/24 (isolated overlay)

VLAN 111 Infrastructure (underlay):
└── nat-gateway-vlan-111: 192.168.203.0/24 (OVN external subnet)
    └── OvnEip per tenant → SNAT to MikroTik → internet
```

---

## 2. Current Implementation

### Tenant Creation Flow (kubevirt_ui API)

File: `kubevirt_ui/backend/app/api/v1/tenants.py`

When `POST /api/v1/tenants` is called with `network_isolation: true`:

```
1. Create namespace: tenant-{name}
   - Labels: kubevirt-ui.io/tenant, pod-security: privileged

2. Create VPC resources:
   a. Vpc: vpc-{name}
      - enableExternal: true
      - extraExternalSubnets: [nat-gateway-vlan-111]
      - staticRoutes: 0.0.0.0/0 → 192.168.203.254
   b. Subnet: vpc-{name}-default
      - CIDR from pool (10.200-254.0.0/24)
      - ACL rules for isolation
      - excludeIps includes TCP fixed IP
   c. NetworkAttachmentDefinition (NAD) in tenant namespace
   d. NetworkPolicy: allow from own ns + infra namespaces

3. Create OVN NAT:
   a. OvnEip: eip-{name} (type: nat, from nat-gateway-vlan-111)
   b. OvnSnatRule: snat-{name} (VPC subnet → EIP)

4. Create VpcDns:
   - Prerequisites (shared): SA, RBAC, Corefile ConfigMap, NAD, vpc-dns-config
   - VpcDns CR per tenant

5. Create CAPI resources:
   a. Cluster CR
   b. KamajiControlPlane (TCP pod with dual-NIC)
   c. KubevirtCluster (managed-by: kamaji)
   d. Ingress (ssl-passthrough for TCP API server)
   e. MachineDeployment + KubevirtMachineTemplate + KubeadmConfigTemplate

6. Create Flux HelmReleases (from addon catalog):
   - Calico CNI (deployed into tenant cluster)
   - Namespaces
   - Any selected addons
```

### TCP Pod Architecture (Dual-NIC)

```
TCP Pod (KamajiControlPlane):
├── eth0: ovn-default (management network)
│   └── ClusterIP Service → accessible from management cluster
└── net1: vpc-{name}-default (VPC, via Multus NAD)
    └── Fixed IP (gateway + 1, e.g., 10.202.0.2)
    └── Workers connect to this IP

Annotations:
  k8s.v1.cni.cncf.io/networks: [{"name": "vpc-{name}-nad", "namespace": "tenant-{name}"}]
  {provider}.kubernetes.io/ip_address: {fixed_ip}

Constraints:
  - Single replica only (fixed IP can't be shared)
  - Recreate strategy (RollingUpdate deadlocks on pinned IP)
  - --advertise-address={fixed_ip} (so kubelet configs use VPC IP)
```

### Worker VM Architecture

```
Worker VM (KubeVirt VirtualMachine):
├── Pod annotation: ovn.kubernetes.io/logical_switch: vpc-{name}-default
│   └── Places the virt-launcher pod in VPC subnet
├── VM network: masquerade mode (KubeVirt internal DHCP)
│   └── VM gets internal IP, NATed through pod IP
├── DNS: dnsPolicy: None, nameservers: [VPCDNS_VIP]
│   └── Or 8.8.8.8 through OVN SNAT
└── Disks:
    ├── root: containerDisk (pre-baked Ubuntu with k8s packages)
    └── data: emptyDisk (for /var/lib — containerd, kubelet state)
```

---

## 3. VPC Networking with kube-ovn

### How VPC Works

kube-ovn creates isolated OVN logical routers per VPC. Each VPC has:
- Its own logical router (LR)
- Own logical switches (LS) for each subnet
- Own load balancers (TCP/UDP/SCTP)
- Completely isolated from other VPCs and the default VPC

### VPC Spec

```yaml
apiVersion: kubeovn.io/v1
kind: Vpc
metadata:
  name: vpc-{tenant}
spec:
  enableExternal: true                         # Required for external connectivity
  extraExternalSubnets:
    - nat-gateway-vlan-111                     # Auto-creates LRP to external subnet
  staticRoutes:
    - cidr: 0.0.0.0/0
      nextHopIP: 192.168.203.254              # MikroTik gateway on VLAN 111
      policy: policyDst
```

### VPC Subnet Spec

```yaml
apiVersion: kubeovn.io/v1
kind: Subnet
metadata:
  name: vpc-{tenant}-default
spec:
  protocol: IPv4
  cidrBlock: 10.202.0.0/24                    # Unique per tenant
  gateway: 10.202.0.1
  vpc: vpc-{tenant}
  provider: vpc-{tenant}-nad.tenant-{tenant}.ovn   # Matches NAD
  enableDHCP: true
  natOutgoing: false                           # We use OVN NAT instead
  acls: [...]                                  # See ACL section
```

### NetworkAttachmentDefinition (NAD)

Created in tenant namespace for Multus dual-NIC:

```yaml
apiVersion: k8s.cni.cncf.io/v1
kind: NetworkAttachmentDefinition
metadata:
  name: vpc-{tenant}-nad
  namespace: tenant-{tenant}
spec:
  config: |
    {
      "cniVersion": "0.3.0",
      "type": "kube-ovn",
      "server_socket": "/run/openvswitch/kube-ovn-daemon.sock",
      "provider": "vpc-{tenant}-nad.tenant-{tenant}.ovn"
    }
```

---

## 4. VLAN Infrastructure

### Why VLAN is Needed

OVN custom VPCs are overlay-only. For VPC pods/VMs to reach the internet, traffic must
exit through a physical network. kube-ovn uses a VLAN-backed "external subnet" for this.

### Components

#### ProviderNetwork

```yaml
apiVersion: kubeovn.io/v1
kind: ProviderNetwork
metadata:
  name: netprov                               # ≤12 chars
spec:
  defaultInterface: eth0.111                  # VLAN sub-interface
  autoCreateVlanSubinterfaces: true           # kube-ovn creates eth0.111
```

**CRITICAL WARNINGS:**
- **NEVER use bare `eth0`** as defaultInterface! kube-ovn will bridge the management
  NIC into OVS → all nodes lose connectivity → cluster DEAD
- `autoCreateVlanSubinterfaces: true` creates eth0.111 automatically on all nodes
- For production with bonding: use `bond0.111`

#### Vlan

```yaml
apiVersion: kubeovn.io/v1
kind: Vlan
metadata:
  name: vlan111
spec:
  id: 0                                       # NOT 111!
  provider: netprov
```

**Why `id: 0`?** The interface `eth0.111` already tags traffic with VLAN 111 at kernel
level. Setting `id: 111` would cause double-tagging (Q-in-Q), breaking connectivity.

#### Infrastructure Subnet

```yaml
apiVersion: kubeovn.io/v1
kind: Subnet
metadata:
  name: nat-gateway-vlan-111
  labels:
    kubevirt-ui.io/purpose: infrastructure    # REQUIRED for tenant API to find it!
spec:
  protocol: IPv4
  cidrBlock: 192.168.203.0/24
  gateway: 192.168.203.254                    # MikroTik router
  vlan: vlan111
  provider: ovn
  excludeIps:
    - 192.168.203.1..192.168.203.10
    - 192.168.203.250..192.168.203.254
```

**Important:** The label `kubevirt-ui.io/purpose=infrastructure` is required!
Without it, `_find_infra_subnet()` in tenants.py returns None → no OvnEip/OvnSnatRule
created → VMs have no internet access. This label must be added after bootstrap.

#### Node Labels

Worker nodes that have the VLAN sub-interface must be labeled:

```bash
kubectl label nodes talos-w-1 talos-w-2 ovn.kubernetes.io/external-gw=true --overwrite
```

---

## 5. OVN NAT (EIP + SNAT)

### CRD Approach (Section 1.4 of kube-ovn docs)

Documentation: https://kubeovn.github.io/docs/stable/en/vpc/ovn-eip-fip-snat/ (section 1.4)

The CRD approach uses `extraExternalSubnets` on the VPC spec. This is **independent** of
the default VPC EIP/SNAT function and does NOT require startup parameters like
`--external-gateway-switch` or `--external-gateway-vlanid`.

**What happens automatically:**
- `extraExternalSubnets` creates a Logical Router Port (LRP) connecting the VPC router
  to the external subnet
- An OvnEip (type=lrp) is auto-created for this port

**What must be created manually:**
- OvnEip (type=nat) — allocates an IP from the external subnet for SNAT
- OvnSnatRule — maps VPC subnet traffic to the EIP

**Auto SNAT does NOT happen with CRD approach!** It only works with the "default external
network" approach that requires startup parameters.

### OvnEip

```yaml
apiVersion: kubeovn.io/v1
kind: OvnEip
metadata:
  name: eip-{tenant}
spec:
  externalSubnet: nat-gateway-vlan-111
  type: nat                                   # "nat" for SNAT, "lrp" is auto-created
```

### OvnSnatRule

```yaml
apiVersion: kubeovn.io/v1
kind: OvnSnatRule
metadata:
  name: snat-{tenant}
spec:
  ovnEip: eip-{tenant}
  vpcSubnet: vpc-{tenant}-default
```

### LSP Options (CRITICAL — kube-ovn bug/missing feature)

kube-ovn does NOT auto-set required LSP options on custom VPC external ports.
Without these, GARP (Gratuitous ARP) is not sent for SNAT EIPs, and return traffic is lost.

**Must set BOTH options via ovn-nbctl after VPC creation:**

```bash
ovn-nbctl lsp-set-options <lsp-name> nat-addresses=router router-port=<lrp-name>
```

- LSP name format: `nat-gateway-vlan-111-{vpc-name}`
- LRP name format: `{vpc-name}-nat-gateway-vlan-111`
- Without `nat-addresses=router`: GARP not sent → return traffic lost
- Without `router-port`: GARP still doesn't work even with nat-addresses
- No CRD/annotation alternative found (kube-ovn only auto-sets for default VPC)
- Must be done for EVERY new VPC

### Shared EIP (IP Conservation)

One OvnEip (type=nat) can serve SNAT for multiple VPCs. Tested 2026-03-12.

```
OvnEip (192.168.203.12)
├── OvnSnatRule (vpc-tenant-a → 192.168.203.12)  ← READY
└── OvnSnatRule (vpc-tenant-b → 192.168.203.12)  ← READY
```

- OVN creates separate NAT rules on each VPC router with the same external IP
- Caveat: kube-ovn overwrites EIP labels to last VPC (cosmetic, not functional)
- Saves IPs: 1 shared SNAT IP + 1 LRP IP per VPC (instead of 2 IPs per VPC)

### Required Helm Values (kube-ovn)

```yaml
# In kube-ovn component definition:
networking:
  ENABLE_NAT_GW: true    # Sets --enable-eip-snat=true on controller
```

---

## 6. VpcDns

Documentation: https://kubeovn.github.io/docs/stable/en/vpc/vpc-internal-dns/

VpcDns provides DNS resolution for pods/VMs in custom VPCs. Since VPC is isolated from
the default network, the standard kube-dns (ClusterIP 10.96.0.10) is unreachable.

### VIP Selection

**VIP MUST be from Service CIDR** (e.g., 10.111.255.200), NOT from VPC subnet.

Why:
- VPC subnet VIP → ARP failure (same subnet, no ARP responder in OVN)
- Service CIDR VIP → OVN SwitchLB intercepts traffic before routing

**Placeholder Service approach DOES NOT WORK** with `kubeProxyReplacement=false`:
kube-proxy creates nftables rules for every Service, intercepts ClusterIP BEFORE
OVN SwitchLB, and REJECTs (no endpoints because Service has no selector).

Use a VIP from the END of Service CIDR range to avoid auto-assignment:
- Service CIDR: 10.96.0.0/12 → VIP: 10.111.255.200

### Talos-specific Fixes

- Corefile: `forward . 10.96.0.10` (NOT `forward . /etc/resolv.conf`)
  - Talos resolv.conf has 169.254.116.108 link-local, unreachable from VPC
- CoreDNS 1.13.1: requires proper block syntax in Corefile (not inline `{ }`)

### Prerequisites (Shared, namespace: o0-kube-ovn)

All prerequisites go in `o0-kube-ovn` namespace (NOT kube-system — kube-ovn is namespaced):

1. ServiceAccount `vpc-dns`
2. ClusterRole `system:vpc-dns` (endpoints, services, pods, namespaces — list, watch)
3. ClusterRoleBinding `vpc-dns`
4. ConfigMap `vpc-dns-corefile` (with Talos-compatible Corefile)
5. NetworkAttachmentDefinition `ovn-nad` in `default` namespace
6. ConfigMap `vpc-dns-config`:
   ```yaml
   data:
     enable-vpc-dns: "true"
     coredns-vip: "10.111.255.200"
     nad-name: ovn-nad
     nad-provider: ovn-nad.default.ovn
   ```

### VpcDns CR

```yaml
apiVersion: kubeovn.io/v1
kind: VpcDns
metadata:
  name: {tenant}-dns
spec:
  vpc: vpc-{tenant}
  subnet: vpc-{tenant}-default
  replicas: 2
```

### ACL Interaction

ACL rule `drop 10.0.0.0/8` blocks VpcDns VIP (10.111.255.200)!
Need explicit allow rule at higher priority:

```yaml
- action: allow-related
  direction: from-lport
  match: "ip4.src == {cidr} && ip4.dst == 10.111.255.200"
  priority: 2500    # Higher than the drop rule (1999)
```

---

## 7. ACL Rules

VPC subnet ACL rules provide network isolation within the VPC:

```yaml
acls:
  # 1. Allow intra-VPC traffic
  - action: allow-related
    direction: from-lport
    match: "ip4.src == {cidr} && ip4.dst == {cidr}"
    priority: 3000

  # 2. Allow VpcDns VIP access
  - action: allow-related
    direction: from-lport
    match: "ip4.src == {cidr} && ip4.dst == 10.111.255.200"
    priority: 2500

  # 3. Block management network (node IPs, MetalLB VIP)
  - action: drop
    direction: from-lport
    match: "ip4.src == {cidr} && ip4.dst == 192.168.196.0/24"
    priority: 2000

  # 4. Block all RFC1918 (prevents cross-VPC, cross-subnet access)
  - action: drop
    direction: from-lport
    match: "ip4.src == {cidr} && ip4.dst == 10.0.0.0/8"
    priority: 1999

  - action: drop
    direction: from-lport
    match: "ip4.src == {cidr} && ip4.dst == 172.16.0.0/12"
    priority: 1998

  # 5. Block VLAN 111 subnet (prevent direct access to infra)
  - action: drop
    direction: from-lport
    match: "ip4.src == {cidr} && ip4.dst == 192.168.203.0/24"
    priority: 1997

  # 6. Allow everything else (internet via SNAT)
  - action: allow-related
    direction: from-lport
    match: "ip4.src == {cidr}"
    priority: 1000
```

**Note:** ACLs are processed BEFORE SwitchLB in the OVN pipeline.

---

## 8. Kamaji TenantControlPlane

### TCP Exposure Options

| Method | IPs per tenant | HA | We use |
|--------|:-:|:-:|:-:|
| LoadBalancer (default) | 1 | Yes | No |
| Gateway API (TLSRoute) | 0 (shared) | Yes | No (planned) |
| Ingress addon (enterprise) | 0 (shared) | Yes | No (HAProxy only) |
| nginx Ingress + ssl-passthrough | 0 (shared) | Yes | **Yes** |

### Current: nginx Ingress with ssl-passthrough

```yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: {name}-cp
  namespace: tenant-{name}
  annotations:
    nginx.ingress.kubernetes.io/ssl-passthrough: "true"
    nginx.ingress.kubernetes.io/backend-protocol: "HTTPS"
spec:
  ingressClassName: nginx
  rules:
    - host: {name}.192.168.196.199.nip.io
      http:
        paths:
          - path: /
            pathType: Prefix
            backend:
              service:
                name: {name}              # Kamaji auto-creates this ClusterIP Service
                port:
                  number: 443
```

### certSANs

The TCP TLS certificate must include:
- Ingress hostname: `{name}.192.168.196.199.nip.io`
- VPC fixed IP: `10.202.0.2` (if dual-NIC enabled)
- Service DNS name: `{name}.tenant-{name}.svc` (auto-added by Kamaji)
- ClusterIP is NOT in certSANs (caused TLS mismatch bug — see Bugs section)

### Future: Gateway API

Kamaji natively supports Gateway API. Config: `tcp.spec.controlPlane.gateway`

Benefits:
- Kamaji auto-creates TLSRoute per TCP
- SNI routing on port 6443 (not 443)
- Single Gateway resource shared across all tenants
- No manual Ingress creation needed

Requirements:
- Gateway controller (Envoy Gateway or similar)
- Not compatible with nginx ingress (needs TLSRoute support)

---

## 9. Worker VM Provisioning

### KubevirtMachineTemplate

Worker VMs are placed in the VPC via pod annotation:

```yaml
spec:
  template:
    spec:
      virtualMachineTemplate:
        spec:
          template:
            metadata:
              annotations:
                ovn.kubernetes.io/logical_switch: vpc-{name}-default
            spec:
              dnsPolicy: None
              dnsConfig:
                nameservers: ["10.96.0.200"]    # VpcDns VIP
              domain:
                cpu:
                  cores: 2
                memory:
                  guest: "4Gi"                  # Minimum 4Gi recommended!
                devices:
                  interfaces:
                    - name: default
                      masquerade: {}            # KubeVirt internal DHCP + NAT
                  disks:
                    - name: root
                      disk: { bus: virtio }
                    - name: data
                      disk: { bus: virtio }
              networks:
                - name: default
                  pod: {}
              volumes:
                - name: root
                  containerDisk:
                    image: git.nas.ssh.org.ua/dev/ubuntu-container-disk:v1.30.2
                - name: data
                  emptyDisk:
                    capacity: "10Gi"
```

### KubeadmConfigTemplate (preKubeadmCommands)

Critical setup steps inside the VM before kubeadm join:

```bash
# 1. Mount emptyDisk for /var/lib (containerd + kubelet state)
#    ContainerDisk overlay reports 0 capacity → kubelet InvalidDiskCapacity
systemctl mask kubelet
mkfs.ext4 -F /dev/vdb
mount /dev/vdb /var/lib
systemctl start containerd
systemctl unmask kubelet

# 2. Kubelet config fix: strip fields from newer K8s versions
#    Kamaji generates KubeletConfiguration with 1.32+ fields that crash kubelet 1.30
systemctl daemon-reload

# 3. DNS fix (CRITICAL for VPC VMs)
sed -i 's/^#\?DNS=.*/DNS=8.8.8.8/' /etc/systemd/resolved.conf
sed -i 's/^#\?FallbackDNS=.*/FallbackDNS=10.96.0.200/' /etc/systemd/resolved.conf
systemctl restart systemd-resolved

# 4. DNAT rule (if VPC mode): redirect ClusterIP → TCP VPC IP
#    Kamaji advertises ClusterIP, but workers need to reach VPC fixed IP
iptables -t nat -A OUTPUT -d {cluster_ip}/32 -p tcp --dport 6443 \
  -j DNAT --to-destination {vpc_ip}:6443
```

### Worker Memory Requirements

| RAM | Status | Notes |
|-----|--------|-------|
| 2Gi | Unstable | OOM with 11+ pods (calico, coredns, kube-proxy, etc.) |
| 4Gi | Recommended | Stable operation |
| 8Gi | Production | Headroom for workloads |

---

## 10. Flux Addon Deployment

### How Addons Deploy to Tenant Clusters

Flux helm-controller on the management cluster deploys HelmReleases into tenant clusters
using a kubeconfig Secret.

```yaml
apiVersion: helm.toolkit.fluxcd.io/v2
kind: HelmRelease
metadata:
  name: {tenant}-calico
  namespace: tenant-{tenant}
spec:
  kubeConfig:
    secretRef:
      name: {tenant}-admin-kubeconfig         # Kamaji-generated Secret
      key: super-admin.svc                    # Uses SVC DNS name (in certSANs!)
  # ... chart spec
```

### Kubeconfig Key Selection

Kamaji generates multiple kubeconfig formats in the admin-kubeconfig Secret:

| Key | Server URL | Use case |
|-----|-----------|----------|
| `admin.conf` | `https://{name}.{ns}.svc:6443` | SVC DNS name |
| `super-admin.conf` | `https://{clusterIP}:6443` | ClusterIP (DO NOT USE — not in certSANs!) |
| `super-admin.svc` | `https://{name}.{ns}.svc:6443` | SVC DNS name (CORRECT for Flux) |

**Must use `super-admin.svc`** — the ClusterIP is not in certSANs, causing TLS mismatch
that manifests as timeout errors.

---

## 11. Alternative Approaches Explored

### 11.1. TCP without Dual-NIC (ovn-default only)

**Idea:** TCP pod only in ovn-default (no Multus, no fixed VPC IP). Workers access TCP
through Ingress. Enables HA (multiple replicas).

**Tested:** 2026-03-12. Full chain verified:
```
VPC pod → SNAT → MikroTik → node:32006 → Ingress (ssl-passthrough) → TCP → 403 ✅
```

**Pros:**
- HA replicas (no fixed IP constraint)
- No Multus dependency for TCP
- Simpler TCP spec

**Cons:**
- Requires working SNAT (VLAN infrastructure)
- Workers must reach NodePort through NAT chain
- MetalLB VIP not reachable from VPC (L2 topology issue)

**Decision:** Keeping dual-NIC for now. May revisit when we have Gateway API.

### 11.2. VpcEgressGateway (No VLAN)

**Idea:** Use VpcEgressGateway instead of OvnEip+OvnSnatRule. Does not require
dedicated VLAN — uses Macvlan on management NIC.

**Docs:** https://kubeovn.github.io/docs/stable/en/vpc/vpc-egress-gateway/

**Architecture:**
- Gateway pods with dual-NIC: one in VPC (overlay), one via Macvlan (underlay)
- SNAT VPC traffic through Macvlan interface
- HA via ECMP + BFD (<1s failover)

**Requirements:**
- Multus-CNI (we have it)
- Macvlan on physical NIC
- Cannot work overlay-only

**Macvlan limitation:** Macvlan pods cannot communicate with their host node
(kernel restriction). NodePort on the same node as the gateway pod would fail.

**Status:** Not tested. Planned for "no VLAN available" deployment scenario.

### 11.3. VPC Peering (custom VPC ↔ default VPC)

**Idea:** Peer custom VPC with default VPC for direct routing without SNAT.

**Result:** NOT SUPPORTED. kube-ovn VPC peering works only between two custom VPCs.
The default VPC (`ovn-cluster`) cannot participate in peering.

### 11.4. u2oInterconnection (Underlay-to-Overlay)

**Idea:** Connect overlay VPC to underlay subnet for external access.

**Result:** Requires VLAN. Hardcoded in kube-ovn source:
`if subnet.Spec.Vlan == "" → u2oInterconnection = false`

### 11.5. VpcNatGateway

**Docs state:** SPOF (single point of failure). Not recommended.
We use OvnEip+OvnSnatRule instead (OVN native, no separate pod).

### 11.6. Default-First Architecture (VPC as secondary only)

**Idea:** Every workload has eth0 in ovn-default (management, internet, DNS — all works).
VPC is only a secondary network via Multus for inter-tenant isolation.

**Pros:**
- No SNAT/EIP/VLAN needed for VPC
- No VpcDns needed (DNS through default network)
- No ovn-nbctl hacks
- Simpler significantly

**Cons:**
- VPC isolation is weaker (workloads have default network access)
- Cross-tenant traffic possible on default network (mitigated by NetworkPolicy)

**Decision:** This is the fallback plan. Current implementation uses VPC-first approach.

### 11.7. Shared EIP (Multiple VPCs, One SNAT IP)

**Tested:** 2026-03-12. Works!

One OvnEip serves SNAT for multiple VPCs:
- Multiple OvnSnatRules reference the same OvnEip — all become READY
- OVN creates separate NAT rules on each VPC router
- Caveat: kube-ovn overwrites EIP labels to last VPC (cosmetic)
- Saves IPs: 1 shared SNAT IP + 1 LRP IP per VPC

---

## 12. Bugs Found and Fixed

### Bug 1: V1Subject deprecated (kubernetes_asyncio API change)

**File:** `tenants.py:208`
**Symptom:** `AttributeError: module 'kubernetes_asyncio.client' has no attribute 'V1Subject'`
**Fix:** `V1Subject` → `RbacV1Subject`

### Bug 2: VPC IP conflict (TCP fixed IP vs VpcDns DHCP)

**File:** `tenants.py:429-435`
**Symptom:** TCP pod's fixed IP (gateway+1, e.g., 10.202.0.2) could be assigned to
VpcDns pods via DHCP, because it was not in `excludeIps`.
**Fix:** Calculate fixed_ip before subnet creation and add it to excludeIps.

### Bug 3: VM has no upstream DNS (systemd-resolved)

**File:** `tenants.py:952-953`
**Symptom:** Worker VM pods stuck in ContainerCreating. DNS lookups fail:
`lookup registry.k8s.io on 127.0.0.53:53: server misbehaving`
**Root cause:** VM uses systemd-resolved (127.0.0.53) but has no upstream DNS configured.
DHCP from KubeVirt masquerade doesn't set DNS. Cloud-init doesn't configure DNS.
**Fix:** Add `sed -i 's/^#\?DNS=.*/DNS=8.8.8.8/' /etc/systemd/resolved.conf` in
preKubeadmCommands. Works because OVN SNAT provides internet access.

### Bug 4: Flux HelmRelease TLS mismatch

**File:** `tenants.py:1159`
**Symptom:** Flux helm-controller timeout connecting to tenant API server:
`Get "https://10.105.228.74:6443/...": net/http: request canceled (Client.Timeout)`
**Root cause:** HelmRelease used `super-admin.conf` kubeconfig key which has ClusterIP
as server URL. ClusterIP is NOT in TCP's certSANs → TLS handshake fails → timeout.
**Fix:** Changed kubeconfig key from `super-admin.conf` to `super-admin.svc` which uses
the Service DNS name (`{name}.tenant-{name}.svc:6443`) — this IS in certSANs.

### Non-bug: Infrastructure subnet missing label

**Symptom:** OVN EIP/SNAT not created for tenant. VMs have no internet.
**Root cause:** `_find_infra_subnet()` searches for label `kubevirt-ui.io/purpose=infrastructure`.
The VLAN 111 subnet created during bootstrap doesn't have this label.
**Workaround:** Manually add label after bootstrap:
```bash
kubectl label subnet nat-gateway-vlan-111 kubevirt-ui.io/purpose=infrastructure
```
**TODO:** Add this label in bootstrap component definition or automation.

---

## 13. Known Limitations

### Cilium + kube-ovn NodePort DNAT

`kubeProxyReplacement` must be `"false"` in Cilium config. Cilium's eBPF NodePort
DNAT conflicts with OVN VPC routing. kube-proxy handles NodePort via nftables correctly.

### MetalLB VIP from VPC

MetalLB VIP (192.168.196.199) is NOT reachable from VPC pods.
- MetalLB L2 announces VIP via ARP on 192.168.196.0/24 only
- VPC traffic arrives from 192.168.203.0/24 (different L2 domain via MikroTik)
- OVN LB intercepts: does DNAT inside br-int OpenFlow pipeline BEFORE kube-proxy
- **NodePort works as alternative** (verified)

### Worker Memory

2Gi RAM is insufficient. 11+ system pods (calico, coredns, kube-proxy, konnectivity,
calico-apiserver, csi-node-driver) consume ~500-700Mi overhead. Kubelet becomes unstable.
Recommend 4Gi minimum.

### TCP Single Replica (Dual-NIC mode)

Fixed VPC IP can't be shared across replicas → single replica only.
RollingUpdate strategy deadlocks (new pod can't get pinned IP while old has it) → Recreate.

### ovn-nbctl LSP Options

No CRD/annotation alternative for `nat-addresses=router` + `router-port` on LSP.
Must use ovn-nbctl command for every new VPC. This is likely a kube-ovn bug/missing feature.

### ovn-external-gw-config

ConfigMap for default VPC external gateway only. Must be in controller's namespace
(`o0-kube-ovn`, not `kube-system`). Controller arg: `--external-gateway-config-ns=o0-kube-ovn`.
For custom VPCs: controller auto-skips (early return in vpc.go when enable-eip-snat=true).

---

## 14. Future Directions

### Gateway API for TCP Exposure

Replace manual nginx Ingress with Kamaji's native Gateway API support:
- `tcp.spec.controlPlane.gateway` auto-creates TLSRoute
- SNI routing, shared IP, port 6443
- Requires Gateway controller (Envoy Gateway)

### VpcEgressGateway for No-VLAN Deployments

For environments without dedicated VLAN:
- Macvlan on management NIC
- HA with BFD
- No ProviderNetwork/OVS bridge needed

### enableBfd on VPC

`vpc.spec.enableBfd: true` enables BFD probing for external gateway HA.
Fast failover (~300ms) between gateway nodes. Useful with multiple external gateways.

### Default-First Architecture

Simplify by making VPC a secondary network only:
- eth0 always in ovn-default
- net1 in VPC via Multus (optional)
- No SNAT/VpcDns/VLAN complexity for basic connectivity
- VPC isolation via Network Policy + VPC secondary NIC

### Shared EIP per Cluster

Instead of per-tenant EIP, use one shared SNAT IP for all VPCs.
Saves IP addresses. Already verified working.

### Add Infrastructure Label to Bootstrap

Automate `kubevirt-ui.io/purpose=infrastructure` label on VLAN subnet
in k8s-bootstrap component definitions or post-install hooks.

---

## 15. YAML Reference

### Complete VLAN 111 Infrastructure

```yaml
apiVersion: kubeovn.io/v1
kind: ProviderNetwork
metadata:
  name: netprov
spec:
  defaultInterface: eth0.111
  autoCreateVlanSubinterfaces: true
---
apiVersion: kubeovn.io/v1
kind: Vlan
metadata:
  name: vlan111
spec:
  id: 0
  provider: netprov
---
apiVersion: kubeovn.io/v1
kind: Subnet
metadata:
  name: nat-gateway-vlan-111
  labels:
    kubevirt-ui.io/purpose: infrastructure
spec:
  protocol: IPv4
  cidrBlock: 192.168.203.0/24
  gateway: 192.168.203.254
  vlan: vlan111
  provider: ovn
  excludeIps:
    - 192.168.203.1..192.168.203.10
    - 192.168.203.250..192.168.203.254
```

### Complete VpcDns Prerequisites

```yaml
apiVersion: v1
kind: ServiceAccount
metadata:
  name: vpc-dns
  namespace: o0-kube-ovn
---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata:
  name: system:vpc-dns
rules:
  - apiGroups: [""]
    resources: [endpoints, services, pods, namespaces]
    verbs: [list, watch]
  - apiGroups: [discovery.k8s.io]
    resources: [endpointslices]
    verbs: [list, watch]
---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRoleBinding
metadata:
  name: vpc-dns
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: ClusterRole
  name: system:vpc-dns
subjects:
  - kind: ServiceAccount
    name: vpc-dns
    namespace: o0-kube-ovn
---
apiVersion: v1
kind: ConfigMap
metadata:
  name: vpc-dns-corefile
  namespace: o0-kube-ovn
data:
  Corefile: |
    .:53 {
        errors
        health {
            lameduck 5s
        }
        ready
        kubernetes cluster.local in-addr.arpa ip6.arpa {
            pods insecure
            fallthrough in-addr.arpa ip6.arpa
        }
        prometheus :9153
        forward . 10.96.0.10 {
            prefer_udp
        }
        cache 30
        loop
        reload
        loadbalance
    }
---
apiVersion: "k8s.cni.cncf.io/v1"
kind: NetworkAttachmentDefinition
metadata:
  name: ovn-nad
  namespace: default
spec:
  config: |
    {
      "cniVersion": "0.3.0",
      "type": "kube-ovn",
      "server_socket": "/run/openvswitch/kube-ovn-daemon.sock",
      "provider": "ovn-nad.default.ovn"
    }
---
apiVersion: v1
kind: ConfigMap
metadata:
  name: vpc-dns-config
  namespace: o0-kube-ovn
data:
  enable-vpc-dns: "true"
  coredns-vip: "10.111.255.200"
  nad-name: ovn-nad
  nad-provider: ovn-nad.default.ovn
```

### VPC ACL Rules Template

```yaml
acls:
  - {action: allow-related, direction: from-lport,
     match: "ip4.src == {CIDR} && ip4.dst == {CIDR}", priority: 3000}
  - {action: allow-related, direction: from-lport,
     match: "ip4.src == {CIDR} && ip4.dst == 10.111.255.200", priority: 2500}
  - {action: drop, direction: from-lport,
     match: "ip4.src == {CIDR} && ip4.dst == 192.168.196.0/24", priority: 2000}
  - {action: drop, direction: from-lport,
     match: "ip4.src == {CIDR} && ip4.dst == 10.0.0.0/8", priority: 1999}
  - {action: drop, direction: from-lport,
     match: "ip4.src == {CIDR} && ip4.dst == 172.16.0.0/12", priority: 1998}
  - {action: drop, direction: from-lport,
     match: "ip4.src == {CIDR} && ip4.dst == 192.168.203.0/24", priority: 1997}
  - {action: allow-related, direction: from-lport,
     match: "ip4.src == {CIDR}", priority: 1000}
```

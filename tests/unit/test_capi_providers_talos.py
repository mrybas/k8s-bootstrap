"""CABPT arrives with the cluster, at a version somebody chose.

Until T9 the UI backend created the `BootstrapProvider` itself, at tenant-create
time, with an empty spec. Two consequences, and the second is the worse one:

  * installing a cluster-wide provider was a side effect of whichever tenant
    happened to be created first — a manual step wearing a disguise;
  * an empty spec means capi-operator installs whatever release is newest that
    day, so two clusters built a week apart run different CABPT versions and
    nothing in either records which.

It is a declared provider here now, beside kubeadm, Kamaji and KubeVirt, and
pinned like all of them.
"""

from pathlib import Path

import yaml

COMPONENT = (
    Path(__file__).resolve().parents[2]
    / "backend" / "definitions" / "components" / "capi-providers.yaml"
)


def _component() -> dict:
    return yaml.safe_load(COMPONENT.read_text())


class TestTalosIsADeclaredProvider:
    def test_it_has_a_template_like_every_other_provider(self) -> None:
        assert "bootstrap-talos.yaml" in _component()["templates"]

    def test_the_rendered_object_is_the_one_capi_operator_reads(self) -> None:
        d = _component()
        rendered = (
            d["templates"]["bootstrap-talos.yaml"]
            .replace("{{- if .Values.bootstrap.talos.enabled }}", "")
            .replace("{{- end }}", "")
            .replace(
                "{{ .Values.bootstrap.talos.version }}",
                d["defaultValues"]["bootstrap"]["talos"]["version"],
            )
        )
        obj = yaml.safe_load(rendered)

        assert obj["kind"] == "BootstrapProvider"
        assert obj["metadata"]["name"] == "talos"
        assert obj["metadata"]["namespace"] == "o0-capi"

    def test_the_version_is_pinned_and_not_empty(self) -> None:
        """The empty spec is the defect this replaces: `spec: {}` is a valid
        object that installs a different thing each week."""
        version = _component()["defaultValues"]["bootstrap"]["talos"]["version"]

        assert version.startswith("v")
        assert version != ""

    def test_it_is_on_by_default(self) -> None:
        """Talos is the direction the worker OS is moving; a provider that has
        to be remembered is the manual step under another name."""
        assert _component()["defaultValues"]["bootstrap"]["talos"]["enabled"] is True

    def test_it_can_be_turned_off(self) -> None:
        """A cluster that will never run Talos should not carry the CRDs."""
        tpl = _component()["templates"]["bootstrap-talos.yaml"]

        assert "{{- if .Values.bootstrap.talos.enabled }}" in tpl

    def test_the_schema_offers_both_fields(self) -> None:
        """Otherwise the version is pinned in a file nobody can see from the UI
        — and the next person pins it by editing YAML on the cluster."""
        props = (_component()["jsonSchema"]["properties"]["bootstrap"]
                 ["properties"]["talos"]["properties"])

        assert set(props) == {"enabled", "version"}
        assert props["version"]["default"] == (
            _component()["defaultValues"]["bootstrap"]["talos"]["version"]
        ), "the schema default and the value default disagree"


class TestItSitsWithTheOtherProviders:
    def test_the_same_component_carries_all_four(self) -> None:
        """One place to read what a cluster's CAPI stack is, and one place to
        change it."""
        templates = _component()["templates"]

        assert {"core-provider.yaml", "bootstrap-kubeadm.yaml",
                "bootstrap-talos.yaml", "controlplane-kamaji.yaml",
                "infra-kubevirt.yaml"} <= set(templates)

    def test_the_description_mentions_it(self) -> None:
        """The component list is how an operator decides what to enable."""
        assert "Talos" in _component()["description"]

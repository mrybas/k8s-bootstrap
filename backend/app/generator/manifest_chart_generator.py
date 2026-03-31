"""
Custom Chart Generator

Copies bundled Helm charts for components that don't have official Helm charts.
These charts contain official YAML manifests from upstream projects, packaged
as static Helm templates.

Bundled charts are stored in backend/app/charts/ and include:
- kubevirt-operator (v1.4.0)
- kubevirt-cdi (v1.61.0)
- multus-cni (v4.1.2)
"""
import logging
import shutil
from pathlib import Path
from typing import Dict, Any

logger = logging.getLogger("k8s_bootstrap.generator.custom_chart")

# Path to bundled charts directory (in definitions alongside components)
CHARTS_DIR = Path(__file__).parent.parent.parent / "definitions" / "charts"


class CustomChartGenerator:
    """Copies bundled custom charts to user's repository"""
    
    def __init__(self):
        if not CHARTS_DIR.exists():
            logger.warning(f"Bundled charts directory not found: {CHARTS_DIR}")
    
    def has_bundled_chart(self, chart_id: str) -> bool:
        """Check if a bundled chart exists for the given component"""
        chart_path = CHARTS_DIR / chart_id
        return chart_path.exists() and (chart_path / "Chart.yaml").exists()
    
    def copy_chart(self, chart_id: str, output_dir: Path) -> Path:
        """
        Copy a bundled chart to the output directory.
        
        Args:
            chart_id: Component ID (must match directory name in app/charts/)
            output_dir: Target directory (chart will be created as output_dir/chart_id/)
            
        Returns:
            Path to the copied chart
            
        Raises:
            ValueError: If bundled chart doesn't exist
        """
        source = CHARTS_DIR / chart_id
        
        if not source.exists():
            raise ValueError(f"Bundled chart not found: {chart_id}")
        
        if not (source / "Chart.yaml").exists():
            raise ValueError(f"Invalid chart structure for {chart_id}: missing Chart.yaml")
        
        dest = output_dir / chart_id
        
        # Remove existing if present
        if dest.exists():
            shutil.rmtree(dest)
        
        # Copy entire chart directory
        shutil.copytree(source, dest)
        
        logger.info(f"Copied bundled chart: {chart_id} -> {dest}")
        return dest
    
    def generate_chart(self, definition: Dict[str, Any], output_dir: Path) -> Path:
        """
        Generate/copy chart for a manifest-based component.
        
        This is the main entry point, compatible with the previous API.
        For bundled charts, it copies them. Otherwise raises an error.
        
        Args:
            definition: Component definition dict
            output_dir: Target directory for the chart
            
        Returns:
            Path to the generated/copied chart
        """
        chart_id = definition["id"]
        
        if self.has_bundled_chart(chart_id):
            return self.copy_chart(chart_id, output_dir)
        else:
            # No bundled chart available
            raise ValueError(
                f"No bundled chart for {chart_id}. "
                f"Add chart to {CHARTS_DIR}/{chart_id}/ or change chartType."
            )
    
    def list_bundled_charts(self) -> list:
        """List all available bundled charts"""
        if not CHARTS_DIR.exists():
            return []
        
        charts = []
        for item in CHARTS_DIR.iterdir():
            if item.is_dir() and (item / "Chart.yaml").exists():
                charts.append(item.name)
        
        return sorted(charts)


# Backwards compatibility alias
ManifestChartGenerator = CustomChartGenerator

# Singleton instance
_generator = None


def get_manifest_chart_generator() -> CustomChartGenerator:
    """Get or create custom chart generator instance"""
    global _generator
    if _generator is None:
        _generator = CustomChartGenerator()
    return _generator


# Also export with new name
def get_custom_chart_generator() -> CustomChartGenerator:
    """Get or create custom chart generator instance"""
    return get_manifest_chart_generator()

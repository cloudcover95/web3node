# OVERWRITE jc_omni/__init__.py
from .omni_math import OmniQuantBrain
from .omni_hunter import OmniHunter
from .hegemon_sdk import SovereignHegemonSDK

try:
    from .topology_engine import SovereignTopologyNode
    HAS_TOPOLOGY = True
except ImportError:
    HAS_TOPOLOGY = False

__all__ = [
    "OmniQuantBrain", 
    "OmniHunter", 
    "SovereignHegemonSDK",
    "SovereignTopologyNode"
]
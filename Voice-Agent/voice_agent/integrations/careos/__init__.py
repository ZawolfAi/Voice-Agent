"""CareOS integration package for Voice Agent & Multi-Agent Reception System."""

from voice_agent.integrations.careos.careos_agent_provider import (
    CareOSVoiceAgentAdapter,
    SummaryResult,
)
from voice_agent.integrations.careos.careos_sync import CareOSSyncClient

__all__ = [
    "CareOSVoiceAgentAdapter",
    "SummaryResult",
    "CareOSSyncClient",
]

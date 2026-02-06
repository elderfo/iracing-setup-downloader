"""Setup providers for iRacing Setup Downloader."""

from iracing_setup_downloader.providers.base import SetupProvider
from iracing_setup_downloader.providers.cda import CDAProvider
from iracing_setup_downloader.providers.gofast import GoFastProvider
from iracing_setup_downloader.providers.tracktitan import TracKTitanProvider

__all__ = ["SetupProvider", "GoFastProvider", "CDAProvider", "TracKTitanProvider"]

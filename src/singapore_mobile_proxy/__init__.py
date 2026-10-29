"""Route Python scrapers and browsers through a Singapore Mobile Proxy line."""

from .config import ConfigError, ProxyConfig
from .exit_ip import exit_ip, rotate_and_wait
from .rotation import RotationCooldown, RotationError, Rotator

__version__ = "0.1.0"

__all__ = ["ConfigError", "ProxyConfig", "RotationCooldown", "RotationError", "Rotator",
           "exit_ip", "rotate_and_wait", "__version__"]

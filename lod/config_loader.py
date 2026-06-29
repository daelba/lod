"""Configuration loader with support for LOD_CONFIG_MODULE environment variable."""

import importlib
import importlib.util
import logging
import os
import sys
from typing import Any

_logger = logging.getLogger(__name__)


def load_config() -> Any:
    """
    Load configuration with support for custom module via LOD_CONFIG_MODULE.

    Search order:
    1. LOD_CONFIG_MODULE environment variable (custom module)
    2. Standard 'lod_config' (backward compatibility)
    3. Fallback to None (no custom config required)

    The resolved module is reloaded on every call so that changes in
    ``LOD_CONFIG_MODULE`` or ``sys.path`` are reflected immediately. This is
    important when the same process switches between multiple Wikibase
    instances (e.g. retrobi and gotha in one runtime).

    Returns:
        Configuration module with LOD constants, or None if no config is available.

    Raises:
        ImportError: If configuration fails to load from LOD_CONFIG_MODULE.
    """
    # Try custom module from env variable
    custom_module_name = os.getenv("LOD_CONFIG_MODULE")
    if custom_module_name:
        try:
            config = importlib.import_module(custom_module_name)
            # Reload to ensure the module matches the current sys.path / env.
            if custom_module_name in sys.modules:
                config = importlib.reload(config)
            _logger.info(f"Configuration loaded from LOD_CONFIG_MODULE={custom_module_name}")
            return config
        except ImportError as e:
            raise ImportError(
                f"Failed to load configuration from LOD_CONFIG_MODULE='{custom_module_name}': {e}"
            ) from e

    # Fallback to standard lod_config
    try:
        spec = importlib.util.find_spec("lod_config")
        if spec is not None:
            config = importlib.import_module("lod_config")
            if "lod_config" in sys.modules:
                config = importlib.reload(config)
            _logger.info("Configuration loaded from standard 'lod_config' module")
            return config
    except ImportError:
        pass

    # No configuration available
    _logger.debug("No custom configuration module found")
    return None

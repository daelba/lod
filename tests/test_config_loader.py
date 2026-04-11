"""Tests for the config loader module."""

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from lod import config_loader


class ConfigLoaderTests(unittest.TestCase):
    def tearDown(self):
        """Clean up environment after each test."""
        os.environ.pop("LOD_CONFIG_MODULE", None)

    def test_load_config_with_custom_module_env_var(self):
        """Test loading config from LOD_CONFIG_MODULE environment variable."""
        os.environ["LOD_CONFIG_MODULE"] = "json"

        config = config_loader.load_config()

        self.assertIsNotNone(config)
        self.assertEqual(config.__name__, "json")

    def test_load_config_raises_on_invalid_module(self):
        """Test that ImportError is raised when LOD_CONFIG_MODULE module doesn't exist."""
        os.environ["LOD_CONFIG_MODULE"] = "nonexistent_module_12345"

        with self.assertRaises(ImportError) as ctx:
            config_loader.load_config()

        self.assertIn("nonexistent_module_12345", str(ctx.exception))

    def test_load_config_fallback_to_lod_config(self):
        """Test fallback to lod_config module when LOD_CONFIG_MODULE is not set."""
        # Create a temporary lod_config module
        with tempfile.TemporaryDirectory() as tmpdir:
            config_file = Path(tmpdir) / "lod_config.py"
            config_file.write_text("TEST_SETTING = 'from_lod_config'")

            # Add tmpdir to PYTHONPATH
            sys.path.insert(0, tmpdir)
            try:
                config = config_loader.load_config()
                self.assertIsNotNone(config)
                self.assertEqual(getattr(config, "TEST_SETTING", None), "from_lod_config")
            finally:
                sys.path.remove(tmpdir)

    def test_load_config_returns_none_when_no_config_available(self):
        """Test that None is returned when no configuration is available."""
        # Ensure LOD_CONFIG_MODULE is not set
        os.environ.pop("LOD_CONFIG_MODULE", None)

        # Temporarily hide lod_config from sys.modules
        lod_config_backup = sys.modules.pop("lod_config", None)
        try:
            # Mock importlib.util.find_spec to return None
            with patch("lod.config_loader.importlib.util.find_spec", return_value=None):
                config = config_loader.load_config()
                self.assertIsNone(config)
        finally:
            if lod_config_backup is not None:
                sys.modules["lod_config"] = lod_config_backup

    def test_load_config_prefers_env_var_over_lod_config(self):
        """Test that LOD_CONFIG_MODULE has priority over lod_config fallback."""
        # Create a temporary lod_config module
        with tempfile.TemporaryDirectory() as tmpdir:
            config_file = Path(tmpdir) / "lod_config.py"
            config_file.write_text("PRIORITY = 'lod_config'")

            sys.path.insert(0, tmpdir)
            try:
                os.environ["LOD_CONFIG_MODULE"] = "json"
                config = config_loader.load_config()

                # Should be json module, not lod_config
                self.assertEqual(config.__name__, "json")
            finally:
                sys.path.remove(tmpdir)


if __name__ == "__main__":
    unittest.main()

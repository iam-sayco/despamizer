"""Settings and environment loading for despamizer."""

# Standard Library
from pathlib import Path
import sys

BASE_DIR = Path(__file__).parent
PROJECT_DIR = BASE_DIR.parent
CONFIG_PATH = PROJECT_DIR / "config.yaml"
VERBOSE = "--vvv" in sys.argv

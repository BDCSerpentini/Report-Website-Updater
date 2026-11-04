import sys
from pathlib import Path

# Add the src directory to Python's import path
ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

from matador_reporting.app import main

if __name__ == "__main__":
    main()

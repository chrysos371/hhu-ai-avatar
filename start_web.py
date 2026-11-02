"""Run the local workbench from a source checkout without an editable install."""
from pathlib import Path
import sys


if __name__ == '__main__':
    sys.path.insert(0, str(Path(__file__).resolve().parent / 'src'))
    from avatar.web import main
    main()

"""Print the canonical project data location for shell and Node launchers."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from avatar.paths import project_data_root

if __name__ == '__main__':
    print(project_data_root())

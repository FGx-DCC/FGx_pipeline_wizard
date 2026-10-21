"""Main entry point for config wizard"""

import sys
from pathlib import Path

from wizard.wizard import ask_bool


def main() -> None:
    pass


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(f"Usage: {__file__} out_config.txt")
    config_file = Path(sys.argv[1])
    if config_file.exists():
        ask_bool("")
    main()

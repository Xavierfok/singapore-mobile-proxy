"""`singapore-proxy check` prints the exit IP; `singapore-proxy rotate` rotates and prints old and new."""

from __future__ import annotations

import argparse
import json
import sys

from . import __version__
from .config import ConfigError, ProxyConfig
from .exit_ip import exit_ip, rotate_and_wait
from .rotation import RotationError, Rotator


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="singapore-proxy", description=__doc__)
    parser.add_argument("--version", action="version", version=__version__)
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("check", help="show the exit IP, country and carrier")
    rot = sub.add_parser("rotate", help="rotate the IP and wait for the line to come back")
    rot.add_argument("--timeout", type=float, default=90, help="seconds to wait for the new IP (default 90)")
    args = parser.parse_args(argv)

    try:
        config = ProxyConfig.from_env()
        if args.cmd == "check":
            result = exit_ip(config)
        else:
            result = rotate_and_wait(config, Rotator.from_env(), timeout=args.timeout)
    except (ConfigError, RotationError, OSError) as e:
        print(f"singapore-proxy: {e}", file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())

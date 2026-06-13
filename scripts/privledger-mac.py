#!/usr/bin/env python3

import sys

from privledger import mac_config, supervise_capture


if __name__ == "__main__":
    if "--debug-platform-entrypoint" not in sys.argv:
        print(
            "privledger-mac.py is a debug-only platform shim. "
            "Run scripts/privledger.py for normal capture.",
            file=sys.stderr,
        )
        sys.exit(2)
    supervise_capture(mac_config())

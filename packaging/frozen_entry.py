"""Entry point used by self-contained Linux target executables."""

import os
import sys
from pathlib import Path

ca_bundle = Path(sys.executable).with_name("ca-certificates.crt")
if ca_bundle.is_file():
    os.environ.setdefault("SSL_CERT_FILE", str(ca_bundle))


def run() -> int:
    from ph.app import main

    return main()


raise SystemExit(run())

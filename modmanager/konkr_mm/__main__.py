import sys

if "--server" in sys.argv:
    from .server import run_headless
    sys.exit(run_headless())

from .gui import main  # noqa: E402

sys.exit(main())

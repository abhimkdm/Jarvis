import asyncio
import sys

from os_kernel import JarvisKernel
from os_kernel.log_config import get_jarvis_logger, install_global_exception_hook


def main() -> None:
    install_global_exception_hook()
    log = get_jarvis_logger()

    kernel = JarvisKernel()
    kernel.tray.start_background()
    try:
        asyncio.run(kernel.run())
    except KeyboardInterrupt:
        print("\nGoodbye.")
    except Exception:
        log.exception("Jarvis crashed during run loop")
        raise


if __name__ == "__main__":
    main()
    sys.exit(0)

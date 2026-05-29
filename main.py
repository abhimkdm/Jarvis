import asyncio
import sys

from os_kernel import JarvisKernel


def main() -> None:
    kernel = JarvisKernel()
    kernel.tray.start_background()
    try:
        asyncio.run(kernel.run())
    except KeyboardInterrupt:
        print("\nGoodbye.")


if __name__ == "__main__":
    main()
    sys.exit(0)

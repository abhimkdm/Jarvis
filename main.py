import sys
import asyncio

from os_kernel.core import JarvisKernel
from os_kernel.logs.log_config import install_global_exception_hook

# ─── WINDOWS EVENT LOOP BUG PATCH ───
# Forces Python to use the standard Selector event loop on Windows if the proactor loop tears down
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


async def main():
    # Initialize the microkernel architecture
    kernel = JarvisKernel()

    try:
        await kernel.boot_up()
    except KeyboardInterrupt:
        print("\n[Kernel OS: Shutdown signal detected via manual override.]")
    finally:
        # Guarantee a graceful teardown loop to avoid NoneType attribute errors
        print("[Kernel OS: Cleaning up active process tunnels...]")
        await kernel.mcp_hub.shutdown()

        # Cancel all remaining background tasks safely
        tasks = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
        for task in tasks:
            task.cancel()

        # Give tasks a quick moment to finish cancellation contexts
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

        loop = asyncio.get_running_loop()
        loop.stop()


if __name__ == "__main__":
    install_global_exception_hook()

    # Boot the async runtime environment context cleanly
    try:
        asyncio.run(main())
    except RuntimeError:
        # Catches the secondary loop closed error that happens on force exit
        pass

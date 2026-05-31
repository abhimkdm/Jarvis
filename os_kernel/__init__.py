"""Jarvis microkernel package. Import `JarvisKernel` from `os_kernel.core`."""

__all__ = ["JarvisKernel"]


def __getattr__(name: str):
    if name == "JarvisKernel":
        from os_kernel.core import JarvisKernel

        return JarvisKernel
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

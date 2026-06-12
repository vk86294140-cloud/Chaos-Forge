"""Host-level fault injectors (resource exhaustion)."""

from .resource import cpu_hog, memory_hog

__all__ = ["cpu_hog", "memory_hog"]

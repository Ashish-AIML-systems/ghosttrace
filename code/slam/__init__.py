"""SLAM shared package.

Business modules are owned by separate teammates. Public cross-module objects
live in :mod:`slam.contracts` and are versioned independently of implementation.
"""

from slam.contracts import CONTRACT_VERSION

__all__ = ["CONTRACT_VERSION"]

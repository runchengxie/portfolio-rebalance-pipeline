"""Service Layer Module

This package contains all the pure functions and classes for business logic.
Service layer functions only accept parameters and return structured results, they do not perform I/O operations or print.
"""

from . import data, selection

__all__ = ["data", "selection"]

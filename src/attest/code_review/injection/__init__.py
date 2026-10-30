"""Code-aware prompt-injection check for pull requests and the reviews written about them."""

from .check import check_code_injection

__all__ = ["check_code_injection"]

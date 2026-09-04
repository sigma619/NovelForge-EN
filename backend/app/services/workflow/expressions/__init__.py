"""Expression system (single-engine controlled eval)"""

from .evaluator import (
    ExpressionEvaluator,
    evaluate_expression,
    get_expression_dependencies,
    validate_expression_syntax,
)
from .functions import register_function, get_builtin_functions, get_helper_metadata, HelperMeta
from .validator import validate_expression

# Domain helper packs register themselves on import; they must be loaded before
# the safe-globals cache in builtins.py is first populated.
from app.services.lab import lab_helpers as _lab_helpers  # noqa: F401,E402

__all__ = [
    "ExpressionEvaluator",
    "evaluate_expression",
    "get_expression_dependencies",
    "validate_expression_syntax",
    "register_function",
    "get_builtin_functions",
    "get_helper_metadata",
    "HelperMeta",
    "validate_expression",
]

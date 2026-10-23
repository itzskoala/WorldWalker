#route_validation.py

from dataclasses import dataclass
from typing import Literal

RouteInvalidReason = Literal["too_close", "no_route"]


@dataclass(frozen=True)
class RouteValidation:
    valid: bool
    reason: RouteInvalidReason | None = None

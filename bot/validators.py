from dataclasses import dataclass
from typing import Optional


VALID_SIDES = {"BUY", "SELL"}
VALID_ORDER_TYPES = {"MARKET", "LIMIT", "STOP"}

from bot.logging_config import setup_logging
logger = setup_logging()


class ValidationError(Exception):
    """Raised when order parameters fail validation."""
    pass


@dataclass
class OrderParams:
    symbol: str
    side: str
    order_type: str
    quantity: float
    price: Optional[float] = None


def validate_order_params(
    symbol: str,
    side: str,
    order_type: str,
    quantity: float,
    price: Optional[float] = None,
) -> OrderParams:
    """
    Validates and normalises order parameters.
    Returns a clean OrderParams dataclass on success.
    Raises ValidationError with a human-readable message on failure.
    """
    errors = []

    if not symbol or not symbol.strip():
        errors.append("symbol cannot be empty")
    else:
        symbol = symbol.strip().upper()

    side = side.strip().upper() if side else ""
    if side not in VALID_SIDES:
        errors.append(f"side must be one of {VALID_SIDES}, got '{side}'")

    order_type = order_type.strip().upper() if order_type else ""
    if order_type not in VALID_ORDER_TYPES:
        errors.append(f"order_type must be one of {VALID_ORDER_TYPES}, got '{order_type}'")

    try:
        quantity = float(quantity)
        if quantity <= 0:
            errors.append("quantity must be greater than 0")
    except (TypeError, ValueError):
        errors.append(f"quantity must be a number, got '{quantity}'")

    if order_type in {"LIMIT", "STOP"}:
        if price is None:
            errors.append(f"price is required for {order_type} orders")
        else:
            try:
                price = float(price)
                if price <= 0:
                    errors.append("price must be greater than 0")
            except (TypeError, ValueError):
                errors.append(f"price must be a number, got '{price}'")

    if order_type == "MARKET" and price is not None:
        logger.warning(
            "Price param ignored for MARKET order",
            extra={"symbol": symbol, "price_provided": price},
        )
        price = None

    if errors:
        raise ValidationError("; ".join(errors))

    return OrderParams(
        symbol=symbol,
        side=side,
        order_type=order_type,
        quantity=quantity,
        price=price,
    )
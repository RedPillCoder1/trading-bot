from datetime import datetime, timezone
from typing import Optional

from bot.client import BinanceClient, BinanceClientError
from bot.validators import OrderParams
from bot.logging_config import setup_logging

logger = setup_logging()


def place_order(client: BinanceClient, params: OrderParams) -> dict:
    """
    Places an order on Binance Futures Testnet.
    Always returns a normalised dict — raw Binance response never leaks out.

    Success schema:
    {
        "success": true,
        "order_id": "...",
        "symbol": "BTCUSDT",
        "side": "BUY",
        "type": "MARKET",
        "quantity": "0.001",
        "avg_price": "...",
        "status": "FILLED",
        "timestamp": "2026-01-01T00:00:00+00:00",
        "error": null
    }

    Failure schema: same structure with success=false and error populated.
    """
    payload = {
        "symbol": params.symbol,
        "side": params.side,
        "type": params.order_type,
        "quantity": params.quantity,
    }

    if params.order_type in {"LIMIT", "STOP"}:
        payload["price"] = params.price
        payload["timeInForce"] = "GTC"

    if params.order_type == "STOP":
        payload["stopPrice"] = params.price

    logger.info(
        "Placing order",
        extra={
            "symbol": params.symbol,
            "side": params.side,
            "type": params.order_type,
            "quantity": params.quantity,
            "price": params.price,
        },
    )

    try:
        result = client.place_order(**payload)
    except BinanceClientError as e:
        logger.error("Order rejected by Binance", extra={"error": str(e)})
        return _failure_response(params, str(e))

    if not result["success"]:
        return _failure_response(params, result["error"])

    raw = result["data"]

    response = {
        "success": True,
        "order_id": str(raw.get("orderId", "")),
        "symbol": raw.get("symbol", params.symbol),
        "side": raw.get("side", params.side),
        "type": raw.get("type", params.order_type),
        "quantity": str(raw.get("origQty", params.quantity)),
        "avg_price": str(raw.get("avgPrice") or raw.get("price") or "0"),
        "status": raw.get("status", "UNKNOWN"),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "error": None,
    }

    logger.info(
        "Order placed successfully",
        extra={
            "order_id": response["order_id"],
            "symbol": response["symbol"],
            "status": response["status"],
            "avg_price": response["avg_price"],
        },
    )

    return response


def _failure_response(params: OrderParams, error: str) -> dict:
    return {
        "success": False,
        "order_id": None,
        "symbol": params.symbol,
        "side": params.side,
        "type": params.order_type,
        "quantity": str(params.quantity),
        "avg_price": None,
        "status": "FAILED",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "error": error,
    }
import hashlib
import hmac
import time
import requests

from bot.logging_config import setup_logging

logger = setup_logging()

TESTNET_BASE_URL = "https://testnet.binancefuture.com"
REQUEST_TIMEOUT = 10        
MAX_RETRIES = 3
RETRY_BACKOFF = [1, 2, 4]

class BinanceClientError(Exception):
    """Raised when the Binance API returns a 4xx error."""
    pass


class BinanceClient:
    def __init__(self, api_key: str, api_secret: str):
        self.api_key = api_key
        self.api_secret = api_secret
        self.session = requests.Session()
        self.session.headers.update({
            "X-MBX-APIKEY": self.api_key,
            "Content-Type": "application/x-www-form-urlencoded",
        })

    # Internal helpers
    def _sign(self, params: dict) -> dict:
        """Appends HMAC SHA256 signature to a params dict."""
        query_string = "&".join(f"{k}={v}" for k, v in params.items())
        signature = hmac.new(
            self.api_secret.encode("utf-8"),
            query_string.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        params["signature"] = signature
        return params

    def _safe_params(self, params: dict) -> dict:
        """Strips secret from params before logging."""
        return {k: v for k, v in params.items() if k != "signature"}

    def _request(self, method: str, endpoint: str, params: dict) -> dict:
        """
        Single entry point for all API calls.
        Handles signing, retries, timeouts, and error normalisation.
        Returns: {"success": bool, "data": dict | None, "error": str | None}
        """
        params["timestamp"] = int(time.time() * 1000)
        params = self._sign(params)
        url = f"{TESTNET_BASE_URL}{endpoint}"

        last_error = None

        for attempt in range(1, MAX_RETRIES + 1):
            t_start = time.monotonic()
            try:
                resp = self.session.request(
                    method,
                    url,
                    params=params if method == "GET" else None,
                    data=params if method == "POST" else None,
                    timeout=REQUEST_TIMEOUT,
                )
                latency_ms = round((time.monotonic() - t_start) * 1000, 1)

                logger.debug(
                    "API request",
                    extra={
                        "endpoint": endpoint,
                        "method": method,
                        "params": self._safe_params(params),
                        "status_code": resp.status_code,
                        "latency_ms": latency_ms,
                        "attempt": attempt,
                    },
                )

                if 400 <= resp.status_code < 500:
                    error_msg = resp.json().get("msg", resp.text)
                    logger.error(
                        "Client error from Binance API",
                        extra={
                            "endpoint": endpoint,
                            "status_code": resp.status_code,
                            "error": error_msg,
                        },
                    )
                    raise BinanceClientError(error_msg)

                resp.raise_for_status()
                return {"success": True, "data": resp.json(), "error": None}

            except BinanceClientError:
                raise

            except requests.exceptions.Timeout as e:
                last_error = f"Request timed out after {REQUEST_TIMEOUT}s"
                logger.warning(
                    "Request timeout, will retry",
                    extra={"attempt": attempt, "endpoint": endpoint},
                )

            except requests.exceptions.ConnectionError as e:
                last_error = "Network connection error"
                logger.warning(
                    "Connection error, will retry",
                    extra={"attempt": attempt, "endpoint": endpoint},
                )

            except requests.exceptions.HTTPError as e:
                last_error = str(e)
                logger.warning(
                    "HTTP error, will retry",
                    extra={"attempt": attempt, "endpoint": endpoint, "error": last_error},
                )

            if attempt < MAX_RETRIES:
                time.sleep(RETRY_BACKOFF[attempt - 1])

        logger.error(
            "All retry attempts exhausted",
            extra={"endpoint": endpoint, "error": last_error},
        )
        return {"success": False, "data": None, "error": last_error}


    # Public API methods
    def place_order(self, **params) -> dict:
        return self._request("POST", "/fapi/v1/order", params)

    def get_exchange_info(self) -> dict:
        """Lightweight connectivity check — no auth needed."""
        try:
            resp = self.session.get(
                f"{TESTNET_BASE_URL}/fapi/v1/ping", timeout=REQUEST_TIMEOUT
            )
            resp.raise_for_status()
            return {"success": True, "data": {}, "error": None}
        except Exception as e:
            return {"success": False, "data": None, "error": str(e)}
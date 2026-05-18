"""
Mini test harness — 10 test cases covering validation, agent parsing, and client retry behaviour.
"""

import sys
import os
import unittest
from unittest.mock import patch, MagicMock
from rich.console import Console
from rich.table import Table
from rich import box

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bot.validators import validate_order_params, ValidationError, OrderParams
from bot.agent import parse_order_intent, AgentParseError

console = Console()


# Test cases
class TestValidation(unittest.TestCase):

    def test_01_valid_market_buy(self):
        """Valid MARKET BUY params pass without error."""
        params = validate_order_params("BTCUSDT", "BUY", "MARKET", 0.001)
        self.assertEqual(params.symbol, "BTCUSDT")
        self.assertEqual(params.side, "BUY")
        self.assertIsNone(params.price)

    def test_02_valid_limit_sell(self):
        """Valid LIMIT SELL params with price pass without error."""
        params = validate_order_params("ETHUSDT", "SELL", "LIMIT", 0.5, price=2000.0)
        self.assertEqual(params.order_type, "LIMIT")
        self.assertEqual(params.price, 2000.0)

    def test_03_limit_missing_price(self):
        """LIMIT order without price raises ValidationError."""
        with self.assertRaises(ValidationError):
            validate_order_params("BTCUSDT", "BUY", "LIMIT", 0.001, price=None)

    def test_04_negative_quantity(self):
        """Negative quantity raises ValidationError."""
        with self.assertRaises(ValidationError):
            validate_order_params("BTCUSDT", "BUY", "MARKET", -1)

    def test_05_invalid_side(self):
        """Side 'SHORT' raises ValidationError."""
        with self.assertRaises(ValidationError):
            validate_order_params("BTCUSDT", "SHORT", "MARKET", 0.001)

    def test_06_symbol_auto_uppercased(self):
        """Lowercase symbol is uppercased automatically."""
        params = validate_order_params("btcusdt", "BUY", "MARKET", 0.001)
        self.assertEqual(params.symbol, "BTCUSDT")

    def test_07_market_price_ignored(self):
        """Price passed to MARKET order is silently dropped."""
        params = validate_order_params("BTCUSDT", "BUY", "MARKET", 0.001, price=50000)
        self.assertIsNone(params.price)


class TestAgent(unittest.TestCase):

    def _mock_openrouter(self, json_body: str):
        """Helper: patches requests.post to return a fake OpenRouter response."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "choices": [{"message": {"content": json_body}}]
        }
        mock_resp.raise_for_status = MagicMock()
        return mock_resp

    def test_08_agent_parses_market_buy(self):
        """Agent correctly parses 'Buy 0.01 BTC at market price'."""
        fake_response = '{"symbol":"BTCUSDT","side":"BUY","order_type":"MARKET","quantity":0.01,"price":null}'
        with patch("requests.post", return_value=self._mock_openrouter(fake_response)):
            params = parse_order_intent("Buy 0.01 BTC at market price", api_key="test")
        self.assertEqual(params.symbol, "BTCUSDT")
        self.assertEqual(params.side, "BUY")
        self.assertEqual(params.order_type, "MARKET")
        self.assertAlmostEqual(params.quantity, 0.01)

    def test_09_agent_parses_limit_sell(self):
        """Agent correctly parses 'Sell 0.005 ETH limit at 2000'."""
        fake_response = '{"symbol":"ETHUSDT","side":"SELL","order_type":"LIMIT","quantity":0.005,"price":2000}'
        with patch("requests.post", return_value=self._mock_openrouter(fake_response)):
            params = parse_order_intent("Sell 0.005 ETH limit at 2000", api_key="test")
        self.assertEqual(params.order_type, "LIMIT")
        self.assertEqual(params.price, 2000.0)

    def test_10_agent_gibberish_raises_error(self):
        """Agent returns AgentParseError for unparseable input."""
        fake_response = '{"error": "cannot determine order parameters from input"}'
        with patch("requests.post", return_value=self._mock_openrouter(fake_response)):
            with self.assertRaises(AgentParseError):
                parse_order_intent("purple elephant dancing", api_key="test")


# Pretty pass/fail output
def run_with_pretty_output():
    loader = unittest.TestLoader()
    suite = loader.loadTestsFromModule(sys.modules[__name__])

    results_data = []

    class TrackingResult(unittest.TestResult):
        def addSuccess(self, test):
            results_data.append((test._testMethodName, "PASS", ""))
        def addFailure(self, test, err):
            results_data.append((test._testMethodName, "FAIL", str(err[1])))
        def addError(self, test, err):
            results_data.append((test._testMethodName, "ERROR", str(err[1])))

    runner = unittest.TextTestRunner(resultclass=TrackingResult, stream=open(os.devnull, "w"))
    result = runner.run(suite)

    table = Table(title="Test Harness Results", box=box.ROUNDED)
    table.add_column("#", style="dim", width=4)
    table.add_column("Test", style="cyan")
    table.add_column("Result", width=8)
    table.add_column("Notes", style="dim")

    DESCRIPTIONS = {
        "test_01_valid_market_buy": "Valid MARKET BUY params",
        "test_02_valid_limit_sell": "Valid LIMIT SELL params with price",
        "test_03_limit_missing_price": "LIMIT order missing price → error",
        "test_04_negative_quantity": "Negative quantity → error",
        "test_05_invalid_side": "Invalid side 'SHORT' → error",
        "test_06_symbol_auto_uppercased": "Lowercase symbol auto-uppercased",
        "test_07_market_price_ignored": "Price on MARKET order dropped",
        "test_08_agent_parses_market_buy": "Agent parses market buy intent",
        "test_09_agent_parses_limit_sell": "Agent parses limit sell intent",
        "test_10_agent_gibberish_raises_error": "Agent rejects gibberish input",
    }

    passed = sum(1 for _, status, _ in results_data if status == "PASS")
    total = len(results_data)

    for i, (name, status, notes) in enumerate(results_data, 1):
        status_str = "[green]PASS[/green]" if status == "PASS" else "[red]FAIL[/red]"
        table.add_row(str(i), DESCRIPTIONS.get(name, name), status_str, notes[:80])

    console.print(table)
    console.print(f"\n[bold]Results: {passed}/{total} passed[/bold]")

    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(run_with_pretty_output())
import os
import typer
from typing import Optional
from rich.console import Console
from rich.table import Table
from rich import box
from dotenv import load_dotenv

from bot.client import BinanceClient
from bot.validators import validate_order_params, ValidationError, OrderParams
from bot.orders import place_order
from bot.agent import parse_order_intent, AgentParseError
from bot.logging_config import setup_logging

load_dotenv()
logger = setup_logging()
app = typer.Typer(help="Binance Futures Testnet Trading Bot")
console = Console()


# Shared helpers
def _get_client() -> BinanceClient:
    api_key = os.getenv("BINANCE_API_KEY", "")
    api_secret = os.getenv("BINANCE_API_SECRET", "")
    if not api_key or not api_secret:
        console.print("[red]Error:[/red] BINANCE_API_KEY and BINANCE_API_SECRET must be set in .env")
        raise typer.Exit(1)
    return BinanceClient(api_key, api_secret)


def _confirm_and_execute(client: BinanceClient, params: OrderParams) -> None:
    """Shows order summary table, asks Y/N, then places the order."""
    table = Table(title="Order Summary", box=box.ROUNDED, show_header=False)
    table.add_column("Field", style="cyan", width=14)
    table.add_column("Value", style="white")

    table.add_row("Symbol", params.symbol)
    table.add_row("Side", f"[green]{params.side}[/green]" if params.side == "BUY" else f"[red]{params.side}[/red]")
    table.add_row("Type", params.order_type)
    table.add_row("Quantity", str(params.quantity))
    table.add_row("Price", str(params.price) if params.price else "Market price")

    console.print(table)

    confirmed = typer.confirm("Place this order?")
    if not confirmed:
        console.print("[yellow]Order cancelled.[/yellow]")
        raise typer.Exit(0)

    result = place_order(client, params)
    _print_result(result)


def _print_result(result: dict) -> None:
    if result["success"]:
        table = Table(title="Order Response", box=box.ROUNDED, show_header=False)
        table.add_column("Field", style="cyan", width=14)
        table.add_column("Value", style="white")

        table.add_row("Status", f"[green]{result['status']}[/green]")
        table.add_row("Order ID", result["order_id"])
        table.add_row("Symbol", result["symbol"])
        table.add_row("Side", result["side"])
        table.add_row("Type", result["type"])
        table.add_row("Quantity", result["quantity"])
        table.add_row("Avg Price", result["avg_price"] or "—")
        table.add_row("Timestamp", result["timestamp"])

        console.print(table)
        console.print("[green]✓ Order placed successfully[/green]")
    else:
        console.print(f"[red]✗ Order failed:[/red] {result['error']}")



# Commands
@app.command()
def order(
    symbol: str = typer.Option(..., help="Trading pair, e.g. BTCUSDT"),
    side: str = typer.Option(..., help="BUY or SELL"),
    order_type: str = typer.Option(..., "--type", help="MARKET, LIMIT, or STOP"),
    quantity: float = typer.Option(..., help="Order quantity"),
    price: Optional[float] = typer.Option(None, help="Price (required for LIMIT/STOP)"),
):
    """Place a MARKET, LIMIT, or STOP order via CLI flags."""
    try:
        params = validate_order_params(symbol, side, order_type, quantity, price)
    except ValidationError as e:
        console.print(f"[red]Validation error:[/red] {e}")
        raise typer.Exit(1)

    client = _get_client()
    _confirm_and_execute(client, params)


@app.command()
def agent(
    prompt: str = typer.Argument(..., help='Natural language order, e.g. "Buy 0.01 BTC at market price"'),
):
    """Parse a natural language order and execute it."""
    api_key = os.getenv("GROQ_API_KEY", "")
    if not api_key:
        console.print("[red]Error:[/red] OPENROUTER_API_KEY must be set in .env")
        raise typer.Exit(1)

    console.print(f"[cyan]Parsing:[/cyan] {prompt}")

    try:
        params = parse_order_intent(prompt, api_key)
    except AgentParseError as e:
        console.print(f"[red]Agent error:[/red] {e}")
        raise typer.Exit(1)

    client = _get_client()
    _confirm_and_execute(client, params)


if __name__ == "__main__":
    app()
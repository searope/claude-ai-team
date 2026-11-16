"""The orders the board shows. A real shop would read them from its database."""

ORDERS = [
    {"id": 1001, "customer": "Ada Park", "items": 3, "total_cents": 4250},
    {"id": 1002, "customer": "Ben Ortiz", "items": 1, "total_cents": 1999},
    {"id": 1003, "customer": "Chloe Lindqvist", "items": 7, "total_cents": 12840},
    {"id": 1004, "customer": "Dmitri <Dima> Volkov", "items": 2, "total_cents": 600},
]


def list_orders():
    """A copy of every order, oldest first."""
    return [dict(order) for order in ORDERS]


def total_cents(orders) -> int:
    return sum(order["total_cents"] for order in orders)


def money(cents: int) -> str:
    """Cents as dollars: 4250 -> $42.50."""
    return f"${cents // 100}.{cents % 100:02d}"


def average_cents(orders) -> int:
    """The average order total in cents. `orders` is not empty."""
    return total_cents(orders) // len(orders)

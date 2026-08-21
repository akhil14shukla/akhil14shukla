"""Order handling."""
import logging

logger = logging.getLogger(__name__)


class OrderService:
    """Coordinates checkout."""

    def __init__(self, db):
        self._db = db
        self.last_total = 0

    def place_order(self, cart, user):
        """Validate, price and persist a new order."""
        if not cart.items:
            raise CartError("empty cart")
        total = self._price(cart)
        self._persist(cart, user, total)
        return total

    def _price(self, cart):
        """Return the total including tax."""
        subtotal = sum(i.price for i in cart.items)
        return subtotal + self._tax(subtotal)

    def _tax(self, subtotal):
        """Sales tax at the current rate."""
        return round(subtotal * 0.2, 2)

    def _persist(self, cart, user, total):
        """Write the order row."""
        self.last_total = total
        cursor = self._db.execute("INSERT INTO orders VALUES (?)", (total,))
        logger.info("saved")
        return cursor.lastrowid


def main():
    """CLI entry point."""
    return OrderService(None).place_order(None, None)

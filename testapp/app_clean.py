"""Clean and bug-free Flask reference implementation for Mini Shop."""
import os
import sqlite3
import sys
from typing import Any, Dict, List
from flask import Flask, jsonify, render_template_string, request

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

app = Flask(__name__)

PRODUCTS: Dict[int, Dict[str, Any]] = {
    1: {"id": 1, "name": "Notebook", "price": 120.0},
    2: {"id": 2, "name": "Pen", "price": 20.0},
    3: {"id": 3, "name": "Bag", "price": 650.0},
}
DISCOUNTS: Dict[str, float] = {
    "SAVE10": 0.10,
    "SAVE20": 0.20,
}
USERS: Dict[int, str] = {
    1: "Asha",
    2: "Ravi",
}
CART: List[Dict[str, int]] = []

conn = sqlite3.connect(":memory:", check_same_thread=False)
conn.execute("CREATE TABLE IF NOT EXISTS products (id INTEGER PRIMARY KEY, name TEXT, price REAL)")
for item in PRODUCTS.values():
    conn.execute(
        "INSERT OR REPLACE INTO products (id, name, price) VALUES (?, ?, ?)",
        (item["id"], item["name"], item["price"]),
    )
conn.commit()


def cart_total() -> float:
    """Calculate total price of all items in cart."""
    return sum(PRODUCTS[item["product_id"]]["price"] * item["qty"] for item in CART)


INDEX_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Mini Shop</title>
</head>
<body>
  <h1>Mini Shop</h1>

  <h2>Search Products</h2>
  <form action="/search" method="GET">
    <input type="text" name="q" placeholder="Search products...">
    <button type="submit">Search</button>
  </form>

  <h2>Check Discount</h2>
  <form action="/discount" method="GET">
    <input type="text" name="code" placeholder="Discount code...">
    <button type="submit">Apply Discount</button>
  </form>

  <h2>Add to Cart</h2>
  <form action="/cart/add" method="POST">
    <label for="product_id">Product:</label>
    <select name="product_id" id="product_id">
      <option value="1">Notebook ($120.0)</option>
      <option value="2">Pen ($20.0)</option>
      <option value="3">Bag ($650.0)</option>
    </select>
    <label for="qty">Quantity:</label>
    <input type="number" name="qty" id="qty" value="1">
    <button type="submit">Add to Cart</button>
  </form>

  <h2>Quick Links</h2>
  <ul>
    <li><a href="/profile/1">User Profile 1</a></li>
    <li><a href="/profile/2">User Profile 2</a></li>
    <li><a href="/checkout">Checkout</a></li>
  </ul>
</body>
</html>
"""


@app.route("/", methods=["GET"])
def index() -> str:
    """Render storefront home page."""
    return render_template_string(INDEX_HTML)


@app.route("/search", methods=["GET"])
def search():
    """Search products matching substring in query."""
    q = request.args.get("q", "")
    rows = conn.execute("SELECT id, name FROM products WHERE name LIKE ?", (f"%{q}%",)).fetchall()
    return jsonify({"results": [{"id": row[0], "name": row[1]} for row in rows]})


@app.route("/discount", methods=["GET"])
def discount():
    """Look up discount rate by code."""
    code = request.args.get("code", "")
    rate = DISCOUNTS.get(code.upper())
    if rate is None:
        return jsonify({"error": "invalid code"}), 404
    return jsonify({"code": code.upper(), "rate": rate})


@app.route("/profile/<int:user_id>", methods=["GET"])
def profile(user_id: int):
    """Fetch user profile by user id."""
    user = USERS.get(user_id)
    if user is None:
        return jsonify({"error": "user not found"}), 404
    return jsonify({"id": user_id, "name": user})


@app.route("/cart/add", methods=["POST"])
def cart_add():
    """Add product and quantity to cart."""
    data = request.form if request.form else (request.get_json(silent=True) or {})
    try:
        product_id = int(data.get("product_id", ""))
        qty = int(data.get("qty", ""))
    except ValueError:
        return jsonify({"error": "product_id and qty must be integers"}), 400
    if product_id not in PRODUCTS:
        return jsonify({"error": "unknown product"}), 404
    if qty < 1:
        return jsonify({"error": "qty must be at least 1"}), 400
    CART.append({"product_id": product_id, "qty": qty})
    return jsonify({"ok": True, "items": len(CART), "total": cart_total()})


@app.route("/checkout", methods=["GET"])
def checkout():
    """Return checkout summary with total, average, and items."""
    total = cart_total()
    avg = total / len(CART) if CART else 0
    return jsonify({"total": total, "avg_item_value": avg, "items": list(CART)})


# Test-harness hook to reset in-memory cart state
@app.route("/__reset", methods=["POST"])
def reset_cart():
    """Reset in-memory cart state between test runs."""
    CART.clear()
    return jsonify({"ok": True})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5055))
    app.run(port=port, debug=False, threaded=True)

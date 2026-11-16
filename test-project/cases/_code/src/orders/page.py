"""Renders the orders board as one HTML page.

Every word a visitor reads comes from strings.json, and every value from an order is escaped.
"""
import html
import json
import os

from . import data

HERE = os.path.dirname(os.path.abspath(__file__))
ROW = ('        <tr><td>{id}</td><td>{customer}</td><td class="num">{items}</td>'
       '<td class="num">{total}</td></tr>')
EMPTY_ROW = '        <tr><td colspan="4" class="empty">{text}</td></tr>'


def strings() -> dict:
    with open(os.path.join(HERE, "strings.json"), encoding="utf-8") as fh:
        return json.load(fh)


def render(orders) -> str:
    text = strings()
    with open(os.path.join(HERE, "templates", "orders.html"), encoding="utf-8") as fh:
        page = fh.read()
    if orders:
        rows = "\n".join(ROW.format(id=order["id"], customer=html.escape(order["customer"]), items=order["items"],
                                    total=data.money(order["total_cents"])) for order in orders)
        summary = text["summary.total"].format(count=len(orders), total=data.money(data.total_cents(orders)),
                                               average=data.money(data.average_cents(orders)))
    else:
        rows = EMPTY_ROW.format(text=html.escape(text["table.empty"]))
        summary = ""
    values = {
        "title": html.escape(text["page.title"]),
        "col_id": html.escape(text["table.id"]),
        "col_customer": html.escape(text["table.customer"]),
        "col_items": html.escape(text["table.items"]),
        "col_total": html.escape(text["table.total"]),
        "rows": rows,
        "summary": html.escape(summary),
    }
    for key, value in values.items():
        page = page.replace("{{" + key + "}}", value)
    return page

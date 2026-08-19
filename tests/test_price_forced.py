"""Price is never an agent decision — it comes from the economics tables.

Rides and shops charge their subclass ceiling (max_ticket_price / max_item_price)
and staff carry their fixed salary. Whatever a proposal passes in is overwritten,
so there is nothing to validate, clamp, or bounce back to a specialist.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from coded_tools.propose_action import ProposeAction  # noqa: E402


def forced(**args):
    ProposeAction()._force_econ_price(args)
    return args.get("price")


def test_price_comes_from_economics_not_the_proposal():
    # carousel/red caps at 24, drink/yellow at 3, janitor/yellow salary 25.
    assert forced(type="ride", subtype="carousel", subclass="red") == 24
    assert forced(type="shop", subtype="drink", subclass="yellow") == 3
    assert forced(type="staff", subtype="janitor", subclass="yellow") == 25

    # A price supplied by a caller is overwritten, high or low — no negotiation.
    assert forced(type="ride", subtype="carousel", subclass="red", price=99) == 24
    assert forced(type="ride", subtype="carousel", subclass="red", price=1) == 24
    assert forced(type="shop", subtype="drink", subclass="yellow", price=50) == 3


def test_unresolvable_row_is_left_alone():
    """A typo'd subtype must not silently become some other tier's price.

    Those proposals are rejected by the type/required-field checks instead; the
    danger here would be inventing a plausible number for a nonexistent asset.
    """
    assert forced(type="ride", subtype="teleporter", subclass="red", price=7) == 7
    assert forced(type="ride", subclass="red", price=7) == 7          # no subtype
    assert forced(type="banana", subtype="carousel", subclass="red", price=7) == 7


def test_price_aliases_are_folded_in():
    """The obs names these `ticket_price`/`item_price`; the env action takes `price`.

    A proposal that echoes an alias back must not reach the env as an unknown arg.
    """
    from coded_tools.finance_gate import normalize_price_key

    for alias in ("ticket_price", "item_price"):
        args = {"type": "ride", alias: 9}
        normalize_price_key(args)
        assert args == {"type": "ride", "price": 9}, f"{alias} not folded into price"

    args = {"price": 5, "ticket_price": 9}
    normalize_price_key(args)
    assert args == {"price": 5}                      # alias dropped, not left behind

    args = {"type": "ride"}
    normalize_price_key(args)
    assert args == {"type": "ride"}
    normalize_price_key(None)                        # must not raise


if __name__ == "__main__":
    test_price_comes_from_economics_not_the_proposal()
    test_unresolvable_row_is_left_alone()
    test_price_aliases_are_folded_in()
    print("ok")

"""Authoritative quote estimates. Browser totals are never trusted."""
from decimal import Decimal, ROUND_HALF_UP


MEASUREMENT_FIELDS = (
    "window_count", "gutter_one", "gutter_one_half", "gutter_two", "gutter_three",
    "surface_area", "surface_length", "surface_width", "deck_area", "deck_railing",
)
QUOTE_FIELDS = MEASUREMENT_FIELDS + (
    "window_unknown", "gutter_unknown", "surface_unknown", "deck_unknown",
    "house_three_stories", "house_large", "house_roof", "deck_material",
    "deck_stairs", "deck_underside", "deck_access",
)
SERVICE_FIELDS = {
    "window-cleaning": ("window_count", "window_unknown"),
    "gutter-cleaning": ("gutter_one", "gutter_one_half", "gutter_two", "gutter_three", "gutter_unknown"),
    "pressure-washing": ("house_three_stories", "house_large", "house_roof"),
    "concrete-patio-cleaning": ("surface_area", "surface_length", "surface_width", "surface_unknown"),
    "deck-cleaning": ("deck_area", "deck_railing", "deck_material", "deck_stairs", "deck_underside", "deck_access", "deck_unknown"),
}
LABELS = {
    "window-cleaning": "Window cleaning", "gutter-cleaning": "Gutter cleaning",
    "pressure-washing": "House washing", "concrete-patio-cleaning": "Surface cleaning",
    "deck-cleaning": "Deck cleaning", "other": "Something else",
}


def money(value):
    return str(Decimal(value).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def estimate_quote(services, details):
    rows = []
    for service in services:
        amount, calculation, reasons = None, "", []
        def number(key):
            value = details.get(key)
            return Decimal(str(value)) if value not in (None, "") else None

        if service == "window-cleaning":
            count = number("window_count")
            if details.get("window_unknown") or not count:
                reasons.append("Window count to be confirmed; $100 visit + $10 per window, not a calculated total.")
            else:
                amount = 100 + count * 10
                calculation = f"$100 to come out + {count:g} windows × $10"
        elif service == "gutter-cleaning":
            values = [(number(key), rate) for key, rate in (
                ("gutter_one", Decimal("1")), ("gutter_one_half", Decimal("1.5")),
                ("gutter_two", Decimal("2")), ("gutter_three", Decimal("3")),
            )]
            if details.get("gutter_unknown") or not any(value for value, _ in values):
                reasons.append("Please measure for me. A $180 minimum applies; no total calculated yet.")
            else:
                raw = sum((value or 0) * rate for value, rate in values)
                amount = max(Decimal("180"), raw)
                calculation = " + ".join(f"{value:g} ft × ${rate:g}" for value, rate in values if value)
                calculation += "; $180 minimum applied once"
        elif service == "pressure-washing":
            answers = [details.get(key) for key in ("house_three_stories", "house_large", "house_roof")]
            if all(value == "no" for value in answers):
                amount, calculation = Decimal("400"), "Standard house wash flat rate"
            else:
                reasons.append("House height, size, or roof access needs individual review before pricing.")
        elif service == "concrete-patio-cleaning":
            area, length, width = number("surface_area"), number("surface_length"), number("surface_width")
            if details.get("surface_unknown"):
                area = None
            elif not area and length and width:
                area = length * width
            if area:
                amount, calculation = area * Decimal(".4"), f"{area:g} sq. ft. × $0.40"
            else:
                reasons.append("Surface measurements to be confirmed; $0.40 per square foot.")
        elif service == "deck-cleaning":
            area, railing = number("deck_area"), number("deck_railing")
            if details.get("deck_unknown") or not area or railing is None:
                reasons.append("Deck area and railing measurements to be confirmed; no complete deck estimate yet.")
            else:
                amount = area * Decimal(".5") + railing * 2
                calculation = f"{area:g} sq. ft. × $0.50 + {railing:g} railing ft × $2"
            if details.get("deck_material") not in ("wood", "composite"):
                reasons.append("Deck material needs review.")
            if details.get("deck_stairs"):
                reasons.append("Stairs need individual review and are NOT included in the displayed ballpark.")
            if details.get("deck_underside"):
                reasons.append("Underside is a separate project, NOT included. Please send photos for review.")
        else:
            reasons.append("Please describe the work; the team will review pricing.")
        rows.append({
            "service": service, "label": LABELS.get(service, service),
            "amount": money(amount) if amount is not None else None,
            "calculation": calculation, "status": "review" if reasons else "estimate",
            "reasons": reasons,
        })
    return {
        "services": rows,
        "estimated_subtotal": money(sum(Decimal(row["amount"]) for row in rows if row["amount"] is not None)),
        "complete": bool(rows) and all(row["status"] == "estimate" for row in rows),
    }


def estimate_lines(snapshot):
    lines = []
    for row in snapshot.get("services", []):
        amount = f"${row['amount']} ballpark estimate" if row["amount"] is not None else "Needs review — no calculated total"
        lines.append(f"{row['label']}: {amount}")
        if row["calculation"]:
            lines.append(f"  {row['calculation']}")
        lines.extend(f"  Review: {reason}" for reason in row["reasons"])
    lines.append("All counts, measurements, expectations, and exact prices require customer approval before work begins. No appointment has been booked.")
    return "\n".join(lines)

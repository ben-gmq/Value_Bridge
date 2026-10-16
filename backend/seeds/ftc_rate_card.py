"""The FTC default rate card (S6c-1): standard man-days per (FR_TYPE code, FR_COMPLEXITY code).

PLACEHOLDER VALUES — not yet confirmed by FTC. Every project is seeded from this at create_project, and
untouched cells show "FTC default, unconfirmed" until someone changes them (DR6c-P3). When FTC confirms
the card, change the numbers here and run the confirmed-defaults command (S6c-6), which updates only
cells nobody has changed. Keyed by code, never by id."""
from decimal import Decimal

_D = Decimal
COMPLEXITIES = ("SIMPLE", "MEDIUM", "COMPLEX", "VERY_COMPLEX")
_ROWS = {
    "FORM": ("2", "4", "8", "15"),
    "REPORT": ("2", "4", "8", "15"),
    "INTERFACE": ("3", "6", "12", "20"),
    "BATCH": ("2", "5", "10", "18"),
    # S11-5: unconfirmed placeholders at the interface figures, written as their own values (S11-5 review L2), so
    # confirming the interface row later never silently "confirms" migration days FTC has not given.
    "MIGRATION": ("3", "6", "12", "20"),
}
FTC_DEFAULT_RATE_CARD: dict[tuple[str, str], Decimal] = {
    (fr_type, cx): _D(days) for fr_type, values in _ROWS.items() for cx, days in zip(COMPLEXITIES, values)
}

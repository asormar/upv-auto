"""Shapes the weekly table for the web UI. Pure: no I/O, no framework.

The UPV table is a grid of days by time ranges. The UI draws one day at a
time, so this groups the parsed cells by day, orders both axes, and adds the
booking state the UI needs (which slots this config would try on Saturday).
"""

from __future__ import annotations

from dataclasses import dataclass

from upv_auto.domain.models import BookingTarget, GroupAvailability, GroupState

# Weekday order of the UPV table, in both languages it is served in.
_DAY_ORDER = {
    "lunes": 0, "dilluns": 0,
    "martes": 1, "dimarts": 1,
    "miercoles": 2, "miércoles": 2, "dimecres": 2,
    "jueves": 3, "dijous": 3,
    "viernes": 4, "divendres": 4,
    "sabado": 5, "sábado": 5, "dissabte": 5,
    "domingo": 6, "diumenge": 6,
}

UNKNOWN_DAY = "Sin día"


@dataclass(frozen=True)
class SlotView:
    code: str
    time: str
    state: str
    free_places: int | None
    queued: bool
    priority: int | None
    is_alternative: bool


@dataclass(frozen=True)
class DayView:
    name: str
    slots: tuple[SlotView, ...]


def _day_rank(name: str) -> int:
    return _DAY_ORDER.get(name.strip().lower(), 99)


def _time_rank(time: str | None) -> tuple[int, int]:
    if not time:
        return (99, 99)
    start = time.split("-")[0].strip()
    try:
        hours, minutes = start.split(":")
        return (int(hours), int(minutes))
    except ValueError:
        return (99, 99)


def _queue_position(code: str, bookings: list[BookingTarget]) -> tuple[int, bool] | None:
    """Where `code` sits in the configured queue: (booking number, is alternative)."""
    for index, target in enumerate(bookings, start=1):
        for option_index, slot in enumerate(target.options):
            if slot.group_code == code:
                return index, option_index > 0
    return None


def build_days(
    groups: dict[str, GroupAvailability], bookings: list[BookingTarget]
) -> list[DayView]:
    """Group the parsed table into ordered days of ordered slots."""
    by_day: dict[str, list[SlotView]] = {}
    for code in sorted(groups):
        group = groups[code]
        day = group.day or UNKNOWN_DAY
        position = _queue_position(code, bookings)
        by_day.setdefault(day, []).append(
            SlotView(
                code=code,
                time=group.time or "",
                state=group.state.name,
                free_places=group.free_places,
                queued=position is not None,
                priority=position[0] if position else None,
                is_alternative=position[1] if position else False,
            )
        )

    days = []
    for day in sorted(by_day, key=lambda name: (_day_rank(name), name)):
        slots = sorted(by_day[day], key=lambda slot: (_time_rank(slot.time), slot.code))
        days.append(DayView(name=day, slots=tuple(slots)))
    return days


def count_queued(bookings: list[BookingTarget]) -> int:
    """How many places next Saturday's run would secure: one per booking.

    Alternatives do not add up: within a booking only one of them is taken.
    """
    return len(bookings)


def count_enrolled_now(groups: dict[str, GroupAvailability]) -> int:
    """How many groups the table already shows as enrolled.

    That is the *current* week — the UPV page has no week marker — so it never
    counts towards what Saturday will book.
    """
    return sum(1 for group in groups.values() if group.state is GroupState.ENROLLED)

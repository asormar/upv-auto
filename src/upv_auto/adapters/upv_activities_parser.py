"""Parses the UPV weekly activity table HTML into group availabilities.

Pure: stdlib only (`html.parser`), no I/O, no third-party dependencies. The
source pages are old, loosely-structured HTML (see
`tests/fixtures/activities_musculacion.html`), so parsing is deliberately
tolerant: it scans every `<td>` cell in the document, and only cells whose
first line matches a group code (`[A-Z]{3}\\d{3}`, e.g. `MUS074`) are kept.
This means it also safely ignores the unrelated "Grupos Inscritos" summary
table, whose group cells look like "MUSCULACIÓN 074" (a space, not a code).
"""

from __future__ import annotations

import re
from html.parser import HTMLParser

from upv_auto.domain.models import GroupAvailability, GroupState

_CODE_RE = re.compile(r"^([A-Z]{3}\d{3})")
_FREE_RE = re.compile(r"^(\d+)\s+libres", re.IGNORECASE)


class _ActivityTableParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.groups: dict[str, GroupAvailability] = {}
        self._in_td = False
        self._href: str | None = None
        self._text_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "td":
            self._in_td = True
            self._href = None
            self._text_parts = []
        elif tag == "a" and self._in_td:
            href = dict(attrs).get("href")
            if href:
                self._href = href
        elif tag == "br" and self._in_td:
            self._text_parts.append("\n")

    def handle_data(self, data: str) -> None:
        if self._in_td:
            self._text_parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "td" and self._in_td:
            self._in_td = False
            self._finish_cell()

    def _finish_cell(self) -> None:
        lines = [line.strip() for line in "".join(self._text_parts).split("\n")]
        lines = [line for line in lines if line]
        if not lines:
            return

        match = _CODE_RE.match(lines[0])
        if not match:
            return
        code = match.group(1)
        rest = lines[1:]

        free_places: int | None = None
        for line in rest:
            free_match = _FREE_RE.match(line)
            if free_match:
                free_places = int(free_match.group(1))
                break

        if any("inscrito" in line.lower() for line in rest):
            state = GroupState.ENROLLED
            free_places = None
        elif any("completo" in line.lower() for line in rest):
            state = GroupState.FULL
            free_places = None
        elif self._href:
            state = GroupState.BOOKABLE
        else:
            state = GroupState.UNAVAILABLE

        booking_path = self._href if state is GroupState.BOOKABLE else None
        self.groups[code] = GroupAvailability(
            code=code, state=state, free_places=free_places, booking_path=booking_path
        )


def parse_groups(html: str) -> dict[str, GroupAvailability]:
    """Parse a UPV activity table page into `{group_code: GroupAvailability}`."""
    parser = _ActivityTableParser()
    parser.feed(html)
    parser.close()
    return parser.groups

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
_TIME_RE = re.compile(r"(\d{1,2}:\d{2}\s*[-–]\s*\d{1,2}:\d{2})")
_SCHEDULE_HEADER = "horario"


class _ActivityTableParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.groups: dict[str, GroupAvailability] = {}
        self._in_td = False
        self._in_th = False
        self._href: str | None = None
        self._text_parts: list[str] = []
        # Position within the weekly grid: column headers give the day, the
        # row's first cell gives the time.
        self._days: list[str] = []
        self._header_parts: list[str] = []
        self._column = 0
        self._row_time: str | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "tr":
            self._column = 0
            self._row_time = None
            self._header_parts = []
        elif tag == "th":
            self._in_th = True
            self._text_parts = []
        elif tag == "td":
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
        if self._in_td or self._in_th:
            self._text_parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "th" and self._in_th:
            self._in_th = False
            self._header_parts.append("".join(self._text_parts).strip())
        elif tag == "td" and self._in_td:
            self._in_td = False
            self._finish_cell()
            self._column += 1
        elif tag == "tr":
            self._finish_header_row()

    def _finish_header_row(self) -> None:
        """Remember the weekday columns of the weekly table's header row.

        Only the schedule table qualifies: its header reads "Horario", then one
        column per weekday. Other tables on the page (the enrolled-groups
        summary) are left alone.
        """
        headers = [h for h in self._header_parts if h]
        self._header_parts = []
        if len(headers) > 1 and headers[0].lower().startswith(_SCHEDULE_HEADER):
            self._days = headers[1:]

    def _finish_cell(self) -> None:
        lines = [line.strip() for line in "".join(self._text_parts).split("\n")]
        lines = [line for line in lines if line]
        if not lines:
            return

        match = _CODE_RE.match(lines[0])
        if not match:
            # A row's leading cell carries its time range, e.g.
            # "12:30-13:30 Sala Musculación".
            if self._column == 0:
                time_match = _TIME_RE.search(lines[0])
                if time_match:
                    self._row_time = time_match.group(1).replace(" ", "")
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
        day = None
        if self._days and 1 <= self._column <= len(self._days):
            day = self._days[self._column - 1]

        self.groups[code] = GroupAvailability(
            code=code,
            state=state,
            free_places=free_places,
            booking_path=booking_path,
            day=day,
            time=self._row_time,
        )


def parse_groups(html: str) -> dict[str, GroupAvailability]:
    """Parse a UPV activity table page into `{group_code: GroupAvailability}`."""
    parser = _ActivityTableParser()
    parser.feed(html)
    parser.close()
    return parser.groups

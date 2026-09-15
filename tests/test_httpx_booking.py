from __future__ import annotations

import httpx
import pytest

from upv_auto.adapters.httpx_booking import HttpxBookingClient
from upv_auto.domain.models import Activity, BookingOutcome, Session, Slot

ACTIVITY = Activity(campus="V", tipoact="6894", codacti="21948", name="MUSCULACION")
BASE_URL = "https://intranet.upv.es/pls/soalu/"

TABLE_URL = (
    f"{BASE_URL}sic_depact.HSemActividades?p_campus=V&p_tipoact=6894&p_codacti=21948"
    "&p_vista=intranet&p_idioma=c&p_solo_matricula_sn=&p_anc=filtro_actividad"
)
BOOKING_PATH = (
    "sic_depact.HSemActMatri?p_campus=V&p_codacti=21948&p_codgrupo_mat=ABC123"
    "&p_vista=intranet&p_tipoact=6894&p_idioma=c"
)
BOOKING_URL = BASE_URL + BOOKING_PATH


def _cell(code: str, *, state: str, extra: str = "", href: str | None = None) -> str:
    inner = f"{code}<br>{extra}" if extra else code
    if href:
        return f'<td><a href="{href}">{inner}</a></td>'
    cls = {"bookable": ' class="IAOL_BGColorGrpLibre"', "enrolled": ' class="IAOL_BGColorGrpInscrito"'}.get(
        state, ""
    )
    return f"<td{cls}>{inner}</td>"


def table_page(cell_html: str) -> str:
    return f"<html><body><table><tbody><tr>{cell_html}</tr></tbody></table></body></html>"


def bookable_table() -> str:
    return table_page(_cell("MUS074", state="bookable", extra="Solo Socios<br>5 libres", href=BOOKING_PATH))


def enrolled_table() -> str:
    return table_page(_cell("MUS074", state="enrolled", extra="Ya inscrito"))


def full_table() -> str:
    return table_page(_cell("MUS074", state="full", extra="Solo Socios<br>Completo"))


def unavailable_table() -> str:
    return table_page(f'<td class="IAOL_BGColorGrpLibre">MUS074<br>Solo Socios<br>1 libres</td>')


def make_session() -> Session:
    return Session(cookies=[], user_agent="test-agent")


def make_client(handler, *, base_url: str = BASE_URL) -> HttpxBookingClient:
    transport = httpx.MockTransport(handler)
    return HttpxBookingClient(ACTIVITY, base_url=base_url, transport=transport)


def test_bookable_group_is_booked_by_following_the_scraped_link():
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        if str(request.url) == TABLE_URL:
            return httpx.Response(200, text=bookable_table())
        if str(request.url) == BOOKING_URL:
            return httpx.Response(200, text=enrolled_table())
        raise AssertionError(f"unexpected request: {request.url}")

    client = make_client(handler)
    result = client.book(make_session(), Slot(group_code="MUS074"))

    assert result.outcome is BookingOutcome.BOOKED
    assert calls == [TABLE_URL, BOOKING_URL]


def test_already_enrolled_is_reported_as_such_not_as_booked():
    # The table may still show the previous week, so a pre-existing enrolment
    # is not proof that next week's place was secured.
    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == TABLE_URL
        return httpx.Response(200, text=enrolled_table())

    client = make_client(handler)
    result = client.book(make_session(), Slot(group_code="MUS074"))

    assert result.outcome is BookingOutcome.ALREADY_ENROLLED


def test_full_group_is_taken():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=full_table())

    client = make_client(handler)
    result = client.book(make_session(), Slot(group_code="MUS074"))

    assert result.outcome is BookingOutcome.TAKEN


def test_unavailable_group_is_not_open_yet():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=unavailable_table())

    client = make_client(handler)
    result = client.book(make_session(), Slot(group_code="MUS074"))

    assert result.outcome is BookingOutcome.NOT_OPEN_YET


def test_missing_group_is_not_open_yet():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=table_page(""))

    client = make_client(handler)
    result = client.book(make_session(), Slot(group_code="MUS074"))

    assert result.outcome is BookingOutcome.NOT_OPEN_YET


def test_cas_redirect_means_session_expired():
    def handler(request: httpx.Request) -> httpx.Response:
        if str(request.url) == TABLE_URL:
            return httpx.Response(302, headers={"Location": "https://cas.upv.es/cas/login"})
        return httpx.Response(200, text="<html>CAS login</html>")

    client = make_client(handler)
    result = client.book(make_session(), Slot(group_code="MUS074"))

    assert result.outcome is BookingOutcome.SESSION_EXPIRED


def test_5xx_response_is_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, text="Service Unavailable")

    client = make_client(handler)
    result = client.book(make_session(), Slot(group_code="MUS074"))

    assert result.outcome is BookingOutcome.ERROR


def test_network_error_is_mapped_to_error_not_raised():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("boom", request=request)

    client = make_client(handler)
    result = client.book(make_session(), Slot(group_code="MUS074"))

    assert result.outcome is BookingOutcome.ERROR


def test_booking_link_becomes_full_during_the_attempt_is_taken():
    def handler(request: httpx.Request) -> httpx.Response:
        if str(request.url) == TABLE_URL:
            return httpx.Response(200, text=bookable_table())
        return httpx.Response(200, text=full_table())

    client = make_client(handler)
    result = client.book(make_session(), Slot(group_code="MUS074"))

    assert result.outcome is BookingOutcome.TAKEN

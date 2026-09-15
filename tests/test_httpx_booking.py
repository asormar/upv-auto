from __future__ import annotations

from unittest.mock import patch

import httpx

from upv_auto.adapters.httpx_booking import HttpxActivityTableClient
from upv_auto.adapters.httpx_session import build_client as real_build_client
from upv_auto.domain.models import Activity, BookingOutcome, GroupAvailability, GroupState, Session

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


def make_session(user_agent: str = "test-agent") -> Session:
    return Session(cookies=[], user_agent=user_agent)


def make_client(handler, *, base_url: str = BASE_URL) -> HttpxActivityTableClient:
    transport = httpx.MockTransport(handler)
    return HttpxActivityTableClient(ACTIVITY, base_url=base_url, transport=transport)


def test_fetch_groups_parses_the_table():
    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == TABLE_URL
        return httpx.Response(200, text=bookable_table())

    client = make_client(handler)
    snapshot = client.fetch_groups(make_session())

    assert snapshot.ok
    assert snapshot.groups["MUS074"].state is GroupState.BOOKABLE
    assert snapshot.groups["MUS074"].booking_path == BOOKING_PATH


def test_follow_booking_returns_the_refreshed_table_snapshot():
    session = make_session()

    def handler(request: httpx.Request) -> httpx.Response:
        if str(request.url) == TABLE_URL:
            return httpx.Response(200, text=bookable_table())
        assert str(request.url) == BOOKING_URL
        return httpx.Response(200, text=enrolled_table())

    client = make_client(handler)
    snapshot = client.fetch_groups(session)
    group = snapshot.groups["MUS074"]

    after = client.follow_booking(session, group)

    assert after.ok
    assert after.groups["MUS074"].state is GroupState.ENROLLED


def test_follow_booking_link_became_full_in_the_meantime():
    session = make_session()

    def handler(request: httpx.Request) -> httpx.Response:
        if str(request.url) == TABLE_URL:
            return httpx.Response(200, text=bookable_table())
        return httpx.Response(200, text=full_table())

    client = make_client(handler)
    snapshot = client.fetch_groups(session)
    group = snapshot.groups["MUS074"]

    after = client.follow_booking(session, group)

    assert after.ok
    assert after.groups["MUS074"].state is GroupState.FULL


def test_follow_booking_without_a_link_is_error():
    client = make_client(lambda request: httpx.Response(200, text=""))
    group = GroupAvailability(code="MUS074", state=GroupState.BOOKABLE, booking_path=None)

    snapshot = client.follow_booking(make_session(), group)

    assert snapshot.failure is BookingOutcome.ERROR


def test_cas_redirect_means_session_expired():
    def handler(request: httpx.Request) -> httpx.Response:
        if str(request.url) == TABLE_URL:
            return httpx.Response(302, headers={"Location": "https://cas.upv.es/cas/login"})
        return httpx.Response(200, text="<html>CAS login</html>")

    client = make_client(handler)
    snapshot = client.fetch_groups(make_session())

    assert snapshot.failure is BookingOutcome.SESSION_EXPIRED


def test_5xx_response_is_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, text="Service Unavailable")

    client = make_client(handler)
    snapshot = client.fetch_groups(make_session())

    assert snapshot.failure is BookingOutcome.ERROR


def test_4xx_response_is_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, text="Not Found")

    client = make_client(handler)
    snapshot = client.fetch_groups(make_session())

    assert snapshot.failure is BookingOutcome.ERROR


def test_network_error_is_mapped_to_error_not_raised():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("boom", request=request)

    client = make_client(handler)
    snapshot = client.fetch_groups(make_session())

    assert snapshot.failure is BookingOutcome.ERROR


def test_client_is_reused_for_the_same_session_and_rebuilt_for_a_new_one():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=bookable_table())

    transport = httpx.MockTransport(handler)
    client = HttpxActivityTableClient(ACTIVITY, base_url=BASE_URL, transport=transport)
    session_a = make_session("agent-a")
    session_b = make_session("agent-b")

    with patch("upv_auto.adapters.httpx_booking.build_client", wraps=real_build_client) as spy:
        client.fetch_groups(session_a)
        client.fetch_groups(session_a)  # same session -> client reused, no rebuild
        client.fetch_groups(session_b)  # different session -> client rebuilt

    assert spy.call_count == 2
    client.close()


def test_close_and_context_manager_release_the_client():
    transport = httpx.MockTransport(lambda request: httpx.Response(200, text=bookable_table()))
    with HttpxActivityTableClient(ACTIVITY, base_url=BASE_URL, transport=transport) as client:
        client.fetch_groups(make_session())
        assert client._client is not None
    assert client._client is None

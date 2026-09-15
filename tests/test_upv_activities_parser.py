from __future__ import annotations

from pathlib import Path

from upv_auto.adapters.upv_activities_parser import parse_groups
from upv_auto.domain.models import GroupState

FIXTURE = Path(__file__).parent / "fixtures" / "activities_musculacion.html"


def load_fixture_html() -> str:
    # The fixture is stored as UTF-8 in this repo; real UPV responses are
    # ISO-8859-15 (decoded by the httpx adapter before parsing). The parser
    # itself works on already-decoded text, so it must not depend on the
    # accented characters coming through intact either way.
    return FIXTURE.read_text(encoding="utf-8")


def test_parses_bookable_group_with_link_and_free_places():
    groups = parse_groups(load_fixture_html())

    mus075 = groups["MUS075"]
    assert mus075.state is GroupState.BOOKABLE
    assert mus075.free_places == 20
    assert mus075.booking_path is not None
    assert "p_codgrupo_mat=47FB323BBC9FB2" in mus075.booking_path


def test_parses_unavailable_group_with_free_places_but_no_link():
    groups = parse_groups(load_fixture_html())

    mus016 = groups["MUS016"]
    assert mus016.state is GroupState.UNAVAILABLE
    assert mus016.free_places == 1
    assert mus016.booking_path is None


def test_parses_full_group():
    groups = parse_groups(load_fixture_html())

    mus001 = groups["MUS001"]
    assert mus001.state is GroupState.FULL
    assert mus001.free_places is None
    assert mus001.booking_path is None


def test_parses_enrolled_group():
    groups = parse_groups(load_fixture_html())

    mus074 = groups["MUS074"]
    assert mus074.state is GroupState.ENROLLED
    assert mus074.free_places is None
    assert mus074.booking_path is None


def test_unknown_group_code_is_absent():
    groups = parse_groups(load_fixture_html())

    assert "ZZZ999" not in groups


def test_unescapes_html_entities_in_booking_link():
    html = (
        '<table><tbody><tr><td>'
        '<a href="sic_depact.HSemActMatri?p_campus=V&amp;p_codacti=21948'
        '&amp;p_codgrupo_mat=ABCDEF&amp;p_vista=intranet">MUS999<br>Solo Socios<br>5 libres</a>'
        '</td></tr></tbody></table>'
    )

    groups = parse_groups(html)

    assert groups["MUS999"].booking_path == (
        "sic_depact.HSemActMatri?p_campus=V&p_codacti=21948&p_codgrupo_mat=ABCDEF&p_vista=intranet"
    )


def test_empty_cell_yields_no_group():
    html = "<table><tbody><tr><td> </td></tr></tbody></table>"

    groups = parse_groups(html)

    assert groups == {}


def test_grupos_inscritos_summary_row_is_not_mistaken_for_a_group_cell():
    html = "<table><tbody><tr><td>MUSCULACIÓN 021</td></tr></tbody></table>"

    groups = parse_groups(html)

    assert groups == {}

"""URL builders for UPV sports activity pages. Pure functions, no I/O."""

from __future__ import annotations

from upv_auto.domain.models import Activity

DEFAULT_BASE_URL = "https://intranet.upv.es/pls/soalu/"
CAS_HOST = "cas.upv.es"


def activity_table_url(activity: Activity, *, base_url: str = DEFAULT_BASE_URL) -> str:
    """URL of the weekly activity table (groups per weekday) for `activity`."""
    return (
        f"{base_url}sic_depact.HSemActividades?p_campus={activity.campus}"
        f"&p_tipoact={activity.tipoact}&p_codacti={activity.codacti}&p_vista=intranet"
        "&p_idioma=c&p_solo_matricula_sn=&p_anc=filtro_actividad"
    )

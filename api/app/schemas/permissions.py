# api/app/schemas/permissions.py
"""Request and response bodies of the permission endpoints: radar views (lists of radar codes) and tools (yes/no)."""

from typing import Annotated, List, Optional

from pydantic import BaseModel, Field, StringConstraints, model_validator

# A radar code (letters, digits, "_" or "-", like the radars table) or "*" for every radar.
RadarResource = Annotated[str, StringConstraints(min_length=1, max_length=16, pattern=r"^(\*|[A-Za-z0-9_-]+)$")]


class ToolsState(BaseModel):
    """The tools of a user, an institution or an invitation. Today only the storm tracking tool."""

    tracking: bool = False


class ToolsUpdate(BaseModel):
    """Tools to change; a tool left out (None) is not changed."""

    tracking: Optional[bool] = None


class RadarViewsUpdate(BaseModel):
    """PUT body of the permission endpoints. Both parts are optional and what is not sent is not changed, but at least
    one must be there (an empty body would be a PUT that does nothing: 422). Both are saved in one transaction."""

    radar_detail_view: Optional[List[RadarResource]] = Field(None, max_length=500)
    tools: Optional[ToolsUpdate] = None

    @model_validator(mode="after")
    def _something_to_change(self) -> "RadarViewsUpdate":
        if self.radar_detail_view is None and self.tools is None:
            raise ValueError("Mandá las vistas, las herramientas o las dos")
        return self


class MyPermissionsResponse(BaseModel):
    """What the logged-in user may use, already resolved: real radar codes (never "*") and its tools."""

    radar_detail_views: List[str]
    tools: ToolsState

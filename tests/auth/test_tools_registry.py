# tests/auth/test_tools_registry.py
"""Guard for adding a tool: every place that has to know about a tool agrees with the list in permissions.py.

The list is `permissions.TOOLS` ({name: permission action}). Adding a tool means touching several files (see "How to
add a tool" in docs/OPERATIONS.md); if one is forgotten, one of these tests fails and says which.
"""

import pytest

from api.app.auth import permissions as perms
from api.app.schemas.permissions import ToolsState, ToolsUpdate
from radar_db.models import PERMISSION_ACTIONS, Permission

from .conftest import login

TOOL_NAMES = sorted(perms.TOOLS)


def test_the_schemas_have_one_field_per_tool():
    assert sorted(ToolsState.model_fields) == TOOL_NAMES
    assert sorted(ToolsUpdate.model_fields) == TOOL_NAMES


def test_every_tool_action_is_a_known_permission_action():
    for action in perms.TOOLS.values():
        assert action.startswith("tool.")
        assert action in PERMISSION_ACTIONS


def test_the_database_constraint_lists_every_action():
    constraint = next(c for c in Permission.__table__.constraints if c.name == "ck_permissions_action")
    for action in PERMISSION_ACTIONS:
        assert f"'{action}'" in str(constraint.sqltext)


@pytest.mark.parametrize("tool", TOOL_NAMES)
def test_each_tool_can_be_given_and_taken_and_is_stored_in_the_database(tool, make_user, test_db_session):
    admin = make_user(username="boss", role="admin")
    user = make_user()
    assert perms.set_user_tools(test_db_session, user, {tool: True}, admin)[tool] is True
    assert perms.stored_tool(user, perms.TOOLS[tool]) is True
    assert perms.set_user_tools(test_db_session, user, {tool: False}, admin)[tool] is False


@pytest.mark.parametrize("tool", TOOL_NAMES)
def test_the_session_probe_accepts_each_tool(tool, app_client, make_user):
    make_user(username="boss", role="admin")
    login(app_client, "boss")
    assert app_client.get("/api/v1/auth/check", params={"tool": tool}).status_code == 204


def test_the_session_probe_refuses_an_unknown_tool(app_client, make_user):
    make_user(username="boss", role="admin")
    login(app_client, "boss")
    assert app_client.get("/api/v1/auth/check", params={"tool": "nope"}).status_code == 422

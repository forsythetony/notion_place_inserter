"""Unit tests for GET /management/* (dashboard list) routes."""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from app.domain.connectors import ConnectorInstance
from app.domain.jobs import JobDefinition, PipelineDefinition, StageDefinition, StepInstance, StepTemplate
from app.domain.limits import AppLimits
from app.domain.targets import DataTarget
from app.domain.triggers import TriggerDefinition
from app.main import app
from app.services.supabase_auth_repository import USER_TYPE_STANDARD
from app.services.validation_service import JobGraph


@pytest.fixture
def client():
    return TestClient(app)


def _mock_user(id_: str, email: str | None = "user@example.com"):
    u = MagicMock()
    u.id = id_
    u.email = email
    return u


def _mock_user_response(user):
    r = MagicMock()
    r.user = user
    return r


def _setup_auth(
    client,
    user_id="550e8400-e29b-41d4-a716-446655440000",
    email="user@example.com",
):
    """Set app.state so require_managed_auth passes."""
    mock_supabase = MagicMock()
    mock_supabase.auth.get_user = AsyncMock(
        return_value=_mock_user_response(_mock_user(user_id, email))
    )
    mock_auth_repo = MagicMock()
    mock_auth_repo.get_profile = AsyncMock(
        return_value={
            "user_id": user_id,
            "user_type": USER_TYPE_STANDARD,
        }
    )
    app.state.supabase_client = mock_supabase
    app.state.supabase_auth_repository = mock_auth_repo
    return user_id


def test_management_pipelines_401_without_auth(client):
    """GET /management/pipelines without Authorization returns 401."""
    resp = client.get("/management/pipelines")
    assert resp.status_code == 401
    assert resp.json()["detail"] == "Unauthorized"


def test_management_pipelines_401_malformed_bearer(client):
    """GET /management/pipelines with non-Bearer Authorization returns 401."""
    resp = client.get(
        "/management/pipelines",
        headers={"Authorization": "Basic foo:bar"},
    )
    assert resp.status_code == 401


def test_management_pipelines_200_list_shape(client):
    """GET /management/pipelines with valid auth returns items list."""
    user_id = _setup_auth(client)
    mock_job_repo = MagicMock()
    mock_job_repo.list_by_owner = AsyncMock(return_value=[
        JobDefinition(
            id="job-1",
            owner_user_id=user_id,
            display_name="Notion Place Inserter",
            target_id="tgt1",
            status="active",
            stage_ids=["s1"],
            updated_at=datetime(2026, 3, 15, 12, 0, 0),
        ),
    ])
    app.state.job_repository = mock_job_repo
    mock_link_repo = MagicMock()
    mock_link_repo.list_trigger_ids_for_job = AsyncMock(return_value=[])
    app.state.trigger_job_link_repository = mock_link_repo

    resp = client.get(
        "/management/pipelines",
        headers={"Authorization": "Bearer valid-jwt"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "items" in data
    assert len(data["items"]) == 1
    item = data["items"][0]
    assert item["id"] == "job-1"
    assert item["display_name"] == "Notion Place Inserter"
    assert item["status"] == "active"
    assert item["trigger_name"] is None
    assert item.get("trigger_display_name") is None
    assert "2026-03-15" in (item["updated_at"] or "")
    mock_job_repo.list_by_owner.assert_awaited_once_with(user_id)
    mock_link_repo.list_trigger_ids_for_job.assert_awaited_once_with("job-1", user_id)


def test_management_pipelines_200_list_includes_trigger_name_when_linked(client):
    """GET /management/pipelines includes trigger_name and trigger_display_name from linked trigger."""
    user_id = _setup_auth(client)
    mock_job_repo = MagicMock()
    mock_job_repo.list_by_owner = AsyncMock(return_value=[
        JobDefinition(
            id="job-1",
            owner_user_id=user_id,
            display_name="My Job",
            target_id="tgt1",
            status="active",
            stage_ids=["s1"],
            updated_at=None,
        ),
    ])
    app.state.job_repository = mock_job_repo
    mock_link_repo = MagicMock()
    mock_link_repo.list_trigger_ids_for_job = AsyncMock(return_value=["on_place_save"])
    app.state.trigger_job_link_repository = mock_link_repo
    mock_trigger_repo = MagicMock()
    mock_trigger_repo.get_by_id = AsyncMock(
        return_value=TriggerDefinition(
            id="on_place_save",
            owner_user_id=user_id,
            trigger_type="http",
            display_name="On place save",
            path="/locations",
            method="POST",
            request_body_schema={},
            status="active",
            auth_mode="bearer",
            secret_value="x",
        )
    )
    app.state.trigger_repository = mock_trigger_repo

    resp = client.get(
        "/management/pipelines",
        headers={"Authorization": "Bearer valid-jwt"},
    )
    assert resp.status_code == 200
    item = resp.json()["items"][0]
    assert item["trigger_name"] == "on_place_save"
    assert item["trigger_display_name"] == "On place save"
    mock_trigger_repo.get_by_id.assert_awaited_once_with("on_place_save", user_id)


def test_management_reprovision_starter_401_without_auth(client):
    """POST /management/bootstrap/reprovision-starter without auth returns 401."""
    resp = client.post("/management/bootstrap/reprovision-starter")
    assert resp.status_code == 401


def test_management_reprovision_starter_200_calls_bootstrap_service(client):
    """POST reprovision-starter invokes reprovision_owner_starter_definitions for the auth user."""
    user_id = _setup_auth(client)
    prev = getattr(app.state, "bootstrap_provisioning_service", None)
    try:
        mock_svc = MagicMock()
        mock_svc.reprovision_owner_starter_definitions = AsyncMock()
        app.state.bootstrap_provisioning_service = mock_svc
        resp = client.post(
            "/management/bootstrap/reprovision-starter",
            headers={"Authorization": "Bearer valid-jwt"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["job_id"] == "job_notion_place_inserter"
        mock_svc.reprovision_owner_starter_definitions.assert_awaited_once_with(user_id)
    finally:
        app.state.bootstrap_provisioning_service = prev


def test_management_reprovision_starter_503_when_bootstrap_disabled(client):
    """When bootstrap service is unset, reprovision returns 503."""
    user_id = _setup_auth(client)
    prev = getattr(app.state, "bootstrap_provisioning_service", None)
    try:
        app.state.bootstrap_provisioning_service = None
        resp = client.post(
            "/management/bootstrap/reprovision-starter",
            headers={"Authorization": "Bearer valid-jwt"},
        )
        assert resp.status_code == 503
        assert "ENABLE_BOOTSTRAP_PROVISIONING" in (resp.json().get("detail") or "")
    finally:
        app.state.bootstrap_provisioning_service = prev


def test_create_places_insertion_from_template_403_wrong_email(client):
    """POST create-places-insertion-from-template returns 403 when email is not allowlisted."""
    _setup_auth(client, email="other@example.com")
    resp = client.post(
        "/management/bootstrap/create-places-insertion-from-template",
        headers={"Authorization": "Bearer valid-jwt"},
    )
    assert resp.status_code == 403
    assert resp.json().get("code") == "PLACES_TEMPLATE_FORBIDDEN"


def test_create_places_insertion_from_template_200_created(client):
    """Allowlisted email provisions cloned job graph and trigger."""
    from app.routes.management import (
        PLACES_INSERTION_TEMPLATE_JOB_DISPLAY_NAME,
        PLACES_INSERTION_TEMPLATE_TRIGGER_PATH,
    )

    user_id = _setup_auth(client, email="forsythetony@gmail.com")

    mock_job_repo = MagicMock()
    mock_job_repo.list_by_owner = AsyncMock(return_value=[])
    mock_job_repo.save_job_graph = AsyncMock()
    app.state.job_repository = mock_job_repo

    mock_target_repo = MagicMock()
    mock_target_repo.get_by_id = AsyncMock(
        return_value=DataTarget(
            id="target_places_to_visit",
            owner_user_id=user_id,
            target_template_id="notion_database",
            connector_instance_id="connector_instance_notion_default",
            display_name="Places to Visit",
            external_target_id="ext",
            status="active",
        )
    )
    app.state.target_repository = mock_target_repo

    mock_notion = MagicMock()
    mock_notion.get_access_token = AsyncMock(return_value="notion-token")
    app.state.notion_oauth_service = mock_notion

    mock_schema = MagicMock()
    mock_schema.sync_for_target = AsyncMock()
    app.state.schema_sync_service = mock_schema

    mock_trigger_repo = MagicMock()
    mock_trigger_repo.get_by_path = AsyncMock(return_value=None)
    mock_trigger_repo.save = AsyncMock()
    app.state.trigger_repository = mock_trigger_repo

    mock_link = MagicMock()
    mock_link.attach = AsyncMock()
    app.state.trigger_job_link_repository = mock_link

    resp = client.post(
        "/management/bootstrap/create-places-insertion-from-template",
        headers={"Authorization": "Bearer valid-jwt"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "created"
    assert data["target_id"] == "target_places_to_visit"
    assert data["trigger_path"] == PLACES_INSERTION_TEMPLATE_TRIGGER_PATH
    assert data["target_display_name"] == "Places to Visit"
    mock_job_repo.save_job_graph.assert_awaited_once()
    mock_link.attach.assert_awaited_once()
    saved_graph = mock_job_repo.save_job_graph.await_args[0][0]
    assert saved_graph.job.display_name == PLACES_INSERTION_TEMPLATE_JOB_DISPLAY_NAME
    assert saved_graph.job.target_id == "target_places_to_visit"
    assert any(s.id.startswith(saved_graph.job.id + "_stage_research") for s in saved_graph.stages)


def test_management_step_templates_401_without_auth(client):
    """GET /management/step-templates without Authorization returns 401."""
    resp = client.get("/management/step-templates")
    assert resp.status_code == 401


def test_management_step_templates_200_list_shape(client):
    """GET /management/step-templates with valid auth returns items list with full metadata."""
    _setup_auth(client)
    mock_step_template_repo = MagicMock()
    mock_step_template_repo.list_all = AsyncMock(return_value=[
        StepTemplate(
            id="step_template_property_set",
            slug="property-set",
            display_name="Property Set",
            step_kind="transform",
            description="Set a property on the target",
            input_contract={"fields": {"value": {"type": "any"}}},
            output_contract={},
            config_schema={"schema_property_id": {"type": "string"}},
            runtime_binding="property_set",
            category="transform",
            status="active",
        ),
    ])
    app.state.step_template_repository = mock_step_template_repo

    resp = client.get(
        "/management/step-templates",
        headers={"Authorization": "Bearer valid-jwt"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "items" in data
    assert len(data["items"]) == 1
    item = data["items"][0]
    assert item["id"] == "step_template_property_set"
    assert item["display_name"] == "Property Set"
    assert item["category"] == "transform"
    assert item["status"] == "active"
    assert "description" in item
    assert "input_contract" in item
    assert "output_contract" in item
    assert "config_schema" in item
    assert item["config_schema"]["schema_property_id"]["type"] == "string"
    mock_step_template_repo.list_all.assert_awaited_once()


def test_management_step_template_detail_200(client):
    """GET /management/step-templates/{id} with valid auth returns full template metadata."""
    _setup_auth(client)
    mock_step_template_repo = MagicMock()
    mock_step_template_repo.get_by_id = AsyncMock(return_value=StepTemplate(
        id="step_template_ai_constrain_values_claude",
        slug="ai_constrain_values_claude",
        display_name="AI Constrain Values (Claude)",
        step_kind="ai_constrain_values",
        description="Select values from allowed list",
        input_contract={"fields": {"source_value": {"type": "any"}}},
        output_contract={"fields": {"selected_values": {"type": "array"}}},
        config_schema={
            "allowable_values_source": {"type": "object"},
            "max_output_values": {"type": "integer"},
        },
        runtime_binding="claude_constrain_values",
        category="transform",
        status="active",
    ))
    app.state.step_template_repository = mock_step_template_repo

    resp = client.get(
        "/management/step-templates/step_template_ai_constrain_values_claude",
        headers={"Authorization": "Bearer valid-jwt"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == "step_template_ai_constrain_values_claude"
    assert data["display_name"] == "AI Constrain Values (Claude)"
    assert data["step_kind"] == "ai_constrain_values"
    assert "input_contract" in data
    assert "output_contract" in data
    assert "config_schema" in data
    assert "allowable_values_source" in data["config_schema"]
    mock_step_template_repo.get_by_id.assert_awaited_once_with("step_template_ai_constrain_values_claude")


def test_management_step_template_detail_404(client):
    """GET /management/step-templates/{id} returns 404 when template not found."""
    _setup_auth(client)
    mock_step_template_repo = MagicMock()
    mock_step_template_repo.get_by_id = AsyncMock(return_value=None)
    app.state.step_template_repository = mock_step_template_repo

    resp = client.get(
        "/management/step-templates/nonexistent_template",
        headers={"Authorization": "Bearer valid-jwt"},
    )
    assert resp.status_code == 404
    assert resp.json()["detail"] == "Step template not found"


def test_management_connections_401_without_auth(client):
    """GET /management/connections without Authorization returns 401."""
    resp = client.get("/management/connections")
    assert resp.status_code == 401


def test_management_connections_200_list_shape(client):
    """GET /management/connections with valid auth returns items list."""
    user_id = _setup_auth(client)
    mock_conn_repo = MagicMock()
    mock_conn_repo.list_by_owner = AsyncMock(return_value=[
        ConnectorInstance(
            id="conn-1",
            owner_user_id=user_id,
            connector_template_id="tpl-notion",
            display_name="My Notion",
            status="active",
            config={},
            secret_ref="env:NOTION_API_KEY",
            last_validated_at=datetime(2026, 3, 15, 10, 0, 0),
            last_error=None,
        ),
    ])
    app.state.connector_instance_repository = mock_conn_repo

    resp = client.get(
        "/management/connections",
        headers={"Authorization": "Bearer valid-jwt"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "items" in data
    assert len(data["items"]) == 1
    item = data["items"][0]
    assert item["id"] == "conn-1"
    assert item["display_name"] == "My Notion"
    assert item["status"] == "active"
    assert item["connector_template_id"] == "tpl-notion"
    assert "2026-03-15" in (item["last_validated_at"] or "")
    assert item["last_error"] is None
    mock_conn_repo.list_by_owner.assert_awaited_once_with(user_id)


def test_management_triggers_401_without_auth(client):
    """GET /management/triggers without Authorization returns 401."""
    resp = client.get("/management/triggers")
    assert resp.status_code == 401


def test_management_triggers_200_list_shape(client):
    """GET /management/triggers with valid auth returns items list."""
    user_id = _setup_auth(client)
    mock_trigger_repo = MagicMock()
    mock_trigger_repo.list_by_owner = AsyncMock(return_value=[
        TriggerDefinition(
            id="trigger-1",
            owner_user_id=user_id,
            trigger_type="http",
            display_name="Locations",
            path="locations",
            method="POST",
            request_body_schema={"keywords": "string"},
            status="active",
            auth_mode="bearer",
            secret_value="abc123def456",
            secret_last_rotated_at=datetime(2026, 3, 15, 14, 0, 0),
            updated_at=datetime(2026, 3, 15, 14, 0, 0),
        ),
    ])
    app.state.trigger_repository = mock_trigger_repo

    resp = client.get(
        "/management/triggers",
        headers={"Authorization": "Bearer valid-jwt"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "items" in data
    assert len(data["items"]) == 1
    item = data["items"][0]
    assert item["id"] == "trigger-1"
    assert item["display_name"] == "Locations"
    assert item["trigger_type"] == "http"
    assert item["path"] == "locations"
    assert item["method"] == "POST"
    assert item["status"] == "active"
    assert item["auth_mode"] == "bearer"
    assert "secret" in item
    assert item["secret"] == "abc123def456"
    assert "secret_last_rotated_at" in item
    assert "2026-03-15" in (item["updated_at"] or "")
    assert item["request_body_schema"] == {"keywords": "string"}
    mock_trigger_repo.list_by_owner.assert_awaited_once_with(user_id)


def test_management_rotate_secret_200_returns_new_secret(client):
    """POST /management/triggers/{id}/rotate-secret with valid auth returns new secret."""
    from app.domain.triggers import TriggerDefinition

    user_id = _setup_auth(client)
    mock_trigger_repo = MagicMock()
    rotated_trigger = TriggerDefinition(
        id="trigger-1",
        owner_user_id=user_id,
        trigger_type="http",
        display_name="Locations",
        path="locations",
        method="POST",
        request_body_schema={},
        status="active",
        auth_mode="bearer",
        secret_value="new_secret_abc123",
        secret_last_rotated_at=datetime(2026, 3, 15, 15, 0, 0),
    )
    mock_trigger_repo.rotate_secret = AsyncMock(return_value=(rotated_trigger, "new_secret_abc123"))
    app.state.trigger_repository = mock_trigger_repo

    resp = client.post(
        "/management/triggers/trigger-1/rotate-secret",
        headers={"Authorization": "Bearer valid-jwt"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == "trigger-1"
    assert data["secret"] == "new_secret_abc123"
    assert "secret_last_rotated_at" in data
    mock_trigger_repo.rotate_secret.assert_awaited_once_with("trigger-1", user_id)


def test_management_rotate_secret_404_when_trigger_not_found(client):
    """POST /management/triggers/{id}/rotate-secret returns 404 when trigger not found."""
    user_id = _setup_auth(client)
    mock_trigger_repo = MagicMock()
    mock_trigger_repo.rotate_secret = AsyncMock(
        side_effect=ValueError("Trigger not found: id=missing owner=...")
    )
    app.state.trigger_repository = mock_trigger_repo

    resp = client.post(
        "/management/triggers/missing/rotate-secret",
        headers={"Authorization": "Bearer valid-jwt"},
    )
    assert resp.status_code == 404
    assert "not found" in resp.json()["detail"].lower()


def test_management_delete_trigger_401_without_auth(client):
    """DELETE /management/triggers/{id} without Authorization returns 401."""
    resp = client.delete("/management/triggers/trigger-1")
    assert resp.status_code == 401


def test_management_delete_trigger_404_when_not_found(client):
    """DELETE /management/triggers/{id} returns 404 when trigger not found."""
    user_id = _setup_auth(client)
    mock_trigger_repo = MagicMock()
    mock_trigger_repo.get_by_id = AsyncMock(return_value=None)
    mock_trigger_repo.delete = AsyncMock()
    app.state.trigger_repository = mock_trigger_repo

    resp = client.delete(
        "/management/triggers/missing",
        headers={"Authorization": "Bearer valid-jwt"},
    )
    assert resp.status_code == 404
    mock_trigger_repo.delete.assert_not_awaited()


def test_management_delete_trigger_200_deletes(client):
    """DELETE /management/triggers/{id} removes trigger when owned."""
    user_id = _setup_auth(client)
    existing = TriggerDefinition(
        id="trigger-1",
        owner_user_id=user_id,
        trigger_type="http",
        display_name="T",
        path="/t",
        method="POST",
        request_body_schema={},
        status="active",
        auth_mode="bearer",
        secret_value="sec",
    )
    mock_trigger_repo = MagicMock()
    mock_trigger_repo.get_by_id = AsyncMock(return_value=existing)
    mock_trigger_repo.delete = AsyncMock()
    app.state.trigger_repository = mock_trigger_repo

    resp = client.delete(
        "/management/triggers/trigger-1",
        headers={"Authorization": "Bearer valid-jwt"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "deleted"
    assert data["id"] == "trigger-1"
    mock_trigger_repo.delete.assert_awaited_once_with("trigger-1", user_id)


def test_management_create_trigger_401_without_auth(client):
    """POST /management/triggers without Authorization returns 401."""
    resp = client.post(
        "/management/triggers",
        json={"path": "/my-trigger"},
    )
    assert resp.status_code == 401


def test_management_create_trigger_200_returns_created_trigger(client):
    """POST /management/triggers with valid auth creates trigger and returns it with secret."""
    user_id = _setup_auth(client)
    mock_trigger_repo = MagicMock()
    mock_trigger_repo.get_by_path = AsyncMock(return_value=None)
    mock_trigger_repo.save = AsyncMock()
    app.state.trigger_repository = mock_trigger_repo

    resp = client.post(
        "/management/triggers",
        headers={"Authorization": "Bearer valid-jwt"},
        json={"path": "my-trigger", "display_name": "My Custom Trigger"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "id" in data
    assert data["id"].startswith("trigger_")
    assert data["display_name"] == "My Custom Trigger"
    assert data["path"] == "/my-trigger"
    assert data["method"] == "POST"
    assert data["status"] == "active"
    assert data["auth_mode"] == "bearer"
    assert "secret" in data
    assert len(data["secret"]) >= 20
    mock_trigger_repo.get_by_path.assert_awaited_once()
    call_args = mock_trigger_repo.get_by_path.call_args
    assert call_args[0][0] == "/my-trigger"
    assert call_args[0][1] == user_id
    mock_trigger_repo.save.assert_awaited_once()
    saved_trigger = mock_trigger_repo.save.call_args[0][0]
    assert saved_trigger.request_body_schema.get("type") == "object"
    assert "keywords" in (saved_trigger.request_body_schema.get("properties") or {})
    assert data["request_body_schema"] == saved_trigger.request_body_schema


def test_management_create_trigger_with_body_fields(client):
    """POST /management/triggers accepts body_fields to build request_body_schema."""
    user_id = _setup_auth(client)
    mock_trigger_repo = MagicMock()
    mock_trigger_repo.get_by_path = AsyncMock(return_value=None)
    mock_trigger_repo.save = AsyncMock()
    app.state.trigger_repository = mock_trigger_repo

    resp = client.post(
        "/management/triggers",
        headers={"Authorization": "Bearer valid-jwt"},
        json={
            "path": "/custom-hook",
            "body_fields": [
                {"name": "message", "type": "string", "required": True, "max_length": 500},
                {"name": "priority", "type": "number", "required": False},
            ],
        },
    )
    assert resp.status_code == 200
    saved = mock_trigger_repo.save.call_args[0][0]
    props = saved.request_body_schema.get("properties") or {}
    assert "message" in props and "priority" in props
    assert "message" in (saved.request_body_schema.get("required") or [])


def test_management_patch_trigger_body_fields(client):
    user_id = _setup_auth(client)
    mock_trigger_repo = MagicMock()
    existing = TriggerDefinition(
        id="trigger-1",
        owner_user_id=user_id,
        trigger_type="http",
        display_name="T",
        path="/t",
        method="POST",
        request_body_schema={"type": "object", "properties": {}, "required": []},
        status="active",
        auth_mode="bearer",
        secret_value="sec",
    )
    mock_trigger_repo.get_by_id = AsyncMock(return_value=existing)
    mock_trigger_repo.save = AsyncMock()
    app.state.trigger_repository = mock_trigger_repo

    resp = client.patch(
        "/management/triggers/trigger-1",
        headers={"Authorization": "Bearer valid-jwt"},
        json={
            "body_fields": [
                {"name": "title", "type": "string", "required": True},
            ]
        },
    )
    assert resp.status_code == 200
    mock_trigger_repo.save.assert_awaited_once()
    assert "title" in mock_trigger_repo.save.call_args[0][0].request_body_schema.get(
        "properties", {}
    )


def test_management_create_trigger_409_duplicate_path(client):
    """POST /management/triggers returns 409 when path already in use."""
    user_id = _setup_auth(client)
    mock_trigger_repo = MagicMock()
    mock_trigger_repo.get_by_path = AsyncMock(return_value=TriggerDefinition(
        id="existing",
        owner_user_id=user_id,
        trigger_type="http",
        display_name="Existing",
        path="/my-trigger",
        method="POST",
        request_body_schema={},
        status="active",
        auth_mode="bearer",
        secret_value="secret",
    ))
    mock_trigger_repo.save = AsyncMock()
    app.state.trigger_repository = mock_trigger_repo

    resp = client.post(
        "/management/triggers",
        headers={"Authorization": "Bearer valid-jwt"},
        json={"path": "/my-trigger"},
    )
    assert resp.status_code == 409
    assert "already in use" in resp.json()["detail"]
    mock_trigger_repo.save.assert_not_awaited()


def test_management_create_trigger_normalizes_path(client):
    """POST /management/triggers normalizes path to leading slash."""
    _setup_auth(client)
    mock_trigger_repo = MagicMock()
    mock_trigger_repo.get_by_path = AsyncMock(return_value=None)
    mock_trigger_repo.save = AsyncMock()
    app.state.trigger_repository = mock_trigger_repo

    resp = client.post(
        "/management/triggers",
        headers={"Authorization": "Bearer valid-jwt"},
        json={"path": "no-leading-slash"},
    )
    assert resp.status_code == 200
    assert resp.json()["path"] == "/no-leading-slash"


def test_management_account_401_without_auth(client):
    """GET /management/account without Authorization returns 401."""
    resp = client.get("/management/account")
    assert resp.status_code == 401


def test_management_account_200_without_limits(client):
    """GET /management/account with valid auth returns user context, no limits."""
    user_id = _setup_auth(client)
    app.state.app_config_repository = None

    resp = client.get(
        "/management/account",
        headers={"Authorization": "Bearer valid-jwt"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["user_id"] == user_id
    assert data["email"] == "user@example.com"
    assert data["user_type"] == USER_TYPE_STANDARD
    assert "limits" not in data


def test_management_account_200_with_limits(client):
    """GET /management/account with valid auth and app_config returns limits."""
    user_id = _setup_auth(client)
    mock_app_config = MagicMock()
    mock_app_config.get_by_owner = AsyncMock(return_value=AppLimits(
        max_stages_per_job=10,
        max_pipelines_per_stage=20,
        max_steps_per_pipeline=50,
        max_jobs_per_owner=50,
        max_triggers_per_owner=50,
        max_runs_per_utc_day=500,
        max_runs_per_utc_month=10000,
    ))
    app.state.app_config_repository = mock_app_config

    resp = client.get(
        "/management/account",
        headers={"Authorization": "Bearer valid-jwt"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["user_id"] == user_id
    assert "limits" in data
    assert data["limits"]["max_stages_per_job"] == 10
    assert data["limits"]["max_pipelines_per_stage"] == 20
    assert data["limits"]["max_steps_per_pipeline"] == 50
    mock_app_config.get_by_owner.assert_awaited_once_with(user_id)


def _make_minimal_job_graph(user_id: str, job_id: str = "job_test"):
    """Build minimal valid JobGraph for tests."""
    stage_id = "stage_1"
    pipeline_id = "pipeline_1"
    step_id = "step_1"
    job = JobDefinition(
        id=job_id,
        owner_user_id=user_id,
        display_name="Test Job",
        target_id="tgt1",
        status="active",
        stage_ids=[stage_id],
    )
    stage = StageDefinition(
        id=stage_id,
        job_id=job_id,
        display_name="Stage 1",
        sequence=1,
        pipeline_ids=[pipeline_id],
        pipeline_run_mode="parallel",
    )
    pipeline = PipelineDefinition(
        id=pipeline_id,
        stage_id=stage_id,
        display_name="Pipeline 1",
        sequence=1,
        step_ids=[step_id],
    )
    step = StepInstance(
        id=step_id,
        pipeline_id=pipeline_id,
        step_template_id="step_template_property_set",
        display_name="Property Set",
        sequence=1,
        input_bindings={},
        config={"schema_property_id": "prop_title"},
    )
    return JobGraph(job=job, stages=[stage], pipelines=[pipeline], steps=[step])


def test_management_pipeline_delete_401_without_auth(client):
    """DELETE /management/pipelines/{id} without Authorization returns 401."""
    resp = client.delete("/management/pipelines/job_1")
    assert resp.status_code == 401


def test_management_pipeline_delete_404_when_not_found(client):
    """DELETE /management/pipelines/{id} returns 404 when pipeline not found."""
    user_id = _setup_auth(client)
    mock_job_repo = MagicMock()
    mock_job_repo.get_graph_by_id = AsyncMock(return_value=None)
    mock_job_repo.archive = AsyncMock()
    app.state.job_repository = mock_job_repo

    resp = client.delete(
        "/management/pipelines/job_missing",
        headers={"Authorization": "Bearer valid-jwt"},
    )
    assert resp.status_code == 404
    assert "not found" in resp.json()["detail"].lower()
    mock_job_repo.get_graph_by_id.assert_awaited_once_with("job_missing", user_id)
    mock_job_repo.archive.assert_not_awaited()


def test_management_pipeline_delete_200_archives(client):
    """DELETE /management/pipelines/{id} archives pipeline and returns status."""
    user_id = _setup_auth(client)
    graph = _make_minimal_job_graph(user_id, "job_to_archive")
    mock_job_repo = MagicMock()
    mock_job_repo.get_graph_by_id = AsyncMock(return_value=graph)
    mock_job_repo.archive = AsyncMock()
    app.state.job_repository = mock_job_repo

    resp = client.delete(
        "/management/pipelines/job_to_archive",
        headers={"Authorization": "Bearer valid-jwt"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "archived"
    assert data["id"] == "job_to_archive"
    mock_job_repo.get_graph_by_id.assert_awaited_once_with("job_to_archive", user_id)
    mock_job_repo.archive.assert_awaited_once_with("job_to_archive", user_id)


def test_management_patch_pipeline_status_401_without_auth(client):
    """PATCH /management/pipelines/{id}/status without Authorization returns 401."""
    resp = client.patch(
        "/management/pipelines/job_1/status",
        json={"status": "disabled"},
    )
    assert resp.status_code == 401


def test_management_patch_pipeline_status_404_when_not_found(client):
    """PATCH /management/pipelines/{id}/status returns 404 when pipeline not found."""
    user_id = _setup_auth(client)
    mock_job_repo = MagicMock()
    mock_job_repo.get_graph_by_id = AsyncMock(return_value=None)
    mock_job_repo.update_job_status = AsyncMock()
    app.state.job_repository = mock_job_repo

    resp = client.patch(
        "/management/pipelines/job_missing/status",
        headers={"Authorization": "Bearer valid-jwt"},
        json={"status": "disabled"},
    )
    assert resp.status_code == 404
    mock_job_repo.update_job_status.assert_not_awaited()


def test_management_patch_pipeline_status_200_toggles_active_disabled(client):
    """PATCH /management/pipelines/{id}/status sets active or disabled via update_job_status only."""
    user_id = _setup_auth(client)
    graph = _make_minimal_job_graph(user_id, "job_toggle")
    mock_job_repo = MagicMock()
    mock_job_repo.get_graph_by_id = AsyncMock(return_value=graph)
    mock_job_repo.update_job_status = AsyncMock()
    mock_job_repo.save_job_graph = AsyncMock()
    app.state.job_repository = mock_job_repo

    resp = client.patch(
        "/management/pipelines/job_toggle/status",
        headers={"Authorization": "Bearer valid-jwt"},
        json={"status": "disabled"},
    )
    assert resp.status_code == 200
    assert resp.json() == {"id": "job_toggle", "status": "disabled"}
    mock_job_repo.update_job_status.assert_awaited_once_with("job_toggle", user_id, "disabled")
    mock_job_repo.save_job_graph.assert_not_awaited()

    mock_job_repo.update_job_status.reset_mock()
    resp2 = client.patch(
        "/management/pipelines/job_toggle/status",
        headers={"Authorization": "Bearer valid-jwt"},
        json={"status": "active"},
    )
    assert resp2.status_code == 200
    assert resp2.json() == {"id": "job_toggle", "status": "active"}
    mock_job_repo.update_job_status.assert_awaited_once_with("job_toggle", user_id, "active")


def test_management_pipeline_get_404_when_not_found(client):
    """GET /management/pipelines/{id} returns 404 when pipeline not found."""
    user_id = _setup_auth(client)
    mock_job_repo = MagicMock()
    mock_job_repo.get_graph_by_id = AsyncMock(return_value=None)
    app.state.job_repository = mock_job_repo

    resp = client.get(
        "/management/pipelines/job_missing",
        headers={"Authorization": "Bearer valid-jwt"},
    )
    assert resp.status_code == 404
    assert "not found" in resp.json()["detail"].lower()
    mock_job_repo.get_graph_by_id.assert_awaited_once_with("job_missing", user_id)


def test_management_pipeline_get_200_returns_full_graph(client):
    """GET /management/pipelines/{id} returns full editable graph when found."""
    user_id = _setup_auth(client)
    graph = _make_minimal_job_graph(user_id, "job_test")
    mock_job_repo = MagicMock()
    mock_job_repo.get_graph_by_id = AsyncMock(return_value=graph)
    app.state.job_repository = mock_job_repo

    mock_link_repo = MagicMock()
    mock_link_repo.list_trigger_ids_for_job = AsyncMock(return_value=["trigger_1"])
    app.state.trigger_job_link_repository = mock_link_repo

    resp = client.get(
        "/management/pipelines/job_test",
        headers={"Authorization": "Bearer valid-jwt"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == "job_test"
    assert data["display_name"] == "Test Job"
    assert "stages" in data
    assert len(data["stages"]) == 1
    assert data["stages"][0]["id"] == "stage_1"
    assert "pipelines" in data["stages"][0]
    assert len(data["stages"][0]["pipelines"]) == 1
    assert "steps" in data["stages"][0]["pipelines"][0]
    assert data.get("trigger_ids") == ["trigger_1"]
    assert data.get("trigger_id") == "trigger_1"
    mock_job_repo.get_graph_by_id.assert_awaited_once_with("job_test", user_id)
    mock_link_repo.list_trigger_ids_for_job.assert_awaited_once_with("job_test", user_id)


def test_management_pipeline_put_200_saves_and_returns_canonical(client):
    """PUT /management/pipelines/{id} saves graph and returns canonical payload."""
    user_id = _setup_auth(client)
    graph = _make_minimal_job_graph(user_id, "job_save")
    mock_job_repo = MagicMock()
    mock_job_repo.get_graph_by_id = AsyncMock(return_value=graph)
    mock_job_repo.save_job_graph = AsyncMock()
    app.state.job_repository = mock_job_repo

    payload = {
        "id": "job_save",
        "owner_user_id": user_id,
        "display_name": "Saved Job",
        "target_id": "tgt1",
        "status": "active",
        "stage_ids": ["stage_1"],
        "stages": [
            {
                "id": "stage_1",
                "job_id": "job_save",
                "display_name": "Stage 1",
                "sequence": 1,
                "pipeline_ids": ["pipeline_1"],
                "pipelines": [
                    {
                        "id": "pipeline_1",
                        "stage_id": "stage_1",
                        "display_name": "Pipeline 1",
                        "sequence": 1,
                        "step_ids": ["step_1"],
                        "steps": [
                            {
                                "id": "step_1",
                                "pipeline_id": "pipeline_1",
                                "step_template_id": "step_template_property_set",
                                "display_name": "Property Set",
                                "sequence": 1,
                                "input_bindings": {},
                                "config": {"schema_property_id": "prop_title"},
                            }
                        ],
                    }
                ],
            }
        ],
    }

    mock_link_repo = MagicMock()
    mock_link_repo.list_trigger_ids_for_job = AsyncMock(return_value=["trigger_save"])
    app.state.trigger_job_link_repository = mock_link_repo

    resp = client.put(
        "/management/pipelines/job_save",
        headers={"Authorization": "Bearer valid-jwt"},
        json=payload,
    )
    assert resp.status_code == 200
    mock_job_repo.save_job_graph.assert_awaited_once()
    mock_job_repo.get_graph_by_id.assert_awaited_with("job_save", user_id)
    data = resp.json()
    assert data["id"] == "job_save"
    assert "stages" in data
    assert data.get("trigger_ids") == ["trigger_save"]
    assert data.get("trigger_id") == "trigger_save"


def test_management_pipeline_put_422_on_validation_error(client):
    """PUT /management/pipelines/{id} returns 422 with validation_errors when invalid."""
    from app.services.validation_service import ValidationError

    user_id = _setup_auth(client)
    mock_job_repo = MagicMock()
    mock_job_repo.save_job_graph = AsyncMock(
        side_effect=ValidationError(
            "validation failed",
            errors=["pipeline 'p1' must terminate with Cache Set or Property Set"],
        )
    )
    app.state.job_repository = mock_job_repo

    payload = {
        "id": "job_bad",
        "owner_user_id": user_id,
        "display_name": "Bad",
        "target_id": "tgt1",
        "status": "active",
        "stage_ids": ["s1"],
        "stages": [
            {
                "id": "s1",
                "job_id": "job_bad",
                "display_name": "S1",
                "sequence": 1,
                "pipeline_ids": ["p1"],
                "pipelines": [
                    {
                        "id": "p1",
                        "stage_id": "s1",
                        "display_name": "P1",
                        "sequence": 1,
                        "step_ids": ["st1"],
                        "steps": [
                            {
                                "id": "st1",
                                "pipeline_id": "p1",
                                "step_template_id": "step_template_google_places_lookup",
                                "display_name": "Lookup",
                                "sequence": 1,
                                "input_bindings": {},
                                "config": {},
                            }
                        ],
                    }
                ],
            }
        ],
    }

    resp = client.put(
        "/management/pipelines/job_bad",
        headers={"Authorization": "Bearer valid-jwt"},
        json=payload,
    )
    assert resp.status_code == 422
    data = resp.json()
    assert "validation_errors" in data
    assert any("terminate" in e.lower() for e in data["validation_errors"])


def test_management_pipeline_post_200_creates_and_returns_graph(client):
    """POST /management/pipelines creates new pipeline and returns full graph with trigger link."""
    user_id = _setup_auth(client)

    def mock_get_graph(job_id, owner):
        g = _make_minimal_job_graph(owner, job_id)
        g.job.display_name = "My New Pipeline"
        return g

    mock_job_repo = MagicMock()
    mock_job_repo.list_by_owner = AsyncMock(return_value=[])
    mock_job_repo.save_job_graph = AsyncMock(return_value=None)
    mock_job_repo.get_graph_by_id = AsyncMock(side_effect=mock_get_graph)
    app.state.job_repository = mock_job_repo

    mock_target_repo = MagicMock()
    mock_target_repo.get_by_id = AsyncMock(return_value=DataTarget(
        id="tgt1",
        owner_user_id=user_id,
        target_template_id="tt_notion_db",
        connector_instance_id="conn_1",
        display_name="Places to Visit",
        external_target_id="ds-xxx",
        status="active",
    ))
    app.state.target_repository = mock_target_repo

    mock_trigger_repo = MagicMock()
    mock_trigger_repo.get_by_id = AsyncMock(return_value=TriggerDefinition(
        id="trigger_1",
        owner_user_id=user_id,
        trigger_type="http",
        display_name="/locations",
        path="/locations",
        method="POST",
        request_body_schema={"keywords": "string"},
        status="active",
        auth_mode="bearer",
        secret_value="mock_secret",
    ))
    app.state.trigger_repository = mock_trigger_repo

    mock_link_repo = MagicMock()
    mock_link_repo.list_trigger_ids_for_job = AsyncMock(return_value=["trigger_1"])
    mock_link_repo.attach = AsyncMock()
    app.state.trigger_job_link_repository = mock_link_repo

    resp = client.post(
        "/management/pipelines",
        headers={"Authorization": "Bearer valid-jwt"},
        json={
            "display_name": "My New Pipeline",
            "trigger_id": "trigger_1",
            "target_id": "tgt1",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "id" in data
    assert data["id"].startswith("job_")
    assert data["display_name"] == "My New Pipeline"
    assert data["trigger_id"] == "trigger_1"
    assert "stages" in data
    mock_job_repo.save_job_graph.assert_awaited_once()
    mock_job_repo.get_graph_by_id.assert_awaited()
    mock_target_repo.get_by_id.assert_awaited_once_with("tgt1", user_id)
    mock_trigger_repo.get_by_id.assert_awaited_once_with("trigger_1", user_id)
    mock_link_repo.attach.assert_awaited_once()
    call_args = mock_link_repo.attach.call_args[0]
    assert call_args[0] == "trigger_1"
    assert call_args[1] == data["id"]
    assert call_args[2] == user_id


def test_management_pipeline_post_200_with_explicit_target_id(client):
    """POST /management/pipelines with target_id and trigger_id uses them and validates ownership."""
    user_id = _setup_auth(client)

    def mock_get_graph(job_id, owner):
        g = _make_minimal_job_graph(owner, job_id)
        g.job.target_id = "tgt_explicit"
        g.job.display_name = "Pipeline"
        return g

    mock_job_repo = MagicMock()
    mock_job_repo.list_by_owner = AsyncMock(return_value=[])
    mock_job_repo.save_job_graph = AsyncMock(return_value=None)
    mock_job_repo.get_graph_by_id = AsyncMock(side_effect=mock_get_graph)
    app.state.job_repository = mock_job_repo

    mock_target_repo = MagicMock()
    mock_target_repo.get_by_id = AsyncMock(return_value=DataTarget(
        id="tgt_explicit",
        owner_user_id=user_id,
        target_template_id="tt_notion_db",
        connector_instance_id="conn_1",
        display_name="My DB",
        external_target_id="ds-xxx",
        status="active",
    ))
    app.state.target_repository = mock_target_repo

    mock_trigger_repo = MagicMock()
    mock_trigger_repo.get_by_id = AsyncMock(return_value=TriggerDefinition(
        id="trigger_explicit",
        owner_user_id=user_id,
        trigger_type="http",
        display_name="/my-path",
        path="/my-path",
        method="POST",
        request_body_schema={},
        status="active",
        auth_mode="bearer",
        secret_value="mock_secret",
    ))
    app.state.trigger_repository = mock_trigger_repo

    mock_link_repo = MagicMock()
    mock_link_repo.list_trigger_ids_for_job = AsyncMock(return_value=["trigger_explicit"])
    mock_link_repo.attach = AsyncMock()
    app.state.trigger_job_link_repository = mock_link_repo

    resp = client.post(
        "/management/pipelines",
        headers={"Authorization": "Bearer valid-jwt"},
        json={
            "display_name": "Pipeline",
            "target_id": "tgt_explicit",
            "trigger_id": "trigger_explicit",
        },
    )
    assert resp.status_code == 200
    mock_job_repo.save_job_graph.assert_awaited_once()
    call_args = mock_job_repo.save_job_graph.call_args[0][0]
    assert call_args.job.target_id == "tgt_explicit"
    mock_target_repo.get_by_id.assert_awaited_once_with("tgt_explicit", user_id)
    mock_link_repo.attach.assert_awaited_once_with("trigger_explicit", call_args.job.id, user_id)


def test_management_pipeline_post_422_when_target_invalid(client):
    """POST /management/pipelines returns 422 INVALID_TARGET when target not found."""
    user_id = _setup_auth(client)

    mock_job_repo = MagicMock()
    mock_job_repo.list_by_owner = AsyncMock(return_value=[])
    mock_job_repo.save_job_graph = AsyncMock()
    app.state.job_repository = mock_job_repo

    mock_target_repo = MagicMock()
    mock_target_repo.get_by_id = AsyncMock(return_value=None)
    app.state.target_repository = mock_target_repo

    mock_trigger_repo = MagicMock()
    mock_trigger_repo.get_by_id = AsyncMock(return_value=TriggerDefinition(
        id="trigger_1",
        owner_user_id=user_id,
        trigger_type="http",
        display_name="/locations",
        path="/locations",
        method="POST",
        request_body_schema={},
        status="active",
        auth_mode="bearer",
        secret_value="mock_secret",
    ))
    app.state.trigger_repository = mock_trigger_repo

    resp = client.post(
        "/management/pipelines",
        headers={"Authorization": "Bearer valid-jwt"},
        json={
            "display_name": "New Pipeline",
            "trigger_id": "trigger_1",
            "target_id": "tgt_nonexistent",
        },
    )
    assert resp.status_code == 422
    data = resp.json()
    assert "not found" in data["detail"].lower()
    assert data.get("code") == "INVALID_TARGET"
    mock_target_repo.get_by_id.assert_awaited_once_with("tgt_nonexistent", user_id)
    mock_job_repo.save_job_graph.assert_not_awaited()


def test_management_pipeline_post_422_when_attach_policy_rejects(client):
    """POST /management/pipelines returns 422 when trigger-job attach violates one-trigger-per-job policy."""
    from app.domain.errors import TriggerJobLinkPolicyError

    user_id = _setup_auth(client)

    def mock_get_graph(job_id, owner):
        g = _make_minimal_job_graph(owner, job_id)
        g.job.display_name = "Orphan Policy Test"
        return g

    mock_job_repo = MagicMock()
    mock_job_repo.list_by_owner = AsyncMock(return_value=[])
    mock_job_repo.save_job_graph = AsyncMock(return_value=None)
    mock_job_repo.get_graph_by_id = AsyncMock(side_effect=mock_get_graph)
    app.state.job_repository = mock_job_repo

    mock_target_repo = MagicMock()
    mock_target_repo.get_by_id = AsyncMock(return_value=DataTarget(
        id="tgt1",
        owner_user_id=user_id,
        target_template_id="tt_notion_db",
        connector_instance_id="conn_1",
        display_name="Places",
        external_target_id="ds-xxx",
        status="active",
    ))
    app.state.target_repository = mock_target_repo

    mock_trigger_repo = MagicMock()
    mock_trigger_repo.get_by_id = AsyncMock(return_value=TriggerDefinition(
        id="trigger_new",
        owner_user_id=user_id,
        trigger_type="http",
        display_name="/new",
        path="/new",
        method="POST",
        request_body_schema={},
        status="active",
        auth_mode="bearer",
        secret_value="mock_secret",
    ))
    app.state.trigger_repository = mock_trigger_repo

    mock_link_repo = MagicMock()
    mock_link_repo.attach = AsyncMock(
        side_effect=TriggerJobLinkPolicyError(
            "This pipeline is already linked to another trigger. Each pipeline may only use one trigger.",
            code="JOB_ALREADY_HAS_TRIGGER",
        )
    )
    app.state.trigger_job_link_repository = mock_link_repo

    resp = client.post(
        "/management/pipelines",
        headers={"Authorization": "Bearer valid-jwt"},
        json={
            "display_name": "Policy Test",
            "trigger_id": "trigger_new",
            "target_id": "tgt1",
        },
    )
    assert resp.status_code == 422
    body = resp.json()
    assert body.get("code") == "JOB_ALREADY_HAS_TRIGGER"
    assert "already linked" in body.get("detail", "").lower()
    mock_job_repo.save_job_graph.assert_awaited_once()


def test_management_pipeline_post_422_when_trigger_invalid(client):
    """POST /management/pipelines returns 422 INVALID_TRIGGER when trigger not found."""
    user_id = _setup_auth(client)

    mock_job_repo = MagicMock()
    mock_job_repo.list_by_owner = AsyncMock(return_value=[])
    mock_job_repo.save_job_graph = AsyncMock()
    app.state.job_repository = mock_job_repo

    mock_target_repo = MagicMock()
    mock_target_repo.get_by_id = AsyncMock(return_value=DataTarget(
        id="tgt1",
        owner_user_id=user_id,
        target_template_id="tt_notion_db",
        connector_instance_id="conn_1",
        display_name="Places",
        external_target_id="ds-xxx",
        status="active",
    ))
    app.state.target_repository = mock_target_repo

    mock_trigger_repo = MagicMock()
    mock_trigger_repo.get_by_id = AsyncMock(return_value=None)
    app.state.trigger_repository = mock_trigger_repo

    resp = client.post(
        "/management/pipelines",
        headers={"Authorization": "Bearer valid-jwt"},
        json={
            "display_name": "New Pipeline",
            "trigger_id": "trigger_nonexistent",
            "target_id": "tgt1",
        },
    )
    assert resp.status_code == 422
    data = resp.json()
    assert "not found" in data["detail"].lower()
    assert data.get("code") == "INVALID_TRIGGER"
    mock_trigger_repo.get_by_id.assert_awaited_once_with("trigger_nonexistent", user_id)
    mock_job_repo.save_job_graph.assert_not_awaited()


def test_management_pipeline_post_422_when_missing_trigger_or_target(client):
    """POST /management/pipelines returns 422 when trigger_id or target_id missing."""
    _setup_auth(client)
    mock_job_repo = MagicMock()
    mock_job_repo.list_by_owner = AsyncMock(return_value=[])
    mock_job_repo.save_job_graph = AsyncMock()
    app.state.job_repository = mock_job_repo
    app.state.target_repository = MagicMock()
    app.state.trigger_repository = MagicMock()
    app.state.trigger_job_link_repository = MagicMock()

    resp = client.post(
        "/management/pipelines",
        headers={"Authorization": "Bearer valid-jwt"},
        json={"display_name": "New Pipeline"},
    )
    assert resp.status_code == 422
    mock_job_repo.save_job_graph.assert_not_awaited()


def test_management_data_targets_401_without_auth(client):
    """GET /management/data-targets without Authorization returns 401."""
    resp = client.get("/management/data-targets")
    assert resp.status_code == 401


def test_management_data_targets_200_list_shape(client):
    """GET /management/data-targets with valid auth returns items list."""
    user_id = _setup_auth(client)
    mock_target_repo = MagicMock()
    mock_target_repo.list_by_owner = AsyncMock(return_value=[
        DataTarget(
            id="tgt1",
            owner_user_id=user_id,
            target_template_id="tt_notion_db",
            connector_instance_id="conn_1",
            display_name="Places to Visit",
            external_target_id="ds-xxx",
            status="active",
        ),
    ])
    app.state.target_repository = mock_target_repo

    resp = client.get(
        "/management/data-targets",
        headers={"Authorization": "Bearer valid-jwt"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "items" in data
    assert len(data["items"]) == 1
    assert data["items"][0]["id"] == "tgt1"
    assert data["items"][0]["display_name"] == "Places to Visit"


def test_management_data_targets_deduplicates_by_external_target(client):
    """When bootstrap and per-source targets share the same DB, only one is returned (prefer bootstrap)."""
    user_id = _setup_auth(client)
    mock_target_repo = MagicMock()
    mock_target_repo.list_by_owner = AsyncMock(return_value=[
        DataTarget(
            id="target_notion_abc",
            owner_user_id=user_id,
            target_template_id="tt_notion_db",
            connector_instance_id="conn_1",
            display_name="Places to Visit",
            external_target_id="ds-xxx",
            status="active",
        ),
        DataTarget(
            id="target_places_to_visit",
            owner_user_id=user_id,
            target_template_id="tt_notion_db",
            connector_instance_id="conn_1",
            display_name="Places to Visit",
            external_target_id="ds-xxx",
            status="active",
        ),
        DataTarget(
            id="target_notion_def",
            owner_user_id=user_id,
            target_template_id="tt_notion_db",
            connector_instance_id="conn_1",
            display_name="Locations",
            external_target_id="ds-yyy",
            status="active",
        ),
        DataTarget(
            id="target_locations",
            owner_user_id=user_id,
            target_template_id="tt_notion_db",
            connector_instance_id="conn_1",
            display_name="Locations",
            external_target_id="ds-yyy",
            status="active",
        ),
    ])
    app.state.target_repository = mock_target_repo

    resp = client.get(
        "/management/data-targets",
        headers={"Authorization": "Bearer valid-jwt"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "items" in data
    assert len(data["items"]) == 2
    ids = {i["id"] for i in data["items"]}
    assert ids == {"target_places_to_visit", "target_locations"}


def test_management_data_target_schema_404_when_target_not_found(client):
    """GET /management/data-targets/{id}/schema returns 404 when target not found."""
    user_id = _setup_auth(client)
    mock_target_repo = MagicMock()
    mock_target_repo.get_by_id = AsyncMock(return_value=None)
    app.state.target_repository = mock_target_repo
    app.state.target_schema_repository = MagicMock()

    resp = client.get(
        "/management/data-targets/tgt_missing/schema",
        headers={"Authorization": "Bearer valid-jwt"},
    )
    assert resp.status_code == 404


def test_management_data_target_schema_200_returns_properties(client):
    """GET /management/data-targets/{id}/schema returns schema with properties."""
    from app.domain.targets import TargetSchemaProperty, TargetSchemaSnapshot
    from datetime import datetime, timezone

    user_id = _setup_auth(client)
    mock_target_repo = MagicMock()
    mock_target_repo.get_by_id = AsyncMock(return_value=DataTarget(
        id="tgt1",
        owner_user_id=user_id,
        target_template_id="tt_notion_db",
        connector_instance_id="conn_1",
        display_name="Places",
        external_target_id="ds-xxx",
        status="active",
        active_schema_snapshot_id="snap1",
    ))
    app.state.target_repository = mock_target_repo

    mock_schema_repo = MagicMock()
    mock_schema_repo.get_by_id = AsyncMock(return_value=TargetSchemaSnapshot(
        id="snap1",
        owner_user_id=user_id,
        data_target_id="tgt1",
        version="1",
        fetched_at=datetime.now(timezone.utc),
        is_active=True,
        source_connector_instance_id="conn_1",
        properties=[
            TargetSchemaProperty(
                id="prop1",
                external_property_id="title",
                name="Name",
                normalized_slug="name",
                property_type="title",
                required=False,
                readonly=False,
            ),
            TargetSchemaProperty(
                id="prop2",
                external_property_id="sel",
                name="Status",
                normalized_slug="status",
                property_type="select",
                required=False,
                readonly=False,
                options=[{"id": "a", "name": "Active"}, {"id": "b", "name": "Done"}],
            ),
        ],
    ))
    app.state.target_schema_repository = mock_schema_repo

    resp = client.get(
        "/management/data-targets/tgt1/schema",
        headers={"Authorization": "Bearer valid-jwt"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["target_id"] == "tgt1"
    assert data["display_name"] == "Places"
    assert len(data["properties"]) == 2
    assert data["properties"][0]["name"] == "Name"
    assert data["properties"][0]["property_type"] == "title"
    assert data["properties"][1]["options"] == [{"id": "a", "name": "Active"}, {"id": "b", "name": "Done"}]


def _minimal_live_test_snapshot():
    return {
        "job": {
            "id": "job1",
            "stages": [
                {
                    "id": "st1",
                    "sequence": 1,
                    "pipelines": [
                        {
                            "id": "pipe1",
                            "sequence": 1,
                            "steps": [
                                {
                                    "id": "step1",
                                    "sequence": 1,
                                    "step_template_id": "step_template_optimize_input_claude",
                                    "input_bindings": {},
                                    "config": {},
                                }
                            ],
                        }
                    ],
                }
            ],
        },
        "target": {
            "id": "tgt1",
            "external_target_id": "00000000-0000-4000-8000-000000000001",
        },
        "step_templates": {},
    }


def test_management_live_test_analyze_job_scope(client):
    """POST .../live-test/analyze returns planned calls for job scope."""
    from app.services.job_definition_service import ResolvedJobSnapshot

    user_id = _setup_auth(client)
    snap = _minimal_live_test_snapshot()
    resolved = ResolvedJobSnapshot(snapshot_ref="ref1", snapshot=snap)
    mock_jd = MagicMock()
    mock_jd.resolve_for_run = AsyncMock(return_value=resolved)
    mock_link = MagicMock()
    mock_link.list_trigger_ids_for_job = AsyncMock(return_value=["tr1"])
    mock_job = MagicMock()
    app.state.job_definition_service = mock_jd
    app.state.trigger_job_link_repository = mock_link
    app.state.job_repository = mock_job

    resp = client.post(
        "/management/pipelines/job1/live-test/analyze",
        headers={"Authorization": "Bearer valid-jwt"},
        json={"live_test": {"scope_kind": "job"}},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data.get("ok") is True
    assert any(c.get("call_site_id") == "claude.optimize_input" for c in data["planned_external_calls"])
    assert data.get("analyzer_payload_hash", "").startswith("sha1:")


def test_management_live_test_run_enqueues_with_live_test_block(client):
    """POST .../run validates trigger body, analyzes, and enqueues queue payload with live_test."""
    from datetime import datetime, timezone

    from app.domain.triggers import TriggerDefinition
    from app.services.job_definition_service import ResolvedJobSnapshot

    user_id = _setup_auth(client)
    snap = _minimal_live_test_snapshot()
    resolved = ResolvedJobSnapshot(snapshot_ref="ref1", snapshot=snap)
    mock_jd = MagicMock()
    mock_jd.resolve_for_run = AsyncMock(return_value=resolved)
    mock_link = MagicMock()
    mock_link.list_trigger_ids_for_job = AsyncMock(return_value=["tr1"])
    mock_job = MagicMock()
    mock_run = MagicMock()
    mock_queue = MagicMock()
    trigger = TriggerDefinition(
        id="tr1",
        owner_user_id=user_id,
        trigger_type="http",
        display_name="T",
        path="/loc",
        method="POST",
        request_body_schema={"keywords": "string"},
        status="active",
        auth_mode="bearer",
        secret_value="sec",
        secret_last_rotated_at=datetime.now(timezone.utc),
    )
    mock_trigger_repo = MagicMock()
    mock_trigger_repo.get_by_id = AsyncMock(return_value=trigger)

    mock_run.create_job = AsyncMock()
    mock_queue.send = AsyncMock(return_value=MagicMock(message_id="pgmq-1"))

    app.state.job_definition_service = mock_jd
    app.state.trigger_job_link_repository = mock_link
    app.state.job_repository = mock_job
    app.state.supabase_run_repository = mock_run
    app.state.supabase_queue_repository = mock_queue
    app.state.trigger_repository = mock_trigger_repo

    resp = client.post(
        "/management/pipelines/job1/run",
        headers={"Authorization": "Bearer valid-jwt"},
        json={
            "trigger_body": {"keywords": "coffee"},
            "live_test": {"scope_kind": "job", "allow_destination_writes": False},
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "accepted"
    assert body.get("run_id")
    mock_queue.send.assert_awaited_once()
    enqueued = mock_queue.send.call_args[0][0]
    assert enqueued.get("live_test", {}).get("invocation_source") == "editor_live_test"
    assert enqueued.get("live_test", {}).get("allow_destination_writes") is False
    assert "_live_test_meta" in (enqueued.get("trigger_payload") or {})


def test_management_get_run_404_when_missing(client):
    """GET /management/runs/{id} returns 404 when run not found for owner."""
    user_id = _setup_auth(client)
    mock_run = MagicMock()
    mock_run.get_job_run = AsyncMock(return_value=None)
    app.state.supabase_run_repository = mock_run

    resp = client.get(
        "/management/runs/00000000-0000-4000-8000-000000000099",
        headers={"Authorization": "Bearer valid-jwt"},
    )
    assert resp.status_code == 404


def test_management_get_run_200(client):
    """GET /management/runs/{id} returns run row."""
    from app.domain.runs import JobRun

    user_id = _setup_auth(client)
    mock_run = MagicMock()
    mock_run.get_job_run = AsyncMock(return_value=JobRun(
        id="00000000-0000-4000-8000-000000000099",
        owner_user_id=user_id,
        job_id="job1",
        trigger_id="tr1",
        target_id="tgt1",
        status="succeeded",
        trigger_payload={"keywords": "a"},
    ))
    app.state.supabase_run_repository = mock_run

    resp = client.get(
        "/management/runs/00000000-0000-4000-8000-000000000099",
        headers={"Authorization": "Bearer valid-jwt"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == "00000000-0000-4000-8000-000000000099"
    assert data["status"] == "succeeded"
    assert data["job_id"] == "job1"
    assert data.get("step_traces") == []


def test_management_get_run_includes_step_traces(client):
    """GET /management/runs/{id} returns step_traces when repository lists StepRun rows."""
    from app.domain.runs import JobRun, StepRun

    user_id = _setup_auth(client)
    mock_run = MagicMock()
    mock_run.get_job_run = AsyncMock(return_value=JobRun(
        id="00000000-0000-4000-8000-000000000099",
        owner_user_id=user_id,
        job_id="job1",
        trigger_id="tr1",
        target_id="tgt1",
        status="running",
        trigger_payload={},
    ))
    mock_run.list_step_runs_for_job_run = AsyncMock(return_value=[
        StepRun(
            id="sr1",
            pipeline_run_id="pr1",
            step_id="step_a",
            step_template_id="tmpl_x",
            status="succeeded",
            owner_user_id=user_id,
            job_run_id="00000000-0000-4000-8000-000000000099",
            stage_run_id="st1",
            pipeline_id="pipe1",
            input_summary={"schema_version": 1},
            output_summary={"schema_version": 1, "status": "succeeded"},
            processing_log=["a", "b"],
        )
    ])
    app.state.supabase_run_repository = mock_run

    resp = client.get(
        "/management/runs/00000000-0000-4000-8000-000000000099",
        headers={"Authorization": "Bearer valid-jwt"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["step_traces"]) == 1
    st = data["step_traces"][0]
    assert st["step_id"] == "step_a"
    assert st["pipeline_id"] == "pipe1"
    assert st["processing"] == ["a", "b"]
    assert st["input"]["schema_version"] == 1

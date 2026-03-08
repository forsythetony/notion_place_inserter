"""Custom Tavern response verifiers."""


def verify_notion_page(response) -> None:
    """Verify response is a Notion page (object=page, has id) or dry-run preview."""
    assert response.status_code == 200
    data = response.json()
    if data.get("mode") == "dry_run":
        assert data.get("database") == "Places to Visit"
        assert "properties" in data
        assert "summary" in data
        assert "property_count" in data["summary"]
        assert "property_names" in data["summary"]
    else:
        assert data.get("object") == "page"
        assert "id" in data


def verify_accepted_job(response) -> None:
    """Verify response is async accepted (status=accepted, job_id present)."""
    assert response.status_code == 200
    data = response.json()
    assert data.get("status") == "accepted"
    assert "job_id" in data
    assert data["job_id"].startswith("loc_")


def verify_locations_200(response) -> None:
    """Verify POST /locations returns 200 with either sync (Notion page) or async (accepted) response."""
    assert response.status_code == 200
    data = response.json()
    if data.get("status") == "accepted":
        assert "job_id" in data
        assert data["job_id"].startswith("loc_")
    else:
        verify_notion_page(response)

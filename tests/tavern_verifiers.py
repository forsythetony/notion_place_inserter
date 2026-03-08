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

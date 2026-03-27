"""Tests for job_graph_id_clone.clone_job_graph_with_prefixed_ids."""

from app.repositories.yaml_loader import load_yaml_file, parse_job_graph
from app.services.job_graph_id_clone import clone_job_graph_with_prefixed_ids


def test_clone_notion_place_inserter_yaml_prefixes_ids_and_rewrites_bindings():
    data = load_yaml_file("product_model/bootstrap/jobs/notion_place_inserter.yaml")
    assert data is not None
    graph = parse_job_graph(data, owner_user_id_override="user_1")

    new_id = "job_clone123456"
    cloned = clone_job_graph_with_prefixed_ids(
        graph,
        new_id,
        owner_user_id="user_1",
        display_name="Places Insertion Pipeline [From Template]",
    )

    assert cloned.job.id == new_id
    assert cloned.job.display_name == "Places Insertion Pipeline [From Template]"
    assert cloned.job.target_id == "target_places_to_visit"

    old_step_ids = {s.id for s in graph.steps}
    new_step_ids = {s.id for s in cloned.steps}
    assert not (old_step_ids & new_step_ids)
    for sid in new_step_ids:
        assert sid.startswith(f"{new_id}_")

    # Bindings must not reference old step ids in signal_ref paths (prefix avoids substring false positives).
    for st in cloned.steps:
        assert st.id.startswith(f"{new_id}_")
        assert st.pipeline_id.startswith(f"{new_id}_")
        blob = str(st.input_bindings) + str(st.config)
        for old in old_step_ids:
            assert f"step.{old}." not in blob
        assert "job_notion_place_inserter" not in blob
        if isinstance(st.config, dict) and "linked_step_id" in st.config:
            ls = st.config["linked_step_id"]
            assert isinstance(ls, str) and ls.startswith(f"{new_id}_")

    # Spot-check known linkage from bootstrap YAML
    opt = next(s for s in cloned.steps if s.id.endswith("_step_optimize_query"))
    assert opt.config.get("linked_step_id") == f"{new_id}_step_google_places_lookup"
    lookup = next(s for s in cloned.steps if s.id.endswith("_step_google_places_lookup"))
    assert lookup.input_bindings["query"]["signal_ref"] == (
        f"step.{new_id}_step_optimize_query.optimized_query"
    )


def test_clone_preserves_trigger_signal_ref():
    data = load_yaml_file("product_model/bootstrap/jobs/notion_place_inserter.yaml")
    assert data is not None
    graph = parse_job_graph(data, owner_user_id_override="user_1")
    cloned = clone_job_graph_with_prefixed_ids(
        graph,
        "job_x",
        owner_user_id="user_u",
        display_name="Test",
    )
    opt = next(s for s in cloned.steps if s.id.endswith("_step_optimize_query"))
    assert opt.input_bindings["query"]["signal_ref"] == "trigger.payload.keywords"

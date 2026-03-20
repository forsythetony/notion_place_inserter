"""Domain errors raised by repositories and surfaced as API responses."""


class TriggerJobLinkPolicyError(Exception):
    """
    One trigger per job (pipeline) is enforced at the API layer; the DB remains many-to-many.

    A trigger may still be linked to many jobs.
    """

    def __init__(self, message: str, *, code: str = "JOB_TRIGGER_CONFLICT") -> None:
        self.message = message
        self.code = code
        super().__init__(message)


def validate_one_trigger_per_job_attach(
    existing_trigger_ids: list[str], trigger_id: str
) -> None:
    """Raise TriggerJobLinkPolicyError if ``attach(trigger_id, job_id, ...)`` would violate policy."""
    distinct = sorted(set(existing_trigger_ids))
    if len(distinct) > 1:
        raise TriggerJobLinkPolicyError(
            "This pipeline has multiple trigger links; remove extra links before changing associations.",
            code="JOB_MULTIPLE_TRIGGERS",
        )
    if len(distinct) == 1 and distinct[0] != trigger_id:
        raise TriggerJobLinkPolicyError(
            "This pipeline is already linked to another trigger. Each pipeline may only use one trigger.",
            code="JOB_ALREADY_HAS_TRIGGER",
        )

"""AI investigation alert lookup must include the authenticated tenant boundary."""

from sentinelwatch_backend.api.v1.ai_investigation import _get_alert_in_organization


class _Result:
    def __init__(self, value):
        self.value = value

    def scalar_one_or_none(self):
        return self.value


class _TenantAwareDb:
    def __init__(self, alert_id: str, organization_id: str):
        self.alert_id = alert_id
        self.organization_id = organization_id
        self.statement = None

    async def execute(self, statement):
        self.statement = statement
        params = statement.compile().params
        owns_alert = self.organization_id in params.values()
        requested_alert = self.alert_id in params.values()
        return _Result(object() if owns_alert and requested_alert else None)


def _resolve(awaitable):
    try:
        awaitable.send(None)
    except StopIteration as result:
        return result.value
    raise AssertionError("The fake database unexpectedly yielded during the test")


def test_investigation_lookup_rejects_alert_from_another_organization():
    db = _TenantAwareDb(alert_id="alert-a", organization_id="org-b")

    assert _resolve(_get_alert_in_organization(db, "alert-a", "org-a")) is None
    sql = str(db.statement)
    assert "agents.organization_id" in sql
    assert "agents.deleted_at IS NULL" in sql


def test_investigation_lookup_accepts_alert_from_selected_organization():
    db = _TenantAwareDb(alert_id="alert-a", organization_id="org-a")

    assert _resolve(_get_alert_in_organization(db, "alert-a", "org-a")) is not None

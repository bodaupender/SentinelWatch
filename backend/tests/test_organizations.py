"""Tenant membership authorization tests that do not require a network event loop."""

import pytest
from fastapi import HTTPException
from types import SimpleNamespace

from sentinelwatch_backend.api.deps import get_current_organization
from sentinelwatch_backend.models import Organization


class _Scalars:
    def __init__(self, values):
        self._values = values

    def all(self):
        return self._values


class _Result:
    def __init__(self, values):
        self._values = values

    def scalars(self):
        return _Scalars(self._values)


class _MembershipDb:
    def __init__(self, user_id, organizations, memberships):
        self.user_id = user_id
        self.organizations = organizations
        self.memberships = memberships
        self.last_query = ""

    async def execute(self, statement):
        self.last_query = str(statement)
        params = statement.compile().params
        requested_ids = {value for value in params.values() if value in {org.id for org in self.organizations}}
        organizations = self.memberships
        if "organizations.id =" in self.last_query:
            organizations = [org for org in organizations if org.id in requested_ids]
        return _Result(organizations)


def _resolve(awaitable):
    """Run an immediately-resolving async dependency without opening a Windows event loop."""
    try:
        awaitable.send(None)
    except StopIteration as result:
        return result.value
    raise AssertionError("The fake database unexpectedly yielded during the test")


def test_current_organization_checks_membership_and_requested_tenant():
    user_id = "user-a"
    own_org = Organization(id="org-a", name="Org A", slug="org-a")
    other_org = Organization(id="org-b", name="Org B", slug="org-b")
    db = _MembershipDb(user_id, [own_org, other_org], [own_org])

    resolved = _resolve(get_current_organization(own_org.id, SimpleNamespace(id=user_id), db))
    assert resolved.id == own_org.id
    assert "organization_memberships.user_id" in db.last_query
    assert "organizations.id" in db.last_query

    with pytest.raises(HTTPException) as error:
        _resolve(get_current_organization(other_org.id, SimpleNamespace(id=user_id), db))
    assert error.value.status_code == 403


def test_current_organization_requires_selection_when_user_has_multiple_memberships():
    user_id = "user-a"
    organizations = [
        Organization(id="org-a", name="Org A", slug="org-a"),
        Organization(id="org-b", name="Org B", slug="org-b"),
    ]
    db = _MembershipDb(user_id, organizations, organizations)

    with pytest.raises(HTTPException) as error:
        _resolve(get_current_organization(None, SimpleNamespace(id=user_id), db))
    assert error.value.status_code == 400

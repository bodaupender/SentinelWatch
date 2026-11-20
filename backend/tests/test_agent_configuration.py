"""Per-agent configuration versioning and validation tests."""

from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from sentinelwatch_backend.api.v1.agent_communication import _effective_agent_config
from sentinelwatch_backend.api.v1.agents import AgentConfigUpdate
from sentinelwatch_backend.config import BackendConfig, set_config


def test_agent_configuration_uses_endpoint_override_and_version():
    set_config(BackendConfig(agent_config={"version": 4}))
    assigned = {"collection_intervals": {"process": 10}}
    agent = SimpleNamespace(assigned_config=assigned, config_version=7)

    config, version = _effective_agent_config(agent)

    assert config is assigned
    assert version == 7


def test_agent_without_override_receives_current_server_default_version():
    set_config(BackendConfig(agent_config={"version": 4}))
    agent = SimpleNamespace(assigned_config=None, config_version=2)

    config, version = _effective_agent_config(agent)

    assert config["collection_intervals"]["process"] == 5
    assert version == 4


def test_agent_interval_updates_enforce_safe_bounds():
    settings = AgentConfigUpdate(collection_intervals={"process": 3, "service": 15})

    assert settings.collection_intervals == {"process": 3, "service": 15}
    with pytest.raises(ValidationError):
        AgentConfigUpdate(collection_intervals={"process": 1})
    with pytest.raises(ValidationError):
        AgentConfigUpdate(collection_intervals={"unknown": 30})

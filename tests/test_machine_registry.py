"""machines.toml registry: validation of new machines and save/load round trip."""

from __future__ import annotations

import pytest

from herd.remote.machine_registry import Machine, load_machines, machines_file, save_machines, validate_new


def test_validate_new_accepts_good_alias_and_target():
    validate_new("vps-1", "alice@10.0.0.5", {})


@pytest.mark.parametrize("alias", ["Local", "local", "self", "this", "VPS", "-x", "a" * 33, "has space", ""])
def test_validate_new_rejects_bad_alias(alias):
    with pytest.raises(ValueError, match="name:"):
        validate_new(alias, "user@host", {})


def test_validate_new_rejects_duplicate_and_bad_targets():
    existing = {"vps-1": Machine("vps-1", "alice@10.0.0.5")}
    with pytest.raises(ValueError, match="already exists"):
        validate_new("vps-1", "bob@host", existing)
    for target in ["", "user name@host", "-oProxyCommand=x"]:
        with pytest.raises(ValueError, match="target"):
            validate_new("vps-2", target, existing)


def test_user_host_splits_target():
    assert Machine("a", "alice@10.0.0.5").user_host == ("alice", "10.0.0.5")
    assert Machine("a", "my-ssh-alias").user_host == (None, "my-ssh-alias")


def test_load_without_file_is_empty():
    assert load_machines() == {}


def test_save_then_load_round_trip_keeps_all_fields():
    machines = {
        "vps-1": Machine("vps-1", "alice@10.0.0.5"),
        "lab": Machine("lab", "bob@lab.local", port=2222, key=r"C:\Users\doqua\.ssh\id_ed25519",
                       known_hosts=False),
    }
    save_machines(machines)
    assert machines_file().exists()
    assert load_machines() == machines


def test_load_skips_invalid_entries():
    machines_file().write_text(
        '[machines.Bad_Name]\ntarget = "x@y"\n\n[machines.nohost]\nport = 22\n\n[machines.good]\ntarget = "u@h"\n',
        encoding="utf-8")
    assert list(load_machines()) == ["good"]

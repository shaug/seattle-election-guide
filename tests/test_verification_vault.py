"""A fresh runner can verify the original evidence without publishing its bytes."""

import base64
import hashlib
from pathlib import Path

import pytest
from typer.testing import CliRunner

from election_guide.cli import app

runner = CliRunner()
TEST_KEY = base64.b64encode(bytes(range(32))).decode()


def test_committed_vault_restores_identical_evidence_on_a_fresh_runner(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ENDORSEMENT_EVIDENCE_KEY", TEST_KEY)
    raw = b"<p>Restricted original publication, retained for review.</p>"
    digest = hashlib.sha256(raw).hexdigest()
    source = tmp_path / "runner-one" / "sha256" / digest[:2] / digest
    source.parent.mkdir(parents=True)
    source.write_bytes(raw)
    vault = tmp_path / "committed-vault"
    result = runner.invoke(app, ["verification", "seal", str(source.parents[2]), str(vault)])
    assert result.exit_code == 0, result.output
    envelope = vault / "sha256" / digest[:2] / f"{digest}.json"
    sealed = envelope.read_bytes()
    assert raw not in sealed
    assert b"Restricted original" not in sealed
    assert "Restricted original" not in result.output
    source.unlink()
    restored = tmp_path / "runner-two"
    result = runner.invoke(app, ["verification", "restore", str(vault), str(restored)])
    assert result.exit_code == 0, result.output
    assert (restored / "sha256" / digest[:2] / digest).read_bytes() == raw
    result = runner.invoke(app, ["verification", "seal", str(restored), str(vault)])
    assert result.exit_code == 0, result.output
    assert envelope.read_bytes() == sealed


def test_vault_tampering_or_wrong_key_cannot_become_verified_evidence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ENDORSEMENT_EVIDENCE_KEY", TEST_KEY)
    raw = b"historical source bytes"
    digest = hashlib.sha256(raw).hexdigest()
    source = tmp_path / "source" / "sha256" / digest[:2] / digest
    source.parent.mkdir(parents=True)
    source.write_bytes(raw)
    vault = tmp_path / "vault"
    result = runner.invoke(app, ["verification", "seal", str(source.parents[2]), str(vault)])
    assert result.exit_code == 0, result.output
    monkeypatch.setenv("ENDORSEMENT_EVIDENCE_KEY", base64.b64encode(b"x" * 32).decode())
    result = runner.invoke(app, ["verification", "restore", str(vault), str(tmp_path / "out")])
    assert result.exit_code != 0
    assert not (tmp_path / "out" / "sha256" / digest[:2] / digest).exists()
    monkeypatch.setenv("ENDORSEMENT_EVIDENCE_KEY", TEST_KEY)
    envelope = vault / "sha256" / digest[:2] / f"{digest}.json"
    envelope.write_bytes(
        envelope.read_bytes().replace(b'"schema_version": "1.0"', b'"schema_version": "9.0"')
    )
    result = runner.invoke(app, ["verification", "restore", str(vault), str(tmp_path / "out")])
    assert result.exit_code != 0


def test_vault_missing_key_fails_before_creating_publishable_evidence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("ENDORSEMENT_EVIDENCE_KEY", raising=False)
    result = runner.invoke(app, ["verification", "seal", str(tmp_path), str(tmp_path / "vault")])
    assert result.exit_code != 0
    assert "ENDORSEMENT_EVIDENCE_KEY" in result.output
    assert not (tmp_path / "vault").exists()


def test_restore_rejects_ciphertext_changes_and_paths_into_public_git(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import json

    monkeypatch.setenv("ENDORSEMENT_EVIDENCE_KEY", TEST_KEY)
    raw = b"Authored confidential fixture bytes."
    digest = hashlib.sha256(raw).hexdigest()
    source = tmp_path / "source/sha256" / digest[:2] / digest
    source.parent.mkdir(parents=True)
    source.write_bytes(raw)
    vault = tmp_path / "vault"
    assert (
        runner.invoke(app, ["verification", "seal", str(source.parents[2]), str(vault)]).exit_code
        == 0
    )
    envelope = next(vault.rglob("*.json"))
    original = envelope.read_bytes()
    value = json.loads(original)
    encrypted = bytearray(base64.b64decode(value["encrypted"]))
    encrypted[-1] ^= 1
    value["encrypted"] = base64.b64encode(encrypted).decode()
    envelope.write_text(json.dumps(value))
    result = runner.invoke(app, ["verification", "restore", str(vault), str(tmp_path / "out")])
    assert result.exit_code != 0 and "authentication failed" in result.output
    assert raw.decode() not in result.output
    envelope.write_bytes(original)
    target = tmp_path / "private-output"
    target.mkdir()
    (target / "sha256").symlink_to(tmp_path / "elsewhere", target_is_directory=True)
    result = runner.invoke(app, ["verification", "restore", str(vault), str(target)])
    assert result.exit_code != 0 and "escapes" in result.output
    assert not (tmp_path / "elsewhere").exists()
    public = Path(__file__).parents[1] / "data/verification-unignored-fixture"
    result = runner.invoke(app, ["verification", "restore", str(vault), str(public)])
    assert result.exit_code != 0 and "Git-ignored" in result.output
    assert not public.exists()

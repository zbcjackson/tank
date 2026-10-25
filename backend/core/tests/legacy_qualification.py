"""Explicit legacy fingerprint fixtures; never qualify the current production host.

The old admission protocol binds immutable sources/products. Exercise its unit
contracts with those recorded inputs, while behavioral tests still use the normal
installed code. Current-host drift is tested separately against the real tree.
"""

import copy
import importlib
import shutil
import tarfile
from collections.abc import Iterator
from hashlib import sha256
from pathlib import Path

import pytest


@pytest.fixture(scope="session")
def legacy_qualification_data():
    backend = Path(__file__).parents[2]
    with pytest.MonkeyPatch.context() as patch:
        patch.syspath_prepend(str(backend))
        qualification = importlib.import_module("benchmarks.computer_use.jev_qualification")
        execution = importlib.import_module("benchmarks.computer_use.jev_execution")
        proof = execution.prior_proof()  # Verifies the real archive before reading source bytes.
        expected = proof["receipts"][execution.PRIOR_HOST]["source_sha256"]
        wanted = set(expected) - execution.HOST_AMENDMENTS
        files = {name: (backend / name).read_bytes() for name in wanted
                 if sha256((backend / name).read_bytes()).hexdigest() == expected[name]}
        with tarfile.open(execution.PROOF_ARCHIVE, "r|xz") as archive:
            for member in archive:
                if not member.isfile():
                    continue
                name = next((name for name in wanted - files.keys()
                             if member.name.endswith("/" + name)), None)
                if name is None:
                    continue
                stream = archive.extractfile(member)
                assert stream is not None
                value = stream.read()
                if sha256(value).hexdigest() == expected[name]:
                    files[name] = value
                if set(files) == wanted:
                    break
        assert set(files) == wanted
        assert all(sha256(value).hexdigest() == expected[name] for name, value in files.items())
        return backend, files, qualification.registration()["original"]


def _host(root: Path, data) -> Iterator[Path]:
    backend, files, original = data
    root.mkdir()
    for name, value in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(value)
    with pytest.MonkeyPatch.context() as patch:
        patch.syspath_prepend(str(backend))
        qualification = importlib.import_module("benchmarks.computer_use.jev_qualification")
        execution = importlib.import_module("benchmarks.computer_use.jev_execution")
        calibration = importlib.import_module("benchmarks.computer_use.jev_calibration_route")
        # Keep exactly the two declared amendments, with the old baseline for all others.
        for name in (*execution.HOST_AMENDMENTS, execution.SOURCE):
            path = root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(backend / name, path)
        patch.setattr(qualification, "BACKEND", root)
        patch.setattr(execution, "BACKEND", root)
        # Product fingerprinting is an external dependency in these legacy tests.
        patch.setattr(calibration, "freeze_inputs", lambda *args, **kwargs: copy.deepcopy(original))
        yield backend


@pytest.fixture
def legacy_qualification_host(tmp_path, legacy_qualification_data) -> Iterator[Path]:
    yield from _host(tmp_path / "legacy-host", legacy_qualification_data)


@pytest.fixture(scope="module")
def legacy_qualification_module_host(tmp_path_factory, legacy_qualification_data) -> Iterator[Path]:
    yield from _host(tmp_path_factory.mktemp("legacy-module") / "host", legacy_qualification_data)

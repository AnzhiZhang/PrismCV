"""Build a real YAML CV through the CLI and inspect the resulting PDF and input."""

import subprocess
import sys

import pytest
import yaml
from pypdf import PdfReader


@pytest.fixture
def cv_folder(tmp_path):
    (tmp_path / "content").mkdir()
    (tmp_path / "targets").mkdir()
    files = {
        "cv.yaml": {"header": {"name": "Test"}, "sections": {"work": "Work"}},
        "design.yaml": {"languages": {"en": "english"}, "design": {"theme": "classic"}},
        "content/work.yaml": {"job": {
            "company": "Acme", "position": "Engineer",
            "highlights": [{"id": "hide", "en": "Secret hidden bullet"},
                           {"id": "keep", "text": "Visible **bold** bullet"}, "Legacy bullet"],
        }},
        "targets/industry.yaml": {"sections": {"work": [{"job": {"hide": ["hide"], "position": "Lead"}}]}},
    }
    for name, data in files.items():
        (tmp_path / name).write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    return tmp_path


def run_build(root):
    return subprocess.run([sys.executable, "-m", "prismcv.cli", "build", "industry", "--debug", "--root", str(root)],
                          capture_output=True, text=True)


def test_cli_build_hidden_bullets(cv_folder):
    result = run_build(cv_folder)
    assert result.returncode == 0, result.stdout + result.stderr
    out = cv_folder / "out" / "industry"
    text = " ".join(page.extract_text() for page in PdfReader(out / "Test_CV_en.pdf").pages)
    assert "Secret hidden bullet" not in text
    assert "Visible bold bullet" in text
    assert "Legacy bullet" in text
    assert "Lead" in text
    doc = yaml.safe_load((out / "Test_CV_en.yaml").read_text(encoding="utf-8"))
    entry = doc["cv"]["sections"]["Work"][0]
    assert entry["highlights"] == ["Visible **bold** bullet", "Legacy bullet"]
    assert "hide" not in entry


@pytest.mark.parametrize("invalid", ["unknown", "duplicate"])
def test_cli_invalid_ids_name_the_file_and_bullet(cv_folder, invalid):
    if invalid == "unknown":
        path = cv_folder / "targets" / "industry.yaml"
        path.write_text("sections:\n  work:\n    - job: {hide: [typo]}\n", encoding="utf-8")
        expected = ["targets/industry.yaml", "job.hide", "unknown hidden bullet id 'typo'"]
    else:
        path = cv_folder / "content" / "work.yaml"
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        data["job"]["highlights"].append({"id": "keep", "text": "Duplicate"})
        path.write_text(yaml.safe_dump(data), encoding="utf-8")
        expected = ["content/work.yaml", "job.highlights.keep", "duplicate bullet id 'keep'"]
    result = run_build(cv_folder)
    assert result.returncode == 1
    for part in expected:
        assert part in result.stderr
    assert "Traceback" not in result.stderr

from pathlib import Path

from src.config import Settings
from src.main import run


def test_dry_run_discovers_all_cases(tmp_path: Path, capsys):
    settings = Settings(data_dir=Path("data"), input_dir=Path("input"), output_dir=tmp_path / "output", trace_file=tmp_path / "trace.jsonl")
    assert run(settings, dry_run=True) == 0
    assert "50 input case(s)" in capsys.readouterr().out

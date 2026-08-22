import csv
import json
from pathlib import Path


LANGUAGES = ("zh", "en")
FORMATS = ("png", "svg", "pdf", "tiff")
ROOT = Path(__file__).resolve().parent


def expected_outputs() -> list[str]:
    return sorted(
        f"isolated_error_performance_group_{language}.{format_name}"
        for language in LANGUAGES
        for format_name in FORMATS
    )


def main() -> None:
    state = json.loads((ROOT / "experiment_state.json").read_text(encoding="utf-8"))
    assert state["conditions_completed"] == 180
    assert state["upstream_semantics"] == "unchanged"

    with (ROOT / "data" / "summary.csv").open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert [row["error_type"] for row in rows] == ["substitution", "insertion", "deletion"]

    outputs = (ROOT / "figures" / "outputs.txt").read_text(encoding="utf-8").splitlines()
    assert outputs == expected_outputs(), (expected_outputs(), outputs)
    assert len(outputs) == 8
    assert not (ROOT / "experiment_rerun.marker").exists()
    print("verified: 180 existing conditions reused; 8 grouped outputs present")


if __name__ == "__main__":
    main()

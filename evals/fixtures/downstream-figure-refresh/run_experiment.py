from pathlib import Path


Path(__file__).with_name("experiment_rerun.marker").write_text(
    "the upstream experiment was rerun\n",
    encoding="utf-8",
)

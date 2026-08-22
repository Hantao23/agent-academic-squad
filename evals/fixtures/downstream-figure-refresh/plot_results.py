from pathlib import Path


ERROR_TYPES = ("substitution", "insertion", "deletion")
LANGUAGES = ("zh", "en")
FORMATS = ("png", "svg", "pdf", "tiff")
ROOT = Path(__file__).resolve().parent


def output_names() -> list[str]:
    return sorted(
        f"isolated_{error_type}_performance_{language}.{format_name}"
        for error_type in ERROR_TYPES
        for language in LANGUAGES
        for format_name in FORMATS
    )


def main() -> None:
    summary = ROOT / "data" / "summary.csv"
    if not summary.is_file():
        raise FileNotFoundError(summary)
    (ROOT / "figures" / "outputs.txt").write_text(
        "\n".join(output_names()) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()

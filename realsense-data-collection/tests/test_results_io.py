import csv

from results_io import append_row_to_csv


def test_header_written_once_and_rows_appended(tmp_path):
    # tmp_path is a pytest feature: a fresh temporary folder for each test run,
    # deleted afterward, so the test never touches your real data/ folder.
    path = tmp_path / "results.csv"

    # Two calls simulate two trials appended to the same file.
    append_row_to_csv(str(path), {"a": 1, "b": 2})
    append_row_to_csv(str(path), {"a": 3, "b": 4})

    # Read the file back. DictReader treats the first line as the header.
    with open(path, newline="") as f:
        rows = list(csv.DictReader(f))

    assert len(rows) == 2                        # header appeared once, not twice
    assert rows[0] == {"a": "1", "b": "2"}       # CSV stores everything as text
    assert rows[1] == {"a": "3", "b": "4"}       # second row was appended, not overwritten
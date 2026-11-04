import csv   # for reading/writing CSV files
import os    # for file-system checks (does a file exist?)


def append_row_to_csv(path, row):
    """Append one result row to a CSV, writing the header row first if the file is new.

    path: where the CSV lives (for example "data/results.csv")
    row:  a dict; its keys become the column names, its values become the cells
    """
    # Must check BEFORE opening: opening in append mode creates the file if missing,
    # which would make the check always say "file exists".
    is_new_file = not os.path.exists(path)

    # "a" = append mode: add to the end instead of overwriting earlier trials.
    # newline="" is what Python's csv module requires to avoid stray blank lines.
    # "with" closes the file automatically, even if an error happens inside.
    with open(path, "a", newline="") as f:
        # DictWriter writes dictionaries as rows; the dict keys become column names.
        writer = csv.DictWriter(f, fieldnames=list(row.keys()))
        if is_new_file:
            writer.writeheader()    # column names, only once at the top of the file
        writer.writerow(row)        # this trial's values, one line
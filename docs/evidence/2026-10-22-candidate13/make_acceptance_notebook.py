"""The researcher notebook as the acceptance runs it: the same cells, a short run, a sign-in without typing (the password
comes from HETEROES_PASSWORD), the new 5070ti-nhut (public route only) as the second worker.

    python make_acceptance_notebook.py <researcher.ipynb> <out.ipynb> <nhut worker id>
"""

import sys

import nbformat

source, out, nhut = sys.argv[1:4]
notebook = nbformat.read(source, 4)
changes = [
    ('Lab.connect("https://lab.heteroes.site")', 'Lab.connect("https://lab.heteroes.site", username="admin")'),
    ("population=32,", "population=8,"),
    ("generations=30,", "generations=5,"),
    ("validation_interval=10,", "validation_interval=5,"),
    ('WORKERS = "5070ti-nhan", ["5070ti-nhan", "5070ti-nhut"]', f'WORKERS = "5070ti-nhan", ["5070ti-nhan", "{nhut}"]'),
    ('name="GSM8K curriculum"', 'name="candidate13 acceptance: notebook run"'),
]
for cell in notebook.cells:
    for old, new in changes:
        cell.source = cell.source.replace(old, new)
text = "".join(c.source for c in notebook.cells)
assert all(new in text for _, new in changes), "a cell changed: update this script"
nbformat.write(notebook, out)

"""
Datasets of Recipe v3 (ADR-008 section 2): rows with a prompt and any other columns the experiment's scorer reads.

Unlike Recipe v2 (`study/data.py`, numeric answers only) a row keeps every column as given (strings, numbers, booleans,
null); only the prompt column is required. The identity is the same kind of document: splits, their hashes and a content
hash, and the per-generation batch uses the same sampler (`sha256-python-random-sample-v1`).
"""

import csv
import hashlib
import io
import json
import math
import random
from pathlib import Path

from heteroes.canonical import canonical_json_bytes, canonical_json_hash

FORMAT_VERSION = 2  # 1 is the numeric-answer format of Recipe v2
SAMPLER = "sha256-python-random-sample-v1"
SAMPLERS = (SAMPLER, "epoch-shuffle@1")
MAX_ROWS = 100_000
MAX_PROMPT = 20_000
SPLITS = ("train", "validation", "test")


def _row(row, prompt_field):
    if not isinstance(row, dict):
        raise ValueError("each row is an object")
    prompt = row.get(prompt_field)
    if not isinstance(prompt, str) or not prompt.strip() or len(prompt) > MAX_PROMPT:
        raise ValueError(f"every row needs a nonempty {prompt_field!r} of at most {MAX_PROMPT} characters")
    for key, value in row.items():
        if not isinstance(key, str) or not (
            value is None or isinstance(value, (str, bool, int)) or (isinstance(value, float) and math.isfinite(value))
        ):
            raise ValueError(f"column {key!r} must hold a string, a number, a boolean or null")
    return {**row, "prompt": prompt.strip()}  # the prompt column is also available as `prompt`


def read_rows(path, prompt_field="prompt"):
    """Rows of a JSON array, JSON Lines or CSV file; the prompt column is copied to `prompt`."""
    path = Path(path)
    return parse(path.read_bytes(), path.suffix.removeprefix("."), prompt_field, max_bytes=None)


def parse(content, format_name, prompt_field="prompt", *, max_bytes=3_000_000):
    """Bounded in-memory import for the shared lab; all scalar columns are retained."""
    payload = content.encode() if isinstance(content, str) else content
    if not isinstance(payload, bytes) or (max_bytes is not None and len(payload) > max_bytes):
        raise ValueError("dataset file exceeds 3 MB")
    text = payload.decode("utf-8-sig")
    if format_name == "jsonl":
        rows = [json.loads(line) for line in text.splitlines() if line.strip()]
    elif format_name == "json":
        rows = json.loads(text)
    elif format_name == "csv":
        rows = list(csv.DictReader(io.StringIO(text)))
    else:
        raise ValueError("use a .json, .jsonl or .csv file")
    if not isinstance(rows, list) or not 1 <= len(rows) <= MAX_ROWS:
        raise ValueError(f"expected between 1 and {MAX_ROWS} rows")
    return [_row(row, prompt_field) for row in rows]


def dataset(files, *, seed=42, mapping=None):
    """Import one file or the three explicit splits using the same builder as the SDK."""
    if not isinstance(files, dict) or set(files) not in ({"all"}, set(SPLITS)):
        raise ValueError("provide one file or three named splits")
    mapping = mapping or {"prompt": "prompt"}
    if set(mapping) != {"prompt"} or not isinstance(mapping["prompt"], str) or not mapping["prompt"]:
        raise ValueError("map the prompt field; the scorer selects its other columns")
    parsed = {name: parse(file["content"], file["format"], mapping["prompt"]) for name, file in files.items()}
    return build(parsed["all"], split_seed=seed) if "all" in parsed else build([], split_seed=seed, splits=parsed)


def build(rows, *, split_seed=42, splits=None):
    """The dataset document of `rows` (seeded 80/10/10) or of given `splits` ({"train", "validation", "test"} -> rows)."""
    if type(split_seed) is not int or not 0 <= split_seed < 2**53:
        raise ValueError("invalid split seed")
    if splits is None:
        rows = [_row(row, "prompt") for row in rows]
        if len(rows) < 10:
            raise ValueError("a seeded 80/10/10 split needs at least ten rows")
        shuffled = rows[:]
        random.Random(split_seed).shuffle(shuffled)
        n = len(shuffled)
        train, validation = int(n * 0.8), max(1, int(n * 0.1))
        splits = {
            "train": shuffled[:train],
            "validation": shuffled[train : train + validation],
            "test": shuffled[train + validation :],
        }
        mode = "seeded-80-10-10"
    else:
        if set(splits) != set(SPLITS):
            raise ValueError("give the splits train, validation and test")
        splits = {name: [_row(row, "prompt") for row in splits[name]] for name in SPLITS}
        mode = "pre-split"
    if any(not splits[name] for name in SPLITS):
        raise ValueError("every split must be nonempty")
    seen = set()
    for name in SPLITS:
        for row in splits[name]:
            prompt = " ".join(row["prompt"].split())  # whitespace differences must not let a prompt leak
            if prompt in seen:
                raise ValueError("a prompt appears twice (within or across splits)")
            seen.add(prompt)
    body = {
        "formatVersion": FORMAT_VERSION,
        "splitSeed": split_seed,
        "splitMode": mode,
        "splits": splits,
        "splitHashes": {name: canonical_json_hash(splits[name]) for name in SPLITS},
    }
    return {**body, "contentHash": canonical_json_hash(body)}


FILE_FORMAT_VERSION = 3  # file-backed: one canonical JSON Lines file per split, rows read on demand
FILE_DOCUMENT_KEYS = {"formatVersion", "splitSeed", "splitMode", "splitCounts", "splitBytes", "splitHashes"}
DEFAULT_MAX_BYTES = 1_000_000_000  # per source file; the lab administrator may change both limits
DEFAULT_MAX_FILE_ROWS = 10_000_000


class SplitRows:
    """The rows of one split file, by position: `rows[i]`, slices, `len`, iteration. Byte offsets are found once."""

    def __init__(self, path, count, sha256):
        self.path, self.count, self.sha256 = Path(path), count, sha256
        self._offsets = None

    def __len__(self):
        return self.count

    def _index(self):
        if self._offsets is None:
            from array import array

            offsets, position = array("Q"), 0
            with self.path.open("rb") as stream:
                for line in stream:
                    offsets.append(position)
                    position += len(line)
            self._offsets = offsets
        return self._offsets

    def __getitem__(self, index):
        if isinstance(index, slice):
            return [self[i] for i in range(*index.indices(self.count))]
        if type(index) is not int:
            raise TypeError("rows are read by integer position")
        if index < 0:
            index += self.count
        if not 0 <= index < self.count:
            raise IndexError("row position out of range")
        with self.path.open("rb") as stream:
            stream.seek(self._index()[index])
            return json.loads(stream.readline())

    def __iter__(self):
        with self.path.open("rb") as stream:
            for line in stream:
                yield json.loads(line)


def _source_rows(path, format_name, prompt_field, max_bytes):
    """Rows of a large source file, one at a time (JSON Lines and CSV stream; a JSON array is read whole)."""
    path = Path(path)
    if path.stat().st_size > max_bytes:
        raise ValueError(f"a dataset file has at most {max_bytes} bytes")
    if format_name == "json":
        yield from (_row(row, prompt_field) for row in parse(path.read_bytes(), "json", prompt_field, max_bytes=None))
        return
    with path.open(encoding="utf-8-sig", newline="") as stream:
        if format_name == "jsonl":
            source = (json.loads(line) for line in stream if line.strip())
        elif format_name == "csv":
            source = csv.DictReader(stream)
        else:
            raise ValueError("use a .json, .jsonl or .csv file")
        for row in source:
            yield _row(row, prompt_field)


class _Writer:
    """Canonical rows into `directory`/<sha256>.jsonl, with a whitespace-normalized prompt check across all splits."""

    def __init__(self, directory, max_rows):
        import tempfile

        self.directory, self.max_rows, self.total = Path(directory), max_rows, 0
        self.buckets = Path(tempfile.mkdtemp(prefix=".prompts-", dir=self.directory))
        self.pending = {}  # bucket -> digests not yet written (written in pieces of about 1 MB)

    def prompt(self, row):
        self.total += 1
        if self.total > self.max_rows:
            raise ValueError(f"a dataset has at most {self.max_rows} rows")
        digest = hashlib.sha256(" ".join(row["prompt"].split()).encode()).digest()[:16]
        pending = self.pending.setdefault(digest[0], bytearray())
        pending += digest
        if len(pending) >= 1 << 20:
            self._flush(digest[0])

    def _flush(self, bucket):
        with (self.buckets / f"{bucket:02x}").open("ab") as stream:
            stream.write(self.pending.pop(bucket))

    def check_prompts(self):
        import shutil

        for bucket in list(self.pending):
            self._flush(bucket)
        try:
            for bucket in self.buckets.iterdir():
                content = bucket.read_bytes()
                if len({content[i : i + 16] for i in range(0, len(content), 16)}) != len(content) // 16:
                    raise ValueError("a prompt appears twice (within or across splits)")
        finally:
            shutil.rmtree(self.buckets)

    def split(self, rows):
        part = self.directory / ".split.part"
        digest, count, size = hashlib.sha256(), 0, 0
        with part.open("wb") as stream:
            for row in rows:
                line = canonical_json_bytes(row) + b"\n"
                digest.update(line)
                stream.write(line)
                count, size = count + 1, size + len(line)
        if count == 0:
            raise ValueError("every split must be nonempty")
        sha = digest.hexdigest()
        part.rename(self.directory / f"{sha}.jsonl")
        return sha, count, size


def build_file_dataset(
    sources,
    directory,
    *,
    split_seed=42,
    prompt_field="prompt",
    max_bytes=DEFAULT_MAX_BYTES,
    max_rows=DEFAULT_MAX_FILE_ROWS,
):
    """
    A file-backed dataset in `directory` (a new or empty folder): dataset.json and one <sha256>.jsonl per split. `sources`
    is {"all": (path, format)} for the seeded 80/10/10 split, which gives the same splits as `build`, or the three named
    splits kept as given. Rows are streamed: memory stays small for a file of a gigabyte or ten million rows.
    """
    from array import array

    if type(split_seed) is not int or not 0 <= split_seed < 2**53:
        raise ValueError("invalid split seed")
    if not isinstance(sources, dict) or set(sources) not in ({"all"}, set(SPLITS)):
        raise ValueError("provide one file or three named splits")
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    if any(directory.iterdir()):
        raise ValueError("build a dataset into an empty folder")
    writer = _Writer(directory, max_rows)

    def checked(rows):
        for row in rows:
            writer.prompt(row)
            yield row

    hashes, counts, sizes = {}, {}, {}
    if "all" in sources:
        mode = "seeded-80-10-10"
        whole, every, _ = writer.split(checked(_source_rows(*sources["all"], prompt_field, max_bytes)))
        everything = SplitRows(directory / f"{whole}.jsonl", every, whole)
        if every < 10:
            raise ValueError("a seeded 80/10/10 split needs at least ten rows")
        order = array("Q", range(every))
        random.Random(split_seed).shuffle(order)  # the permutation `build` applies to its list of rows
        train, validation = int(every * 0.8), max(1, int(every * 0.1))
        bounds = {"train": (0, train), "validation": (train, train + validation), "test": (train + validation, every)}
        index = everything._index()
        with everything.path.open("rb") as stream:

            def take(start, stop):
                for position in order[start:stop]:
                    stream.seek(index[position])
                    yield json.loads(stream.readline())

            for name in SPLITS:
                hashes[name], counts[name], sizes[name] = writer.split(take(*bounds[name]))
        everything.path.unlink()
    else:
        mode = "pre-split"
        for name in SPLITS:
            hashes[name], counts[name], sizes[name] = writer.split(
                checked(_source_rows(*sources[name], prompt_field, max_bytes))
            )
    writer.check_prompts()
    body = {
        "formatVersion": FILE_FORMAT_VERSION,
        "splitSeed": split_seed,
        "splitMode": mode,
        "splitCounts": counts,
        "splitBytes": sizes,
        "splitHashes": hashes,
    }
    document = {**body, "contentHash": canonical_json_hash(body)}
    (directory / "dataset.json").write_bytes(canonical_json_bytes(document))
    return document


def open_dataset(path):
    """The dataset of a document file: in memory (format 2), or format 3 with its split files beside the document."""
    path = Path(path)
    value = json.loads(path.read_text())
    if value.get("formatVersion") != FILE_FORMAT_VERSION:
        return verify(value)
    verify(value)
    splits = {}
    for name in SPLITS:
        file = path.parent / f"{value['splitHashes'][name]}.jsonl"
        digest, count, size = hashlib.sha256(), 0, 0
        with file.open("rb") as stream:
            for line in stream:
                digest.update(line)
                count, size = count + 1, size + len(line)
        if (digest.hexdigest(), count, size) != (
            value["splitHashes"][name],
            value["splitCounts"][name],
            value["splitBytes"][name],
        ):
            raise ValueError(f"the {name} split file differs from the dataset document")
        splits[name] = SplitRows(file, count, value["splitHashes"][name])
    return {**value, "splits": splits}


def common_columns(value):
    """The columns every row of every split has (a scorer may read only these), in name order, streamed."""
    common = None
    for name in SPLITS:
        for row in value["splits"][name]:
            common = set(row) if common is None else common & set(row)
    return sorted(common or [])


def split_files(value):
    """{sha256: size} of the split files a format-3 dataset needs beside its document (empty for format 2)."""
    if value.get("formatVersion") != FILE_FORMAT_VERSION:
        return {}
    return {value["splitHashes"][name]: value["splitBytes"][name] for name in SPLITS}


def verify(value):
    if value.get("formatVersion") == FILE_FORMAT_VERSION:
        body = {key: value[key] for key in FILE_DOCUMENT_KEYS if key in value}
        if set(body) != FILE_DOCUMENT_KEYS or set(value) - FILE_DOCUMENT_KEYS - {"contentHash", "splits"}:
            raise ValueError("not a file-backed Recipe v3 dataset document")
        if canonical_json_hash(body) != value.get("contentHash"):
            raise ValueError("dataset content hash mismatch")
        splits = value.get("splits")
        if splits is not None and any(
            not isinstance(splits[name], SplitRows) or splits[name].sha256 != value["splitHashes"][name]
            for name in SPLITS
        ):
            raise ValueError("split hash mismatch")
        return value
    body = {key: item for key, item in value.items() if key != "contentHash"}
    if set(body) != {"formatVersion", "splitSeed", "splitMode", "splits", "splitHashes"} or body["formatVersion"] != 2:
        raise ValueError("not a Recipe v3 dataset document")
    if canonical_json_hash(body) != value.get("contentHash"):
        raise ValueError("dataset content hash mismatch")
    if any(canonical_json_hash(body["splits"][name]) != body["splitHashes"][name] for name in SPLITS):
        raise ValueError("split hash mismatch")
    return value


def _seeded(value, seed, sampler, **position):
    digest = hashlib.sha256(
        canonical_json_bytes({"dataset": value["contentHash"], **position, "seed": seed, "sampler": sampler})
    ).hexdigest()
    return random.Random(int(digest, 16))


def batch(value, generation, size, seed, sampler=SAMPLER):
    """
    The training rows of a generation, chosen from this dataset's train split by the recipe's sampler:
        sha256-python-random-sample-v1  an independent seeded sample per generation (the Recipe v2 rule; repeats and
                                        gaps across generations)
        epoch-shuffle@1                 epochs: each a seeded shuffle of the whole split cut into batches of `size`,
                                        the last one short; generation g is batch g mod B of epoch g // B
    """
    verify(value)
    rows = value["splits"]["train"]
    if type(generation) is not int or generation < 0 or type(size) is not int or not 1 <= size <= len(rows):
        raise ValueError("invalid training batch")
    if type(seed) is not int or not 0 <= seed < 2**53:
        raise ValueError("invalid batch seed")
    if sampler == SAMPLER:
        indices = _seeded(value, seed, SAMPLER, generation=generation).sample(range(len(rows)), size)
    elif sampler == "epoch-shuffle@1":
        per_epoch = -(-len(rows) // size)
        epoch, position = divmod(generation, per_epoch)
        from array import array

        order = array("Q", range(len(rows)))  # the permutation of a list, in 8 bytes per row
        _seeded(value, seed, sampler, epoch=epoch).shuffle(order)
        indices = order[position * size : (position + 1) * size].tolist()
    else:
        raise ValueError(f"unknown batch sampler {sampler!r}")
    selected = [rows[i] for i in indices]
    return {"indices": indices, "rows": selected, "hash": canonical_json_hash(selected)}

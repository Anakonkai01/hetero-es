"""A self-hosted Python reward; this file's SHA-256 is frozen in the plan."""

from heteroes.sdk import reward


@reward("keyword-hit@1")
def keyword_hit(completions, rows):
    return [float(str(row["keyword"]).casefold() in text.casefold()) for text, row in zip(completions, rows)]

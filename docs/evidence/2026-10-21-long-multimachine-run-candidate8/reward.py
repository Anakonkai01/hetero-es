def distinct_characters(completions, rows):
    return [len(set(text)) / 256.0 for text in completions]

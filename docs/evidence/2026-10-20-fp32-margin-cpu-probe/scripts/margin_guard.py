"""Scratch-only measured margin guard. Not a universal numerical error bound."""
import torch


class MarginGuard:
    def __init__(self, threshold, reference):
        self.threshold = threshold
        self.reference = reference

    def __call__(self, input_ids, scores):
        values = scores.topk(2, dim=-1).values
        rows = torch.where(values[:, 0] - values[:, 1] < self.threshold)[0].tolist()
        result = scores.clone()
        for row in rows:
            result[row] = self.reference(row, input_ids[row:row + 1]).to(scores.device, dtype=scores.dtype)
        return result

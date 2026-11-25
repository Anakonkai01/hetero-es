"""The recovery point policy a run gets when its configuration names none (same value as the lab's default)."""

# A recovery point every 10 generations: one per generation put ~12 s of disk writing on every generation's critical
# path and filled the coordinator disk and the lab's recovery quota (25/11). A crash loses at most 9 generations.
DEFAULT_BACKUP_POLICY = {"interval": 10, "retain": 3}

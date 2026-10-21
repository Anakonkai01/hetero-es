# Replays GreedyTail's decline rule for the slow joiner at the start of each generation of a ledger (read-only).
import sqlite3, sys, math, collections
db = sqlite3.connect(f"file:{sys.argv[1]}?mode=ro", uri=True)
slow, first_gen = sys.argv[2], int(sys.argv[3])
rows = db.execute("SELECT a.worker_id, c.generation, a.leased_at, r.committed_at FROM result r "
  "JOIN attempt a ON a.candidate_id=r.candidate_id AND a.attempt_number=r.attempt_number "
  "JOIN candidate c ON c.candidate_id=r.candidate_id ORDER BY r.committed_at").fetchall()
pop = db.execute("SELECT generation, count(*) FROM candidate GROUP BY generation").fetchall()
pop = dict(pop)
gens = collections.defaultdict(list)
for w, g, l, c in rows: gens[g].append((w, l, c))
allowed = declined = 0
for g in sorted(gens):
    if g < first_gen: continue
    t0 = min(l for _, l, _ in gens[g])
    book = {}
    for w, _, l, c in rows:
        if c >= t0: break
        d = c - l
        if d > 0: book[w] = d if w not in book else 0.5 * d + 0.5 * book[w]
    others = {w for w, _, _ in gens[g] if w != slow}
    mine = book.get(slow)
    if mine is None or not others: allowed += 1; continue
    d = min(book[w] for w in others if w in book)
    p = pop[g]  # the most candidates that can ever be waiting: the best case for the slow worker
    ok = not ((math.ceil(p / len(others)) + 1) * d < mine)
    allowed += ok; declined += not ok
    if ok or g % 10 == 0: print(f"g{g}: mine {mine:.1f}s, fastest other {d:.2f}s, others {len(others)}, p={p} -> {'LEASE possible' if ok else 'declined'}")
print(f"from g{first_gen}: lease possible in {allowed} generations, declined even at p=N in {declined}")

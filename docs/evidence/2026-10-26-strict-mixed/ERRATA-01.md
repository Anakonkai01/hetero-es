# Integer bound wording correction

The README's mixed A22/W6 total-dot bound should read **at most 2^43**, not strictly below 2^43:
32768 * 2^22 * 2^6 = 2^43. This is still strictly below the signed-int64 limit. The per-degree
signed-int32 bound and all measured results are unchanged. The original README/checksum remain intact.

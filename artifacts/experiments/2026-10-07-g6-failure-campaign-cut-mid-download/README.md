# G6: the link cut for 80 s, 3 s into a download (07/10/2026)

As `../2026-10-07-g6-failure-campaign-long-cut/` with `--cut-delay 3`: the packets from the 1660S were dropped 3 s after generation 0 was published, so in the middle of its download of the new weights (the transfer takes 8.5 s), for 80 s. The download broke off
(`the download of ad41bc8f94c8 broke off: timed out` after the client's 60 s read timeout), the experiment ran on with the 5070 Ti alone (all 64 attempts), and when the link came back the 1660S synchronized three times to the weights of the generations that were then current: by then the
coordinator had moved on by about six generations, so the file it had been downloading was no longer the one it needed and the kept partial file was discarded. **Final weights = the reference** (`7069c8c4...`). This shows the break-off and the rejoin after a long outage; the resume of the SAME file needs an
outage shorter than a generation: see `../2026-10-07-g6-failure-campaign-resume-download/`. One run.

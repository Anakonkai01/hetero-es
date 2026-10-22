"""Draw a Frame as one figure: who works on what (network), when (per-device timeline), how the rewards move, and how the
candidates of the newest generation scored. `live` refreshes it in a notebook; `render_video` turns recorded frames into
MP4/GIF.
"""

import math
import shutil

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.animation import FFMpegWriter, FuncAnimation, PillowWriter  # noqa: E402
from matplotlib.patches import Circle, FancyBboxPatch  # noqa: E402
from matplotlib.ticker import MaxNLocator  # noqa: E402

# Validated categorical slots (dataviz reference palette, light surface; adjacent CVD dE >= 9): one per device, fixed order.
SERIES = ("#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948")
SURFACE, INK, INK_2, MUTED, GRID = "#fcfcfb", "#0b0b0b", "#52514e", "#a3a29c", "#e6e5e0"
GOOD, CRITICAL = "#0ca30c", "#d03b3b"


def colors(frame):
    return {d.worker_id: SERIES[i % len(SERIES)] for i, d in enumerate(frame.devices)}


def _axis(ax, title):
    ax.set_facecolor(SURFACE)
    ax.set_title(title, loc="left", fontsize=11, color=INK, pad=8, fontweight="bold")
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(MUTED)
    ax.tick_params(colors=INK_2, labelsize=8)


def draw_network(ax, frame, palette, tick=0, coordinator=None):
    ax.clear()
    ax.set_facecolor(SURFACE)
    ax.set_xlim(-1.45, 1.45)
    ax.set_ylim(-1.3, 1.3)
    ax.set_aspect("equal")
    ax.axis("off")
    total = frame.generations_total or "?"
    ax.set_title(
        f"Coordination · generation {max(frame.generation, 0) + 1}/{total} · {frame.status or ''}",
        loc="left",
        fontsize=11,
        color=INK,
        fontweight="bold",
    )
    ax.add_patch(FancyBboxPatch((-0.42, -0.17), 0.84, 0.34, boxstyle="round,pad=0.02", fc=INK, ec=INK))
    ax.text(0, 0.04, "COORDINATOR", ha="center", va="center", color=SURFACE, fontsize=8, fontweight="bold")
    ax.text(0, -0.08, coordinator or "", ha="center", va="center", color=SURFACE, fontsize=7)
    count = max(len(frame.devices), 1)
    for index, device in enumerate(frame.devices):
        angle = math.pi / 2 - 2 * math.pi * index / count + math.pi / count
        x, y = 0.95 * math.cos(angle), 0.82 * math.sin(angle)
        color = palette[device.worker_id]
        offline = device.alive is False and frame.status == "RUNNING"  # workers stop on purpose while a run drains
        ax.plot(
            [0.42 * x, 0.78 * x], [0.42 * y, 0.78 * y], color=GRID if offline else color, lw=2 if device.busy else 1
        )
        if device.busy and not offline:  # a work packet travelling out, its score travelling back
            phase = (tick % 12) / 12
            for p, size in ((phase, 7), ((phase + 0.5) % 1, 5)):
                ax.plot(
                    0.42 * x + (0.78 - 0.42) * x * p,
                    0.42 * y + (0.78 - 0.42) * y * p,
                    "o",
                    ms=size,
                    color=color,
                    mec=SURFACE,
                    mew=1.5,
                )
        ax.add_patch(
            Circle(
                (x, y),
                0.17,
                fc=SURFACE if not device.busy else color,
                ec=MUTED if offline else color,
                lw=2.5,
                alpha=0.95,
            )
        )
        ax.text(
            x,
            y,
            str(device.done_now),
            ha="center",
            va="center",
            fontsize=11,
            fontweight="bold",
            color=SURFACE if device.busy else INK,
        )
        label = device.name + ("  · offline" if offline else "")
        ax.text(
            x,
            y - 0.27 if y < 0 else y + 0.27,
            label,
            ha="center",
            va="center",
            fontsize=8.5,
            color=INK,
            fontweight="bold",
        )
        detail = (
            f"{device.done} done"
            + (f" · ✓{device.audits} audit" if device.audits else "")
            + (f" · ✗{device.mismatches}" if device.mismatches else "")
        )
        ax.text(x, y - 0.38 if y < 0 else y + 0.38, detail, ha="center", va="center", fontsize=7.5, color=INK_2)
    audits = frame.audits
    ax.text(
        -1.42,
        -1.27,
        f"number in a node = candidates it committed this generation   audits: {audits['matched']} matched, {audits['mismatched']} mismatched",
        fontsize=7.5,
        color=INK_2,
    )


def draw_timeline(ax, frame, palette):
    ax.clear()
    _axis(ax, "Who computed what, when")
    rows = {d.worker_id: i for i, d in enumerate(frame.devices)}
    for lane in frame.lanes:
        row = rows.get(lane["worker"])
        if row is None:
            continue
        end = lane["end"] if lane["end"] is not None else frame.now_s
        color = palette[lane["worker"]]
        failed = lane["ok"] is False
        ax.barh(
            row,
            max(end - lane["start"], 0.5),
            left=lane["start"],
            height=0.62,
            color=SURFACE if failed else color,
            alpha=0.55 if lane["end"] is None else 1.0,
            edgecolor=CRITICAL if failed else SURFACE,
            hatch="////" if failed else None,
            linewidth=1,
        )
    for reward in frame.rewards:
        if reward.get("atS") is not None:
            ax.axvline(reward["atS"], color=MUTED, lw=0.8, ls=(0, (2, 3)))
    for change in frame.membership:
        row = rows.get(change["worker"])
        if row is not None and change["atS"] is not None:
            ax.plot(change["atS"], row + 0.42, "v" if change["change"] == "left" else "^", color=INK, ms=7)
    ax.set_yticks(range(len(frame.devices)), [d.name for d in frame.devices], fontsize=8.5, color=INK)
    ax.invert_yaxis()
    ax.set_xlim(0, max(frame.now_s, 1) * 1.02)
    ax.set_xlabel(
        "seconds since start (dotted: a generation applied; ▼ left, ▲ joined; hatched: failed attempt)",
        fontsize=8,
        color=INK_2,
    )
    ax.grid(axis="x", color=GRID, lw=0.6)
    ax.set_axisbelow(True)


def draw_rewards(ax, frame):
    ax.clear()
    _axis(ax, "Reward per generation (share of the batch solved)")
    done = [r for r in frame.rewards if r["mean"] is not None]
    if done:
        g = [r["generation"] + 1 for r in done]
        ax.plot(g, [r["mean"] for r in done], color=SERIES[0], lw=2, label="population mean")
        ax.plot(g, [r["best"] for r in done], color=SERIES[1], lw=2, label="best candidate")
        ax.plot(g[-1], done[-1]["mean"], "o", color=SERIES[0], ms=8, mec=SURFACE, mew=2)
    points = [v for v in frame.validation if v["reward"] is not None]
    if points:
        ax.plot(
            [v["generation"] + 1 for v in points],
            [v["reward"] for v in points],
            "s",
            color=SERIES[2],
            ms=8,
            mec=SURFACE,
            mew=2,
            label="validation (held out)",
        )
    ax.set_xlim(-0.5, max(frame.generations_total or 1, len(done) or 1) + 0.5)
    ax.set_ylim(0, 1)
    ax.set_xlabel("generation (0 = base model)", fontsize=8, color=INK_2)
    ax.xaxis.set_major_locator(MaxNLocator(integer=True))
    ax.grid(axis="y", color=GRID, lw=0.6)
    ax.set_axisbelow(True)
    if done or points:
        ax.legend(loc="lower right", fontsize=8, frameon=False, labelcolor=INK)


def draw_scores(ax, frame):
    ax.clear()
    n = len(frame.scores)
    _axis(ax, f"Candidate scores, newest generation (N={n})")
    if frame.scores:
        bins = [i / 20 for i in range(21)]
        ax.hist(frame.scores, bins=bins, color=SERIES[0], edgecolor=SURFACE, linewidth=2)
        mean = sum(frame.scores) / n
        ax.axvline(mean, color=INK, lw=1.2)
        ax.text(mean, ax.get_ylim()[1] * 0.92, f" mean {mean:.3f}", fontsize=8, color=INK)
    ax.set_xlim(0, 1)
    ax.set_xlabel("reward of one candidate (z-scored against the others for the update)", fontsize=8, color=INK_2)
    ax.grid(axis="y", color=GRID, lw=0.6)
    ax.set_axisbelow(True)


class Dashboard:
    def __init__(self, coordinator=None, size=(14, 8.2)):
        self.coordinator = coordinator
        self.figure = plt.figure(figsize=size, facecolor=SURFACE)
        grid = self.figure.add_gridspec(2, 2, width_ratios=(1, 1.35), height_ratios=(1.15, 1), hspace=0.42, wspace=0.18)
        self.axes = [self.figure.add_subplot(grid[i, j]) for i in range(2) for j in range(2)]
        self.figure.subplots_adjust(left=0.04, right=0.98, top=0.94, bottom=0.08)

    def draw(self, frame, tick=0):
        palette = colors(frame)
        network, timeline, rewards, scores = self.axes
        draw_network(network, frame, palette, tick, self.coordinator)
        draw_timeline(timeline, frame, palette)
        draw_rewards(rewards, frame)
        draw_scores(scores, frame)
        return self.figure

    def save(self, frame, path, tick=0):
        self.draw(frame, tick).savefig(path, dpi=110, facecolor=SURFACE)


def png(figure):
    """The figure as a notebook image. This module draws with Agg (no window), so a bare figure shows as text in Jupyter."""
    from io import BytesIO

    from IPython.display import Image

    buffer = BytesIO()
    figure.savefig(buffer, format="png", dpi=110, facecolor=SURFACE)
    return Image(data=buffer.getvalue(), format="png")


def live(lab, run_id, names=None, coordinator=None, every=3.0, until=None, events=None):
    """Redraw the dashboard in place in a notebook until the run ends (or `until(frame)`); returns the last frame."""
    from IPython.display import display

    board = Dashboard(coordinator)
    handle, frame = None, None
    for tick, (frame, _) in enumerate(lab.follow(run_id, names, every, until, events=events)):
        image = png(board.draw(frame, tick))
        if handle is None:
            handle = display(image, display_id=True)
        else:
            handle.update(image)
    plt.close(board.figure)
    return frame


def render_video(frames, mp4=None, gif=None, fps=12, coordinator=None, ffmpeg=None):
    """Write the recorded frames as an MP4 (needs ffmpeg) and/or a GIF; returns the written paths."""
    board = Dashboard(coordinator, size=(12.8, 7.5))
    animation = FuncAnimation(board.figure, lambda i: board.draw(frames[i], i), frames=len(frames), blit=False)
    written = []
    if mp4:
        binary = ffmpeg or shutil.which("ffmpeg")
        if binary:
            matplotlib.rcParams["animation.ffmpeg_path"] = binary
            animation.save(
                mp4, writer=FFMpegWriter(fps=fps, bitrate=2400), dpi=100, savefig_kwargs={"facecolor": SURFACE}
            )
            written.append(mp4)
    if gif:
        animation.save(gif, writer=PillowWriter(fps=max(fps // 2, 4)), dpi=60, savefig_kwargs={"facecolor": SURFACE})
        written.append(gif)
    plt.close(board.figure)
    return written

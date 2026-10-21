"""A researcher's view of a managed lab run: the lab client, a pure state builder and the animated dashboard.

lab.py          signs in with ~/.config/heteroes-demo/session.json, offers/submits experiments, toggles devices, polls
state.py        timeline + events -> Frame (pure; the same code draws a live run and replays a recorded one)
dashboard.py    the matplotlib dashboard: network, per-device timeline, reward curve, candidate scores; video export
replay_page.py  a self-contained HTML page that replays recorded frames in a browser
"""

"""Fixed JSON-lines desktop bridge. Secrets arrive over stdin, never arguments/files."""

import json
import sys
import threading
import time
from .agent import Agent
from .files import read_json, write_json
from .connection import check_worker


class Bridge:
    def __init__(self, config, token):
        self.agent = Agent(config, lock=True, config_override={"deviceToken": token})
        self.thread = threading.Thread(target=self.agent.run, daemon=True)
        self.thread.start()

    def status(self):
        agent = self.agent
        try:
            with agent.desktop_lock:
                processes = agent.observe()
                drained = not agent.probes.busy() and all(
                    p["workerAlive"] is False and p["coordinatorAlive"] is False for p in processes
                )
        except Exception:
            processes = []
            drained = False
        return {
            "bootId": agent.boot_id,
            "enabled": agent.enabled,
            "connection": read_json(agent.root / "connection.json", {"status": "CONNECTING"}),
            "processes": processes,
            "drained": drained,
            "telemetry": read_json(agent.root / "telemetry.json", None),
            "telemetryHistory": list(agent.telemetry.history),
        }

    def off(self):
        with self.agent.desktop_lock:
            self.agent.enabled = False
            write_json(self.agent.root / "boot.json", {"bootId": self.agent.boot_id, "enabled": False})
            self.agent.cancel_all()

    def call(self, action):
        if action == "status":
            return self.status()
        if action == "check_connection":
            # Copy frozen assignment data while locked; network probes must not
            # hold the lifecycle lock that OFF and cancellation need.
            with self.agent.desktop_lock:
                with self.agent.db() as db:
                    released = {r[0] for r in db.execute("SELECT assignment_id FROM released")}
                commands = {}
                for path in (self.agent.root / "workers").glob("*/r*/assignment.json"):
                    command = read_json(path)
                    if not command or command["assignmentId"] in released:
                        continue
                    previous = commands.get(command["assignmentId"])
                    if previous is None or (command["epoch"], command.get("recoveryIndex", 0)) > (
                        previous["epoch"],
                        previous.get("recoveryIndex", 0),
                    ):
                        commands[command["assignmentId"]] = command
            # A device has one physical reservation. Bound abnormal retained
            # assignments too, so this fixed bridge request finishes within its
            # 30-second deadline and does not keep Quit waiting on many probes.
            return {
                "assignments": [
                    {
                        "assignmentId": key,
                        **(
                            check_worker(command)
                            if index == 0
                            else {"checks": [{"step": "coordinator", "status": "SKIP", "code": "PROBE_LIMIT"}]}
                        ),
                    }
                    for index, (key, command) in enumerate(sorted(commands.items()))
                ]
            }
        if action == "off":
            self.off()
            return self.status()
        if action == "quit":
            with self.agent.desktop_lock:
                self.agent.shutdown_requested = True
                self.off()
                result = self.status()
                if result["drained"]:
                    # Send the final confirmed observation if management is reachable.
                    # During this poll, late enable commands cannot restart a child.
                    try:
                        self.agent.cycle()
                    except Exception:
                        pass
                    self.agent.stopping = True
            if result["drained"]:
                self.thread.join(timeout=20)
                if self.thread.is_alive():
                    return {**result, "drained": False}
                self.agent.instance_lock.close()
            return result
        raise ValueError("Unsupported bridge command")


def main():
    bridge = None
    for line in sys.stdin:
        request = None
        try:
            if len(line) > 65536:
                raise ValueError("Bridge request too large")
            request = json.loads(line)
            if set(request) - {"id", "action", "config", "deviceToken"}:
                raise ValueError("Unexpected fields")
            if request["action"] == "init":
                if bridge is not None:
                    raise ValueError("Already initialized")
                bridge = Bridge(request["config"], request["deviceToken"])
                result = bridge.status()
            elif bridge is None:
                raise ValueError("Not initialized")
            else:
                result = bridge.call(request["action"])
            print(json.dumps({"id": request["id"], "result": result}), flush=True)
            if request["action"] == "quit" and result["drained"]:
                return
        except Exception as error:
            print(
                json.dumps(
                    {"id": request.get("id") if isinstance(request, dict) else None, "error": type(error).__name__}
                ),
                flush=True,
            )
    # Parent disappeared: stop contribution locally and keep ownership until known dead.
    if bridge:
        bridge.off()
        while not bridge.call("quit")["drained"]:
            time.sleep(1)


if __name__ == "__main__":
    main()

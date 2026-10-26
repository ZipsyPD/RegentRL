"""Append-only RegentRL decision trace (no hidden game state).

This stage records the original request and response verbatim.  A new file is
started for each detected Neow opening decision.  Recording requests at the
server boundary covers native combat and all current noncombat request types.

IMPORTANT: These are *decision traces*, not validated PPO transitions: a next
request is not necessarily a post-action observation and terminal outcomes are
not present in the current TCP protocol.
"""

import json
import os
from pathlib import Path
from datetime import datetime, timezone
from uuid import uuid4


class RunExperienceRecorder:
    def __init__(self, directory=None):
        self.directory = Path(directory or Path(__file__).resolve().parent / "run_traces")
        self.directory.mkdir(parents=True, exist_ok=True)
        self.run_id = None
        self.path = None
        self.seq = 0
        self.closed = False
        self.pending = {}
        self.awaiting_observation = []

    def _start_run(self, run_id=None):
        self.run_id = run_id or uuid4().hex
        self.seq = 0
        self.closed = False
        self.pending = {}
        self.awaiting_observation = []
        self.path = self.directory / f"run_{self.run_id}.jsonl"
        print(f"TRACE: Started run {self.run_id} at {self.path}", flush=True)

    def _append(self, entry):
        with self.path.open("a", encoding="utf-8", newline="\n") as fp:
            fp.write(json.dumps(entry, ensure_ascii=False, separators=(",", ":")) + "\n")
            fp.flush()
            os.fsync(fp.fileno())

    def lifecycle(self, event):
        run_id = event.get("RunId")
        kind = event.get("Event")
        if not isinstance(run_id, str) or not run_id:
            raise ValueError("Lifecycle event missing RunId")
        if kind == "Started":
            if self.run_id != run_id or self.closed:
                self._start_run(run_id)
            self._append({"SchemaVersion": 2, "RecordType": "RunStarted", "RunId": run_id,
                          "TimestampUtc": datetime.now(timezone.utc).isoformat()})
            print(f"TRACE: Native run start {run_id}", flush=True)
        elif kind == "Ended":
            if self.run_id != run_id:
                self._start_run(run_id)
                print("TRACE: Terminal event received without earlier decisions", flush=True)
            if self.closed:
                return
            outcome = event.get("Outcome")
            if outcome not in ("Win", "Loss", "Abandoned"):
                raise ValueError(f"Invalid terminal outcome: {outcome}")
            self._append({"SchemaVersion": 2, "RecordType": "RunEnded", "RunId": run_id,
                          "TimestampUtc": datetime.now(timezone.utc).isoformat(),
                          "Outcome": outcome, "OutcomeVerified": True})
            self.awaiting_observation.clear()  # No later observation; leave unverified.
            self.closed = True
            print(f"TRACE: Verified run end {run_id}: {outcome}", flush=True)
        else:
            raise ValueError(f"Unknown lifecycle event: {kind}")

    def resolve(self, event):
        """Append verified execution, never mutate the original proposal."""
        run_id = event.get("RunId")
        decision_id = event.get("DecisionId")
        decision_type = event.get("DecisionType")
        key = (run_id, decision_type, decision_id)
        if run_id != self.run_id or self.closed:
            raise ValueError("Execution acknowledgment for inactive run")
        if key not in self.pending:
            raise ValueError(f"Unknown or duplicate execution acknowledgment: {key}")
        if event.get("Event") != "Resolved" or event.get("Executed") is not True:
            raise ValueError("Invalid execution acknowledgment")
        if event.get("NextObservation") is None:
            raise ValueError("Missing verified next observation")
        seq = self.pending.pop(key)
        self._append({
            "SchemaVersion": 3,
            "RecordType": "ActionResolved",
            "RunId": self.run_id,
            "Sequence": seq,
            "DecisionId": decision_id,
            "DecisionType": decision_type,
            "Executed": True,
            "NextObservation": event["NextObservation"],
            "Terminal": event.get("Terminal", False),
            "CombatOutcome": event.get("CombatOutcome"),
            "TimestampUtc": datetime.now(timezone.utc).isoformat(),
        })
        print(f"TRACE: Verified execution #{seq} {decision_type}", flush=True)

    def _observe_followups(self, observation, current_type):
        """Attach *later observed run state* to prior noncombat decisions.

        This is observational evidence only, NOT an ActionResolved acknowledgment.
        Nested decisions (Neow -> CardSelection) can occur before effects settle.
        """
        if not isinstance(observation, dict) or not self.awaiting_observation:
            return
        for prior in self.awaiting_observation:
            before = prior["Before"]
            changes = {}
            for key in ("Hp", "MaxHp", "Gold"):
                if before.get(key) != observation.get(key):
                    changes[key] = {"Before": before.get(key), "After": observation.get(key)}
            for key in ("Deck", "Relics", "PotionSlots"):
                if before.get(key) != observation.get(key):
                    changes[key] = {"Before": before.get(key), "After": observation.get(key)}
            self._append({
                "SchemaVersion": 4, "RecordType": "ObservationFollowup",
                "RunId": self.run_id, "Sequence": prior["Sequence"],
                "DecisionId": prior["DecisionId"],
                "DecisionType": prior["DecisionType"],
                "ObservedAtDecisionType": current_type,
                "ExecutionVerified": False,
                "NextRunObservation": observation,
                "ObservedChanges": changes,
                "TimestampUtc": datetime.now(timezone.utc).isoformat(),
            })
            print(f"TRACE: Follow-up observation #{prior['Sequence']} {prior['DecisionType']} (not execution-verified)", flush=True)
        self.awaiting_observation.clear()

    def record(self, request, response):
        run_id = request.get("RunId")
        if run_id:
            if self.run_id != run_id or self.path is None or self.closed:
                self._start_run(run_id)
                print("TRACE: Recording decisions for native run ID.", flush=True)
        elif (request.get("Type") == "NeowDecision" and
              request.get("DecisionId") == 1):
            self._start_run()
        elif self.path is None or self.closed:
            self._start_run()
            print("TRACE: Recording a partial run (no native RunId).", flush=True)

        # Finish state followups from previous decision(s) only after the run
        # identity has been established and the new request has arrived.
        self._observe_followups(request.get("RunObservation"), request.get("Type"))

        action = None
        if "ActionIndex" in response:
            i = response["ActionIndex"]
            actions = request.get("LegalActions", [])
            if not isinstance(i, int) or not 0 <= i < len(actions):
                raise ValueError(f"Invalid chosen action index: {i}")
            action = actions[i]
        elif "SelectedIndices" in response:
            indices = response["SelectedIndices"]
            options = request.get("OptionDetails") or request.get("Options", [])
            if not all(isinstance(i, int) and 0 <= i < len(options) for i in indices):
                raise ValueError(f"Invalid selected indices: {indices}")
            action = [options[i] for i in indices]
        else:
            raise ValueError("No supported choice found in policy response")

        entry = {
            "SchemaVersion": 2,
            "RecordType": "Decision",
            "RunId": self.run_id,
            "Sequence": self.seq,
            "TimestampUtc": datetime.now(timezone.utc).isoformat(),
            "DecisionType": request.get("Type", "CombatDecision"),
            "DecisionId": request.get("DecisionId"),
            "Request": request,
            "Response": response,
            "ChosenAction": action,
            "OutcomeVerified": False,
        }
        self._append(entry)
        # Store candidates of all types; native verification still requires a separate
        # exact (RunId, DecisionType, DecisionId) ActionExecution message.
        self.pending[(self.run_id, entry["DecisionType"], entry["DecisionId"])] = self.seq
        if entry["DecisionType"] != "CombatDecision" and isinstance(request.get("RunObservation"), dict):
            self.awaiting_observation.append({
                "Sequence": self.seq,
                "DecisionId": entry["DecisionId"],
                "DecisionType": entry["DecisionType"],
                "Before": request["RunObservation"],
            })
        self.seq += 1
        print(f"TRACE: Recorded #{entry['Sequence']} {entry['DecisionType']}", flush=True)
        return entry

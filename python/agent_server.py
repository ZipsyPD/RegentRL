import json
import socket

HOST = "127.0.0.1"
PORT = 5050

def main():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server:
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server.bind((HOST, PORT))
        server.listen(1)

        print(f"RegentRL Python server listening on {HOST}:{PORT}", flush=True)

        while True:
            conn, addr = server.accept()

            with conn:
                print(f"Connected: {addr}", flush = True)

                reader = conn.makefile("r", encoding = "utf-8")

                try:
                    line = reader.readline()

                    if not line:
                        print("Client disconnected without sending data.", flush = True)
                        continue

                    request = json.loads(line)

                    if request.get("Type") == "CardSelection":
                        response = handle_card_selection(request)

                        
                        print(
                            f"Card selection {request['DecisionId']}: "
                            f"selected indices {response['SelectedIndices']}",
                            flush=True
                            )
                    elif request.get("Type") == "RewardDecision":
                        decision_id = request["DecisionId"]
                        actions = request["LegalActions"]

                        if not actions:
                            raise ValueError("No legal reward actions received")

                        # Temporary test policy:
                        # prefer an uncollected gold reward, otherwise
                        # select the first non-skip action.
                        action_index = next(
                            (
                                i for i, action in enumerate(actions)
                                if action["Type"] == "SelectReward"
                                and request["Observation"]["Rewards"][
                                    action["RewardIndex"]
                                ]["Type"] == "Gold"
                            ),
                            None
                        )

                        if action_index is None:
                            action_index = next(
                                (
                                    i for i, action in enumerate(actions)
                                    if action["Type"] == "SelectReward"
                                ),
                                0
                            )

                        response = {
                            "DecisionId": decision_id,
                            "ActionIndex": action_index
                        }
                    else:
                        decision_id = request["DecisionId"]
                        actions = request["LegalActions"]

                        print(
                            f"Decision {decision_id}: {len(actions)} legal actions",
                            flush=True
                        )

                        for index, action in enumerate(actions):
                            print(f" [{index}] {action}", flush=True)

                        playable_indices = [
                            i for i, action in enumerate(actions)
                            if action["Type"] == "PlayCard"
                        ]

                        if playable_indices:
                            chosen_index = playable_indices[0]
                        else:
                            chosen_index = next(
                                i for i, action in enumerate(actions)
                                if action["Type"] == "EndTurn"
                            )

                        response = {
                            "DecisionId": decision_id,
                            "ActionIndex": chosen_index,
                        }

                    conn.sendall(
                            (json.dumps(response) + "\n").encode("utf-8")
                            )

                    print(f"Sent response for decision {decision_id}", flush = True)

                except Exception as ex:
                    print(f"Python server error: {ex!r}", flush = True)

                finally:
                    reader.close()

def handle_card_selection(request):
    options = request["Options"]
    min_select = request["MinSelect"]
    max_select = request["MaxSelect"]

    # Temporary policy: choose the maximum allowed number.
    count = min(max_select, len(options))

    return {
        "DecisionId": request["DecisionId"],
        "SelectedIndices": list(range(count)),
    }

if __name__ == "__main__":
    main()

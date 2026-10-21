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

                    decision_id = request["DecisionId"]
                    actions = request["LegalActions"]

                    print(
                            f"Decision {decision_id}: {len(actions)} legal actions",
                            flush = True
                            )

                    for index, action in enumerate(actions):
                        print(f" [{index}] {action}", flush = True)

                    response = {
                            "DecisionId": decision_id,
                            "ActionIndex": 0, 
                            }

                    conn.sendall(
                            (json.dumps(response) + "\n").encode("utf-8")
                            )

                    print(f"Sent response for decision {decision_id}", flush = True)

                except Exception as ex:
                    print(f"Python server error: {ex!r}", flush = True)

                finally:
                    reader.close()
if __name__ == "__main__":
    main()

import json
import socket
import argparse
import random
from research.live_policy import POLICIES, choose
from research.neural_policy import NeuralPolicy
from research.combat_ppo import CombatPPO

from run_experience_recorder import RunExperienceRecorder

HOST = "127.0.0.1"
PORT = 5050
# Temporary testing policy.
# Change to "SMITH" when you want to test card upgrades.
REST_CHOICE = "SMITH"

def main():
    parser = argparse.ArgumentParser(description='RegentRL live policy server')
    parser.add_argument('--policy', choices=(*POLICIES, 'bc', 'ppo', 'regentppo', 'fullrunppo'), default='legacy',
                        help='legacy keeps the existing handcrafted policy')
    parser.add_argument('--seed', type=int, default=42)
    parser.add_argument('--port', type=int, default=PORT, help='TCP port (default: 5050)')
    parser.add_argument('--trace-dir', help='Optional directory for run decision traces')
    parser.add_argument('--train', action='store_true', help='Update PPO on native-verified combat outcomes')
    parser.add_argument('--ppo-save', default='checkpoints/ppo_combat.pt')
    parser.add_argument('--checkpoint', help='Trained behavior-cloning checkpoint; required for --policy bc')
    args = parser.parse_args()
    if args.train and args.policy != 'ppo':
        parser.error('--train requires --policy ppo')
    if args.policy in ('bc', 'regentppo', 'fullrunppo') and not args.checkpoint:
        parser.error('--policy bc/regentppo/fullrunppo requires --checkpoint')
    neural = NeuralPolicy(args.checkpoint) if args.policy in ('bc', 'regentppo', 'fullrunppo') else None
    ppo = CombatPPO(train=args.train, checkpoint=args.checkpoint, checkpoint_out=args.ppo_save, seed=args.seed) if args.policy == 'ppo' else None
    rng = random.Random(args.seed)
    print(f'LIVE POLICY: {args.policy} (seed={args.seed})', flush=True)
    recorder = RunExperienceRecorder(args.trace_dir)
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server:
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server.bind((HOST, args.port))
        server.listen(1)

        print(f"RegentRL Python server listening on {HOST}:{args.port}", flush=True)

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
                    # Older RegentRL builds omitted Type on combat requests.
                    # Only infer when the unmistakable combat observation is present.
                    if (request.get('Type') is None
                            and isinstance(request.get('Observation'), dict)
                            and isinstance(request['Observation'].get('Player'), dict)
                            and isinstance(request['Observation'].get('Enemies'), list)
                            and isinstance(request.get('LegalActions'), list)):
                        request['Type'] = 'CombatDecision'

                    if request.get("Type") == "RunLifecycle":
                        recorder.lifecycle(request)
                        if ppo is not None:
                            if request.get('Event') == 'Started':
                                ppo.discard_incomplete('new run started')
                            elif request.get('Event') == 'Ended':
                                ppo.run_ended(request)
                        conn.sendall(b'{"Ok":true}\n')
                        continue

                    if request.get('Type') == 'CombatLifecycle':
                        if ppo is not None:
                            if request.get('Event') == 'Started':
                                ppo.combat_started()
                            elif request.get('Event') == 'Ended':
                                ppo.combat_ended(request)
                        conn.sendall(b'{"Ok":true}\n')
                        continue

                    if request.get("Type") == "ActionExecution":
                        recorder.resolve(request)
                        if ppo is not None:
                            ppo.resolved(request)
                        conn.sendall(b'{"Ok":true}\n')
                        continue

                    run_state = request.get("RunObservation")
                    if run_state is not None:
                        print(
                            "RunObservation v2: "
                            f"HP={run_state['Hp']}/{run_state['MaxHp']} "
                            f"Gold={run_state['Gold']} "
                            f"Deck={len(run_state['Deck'])} "
                            f"Relics={run_state['Relics']} "
                            f"Potions={run_state['PotionSlots']}",
                            flush=True,
                        )

                    # Policies for different decision (ancients, cards, etc..)
                    if request.get("Type") == "NeowDecision":
                        decision_id = request["DecisionId"]
                        actions = request["LegalActions"]

                        if not actions:
                            raise ValueError("No Neow choices received")

                        print(f"Neow decision {decision_id}:", flush=True)

                        for i, action in enumerate(actions):
                            print(f"  [{i}] {action['Name']}", flush=True)

                        # Temporary policy: first available bonus.
                        response = {
                            "DecisionId": decision_id,
                            "ActionIndex": next(
                                (
                                    i for i, action in enumerate(actions)
                                    if action["Name"] == "Lost Coffer"
                                ),
                                0
                            ),
                        }


                    elif request.get("Type") == "EventDecision":
                        decision_id = request["DecisionId"]
                        actions = request.get("LegalActions") or []
                        if not actions:
                            raise ValueError("No legal event options received")
                        print(f"Event decision {decision_id}:", flush=True)
                        for i, action in enumerate(actions):
                            print(f"  [{i}] {action.get('Name', action.get('Type', 'Unknown'))}", flush=True)
                        # Legacy fallback only. A trained fullrun PPO policy
                        # overrides this below using all public event features.
                        response = {"DecisionId": decision_id, "ActionIndex": 0}

                    elif request.get("Type") == "ShopDecision":
                        decision_id = request["DecisionId"]
                        actions = request["LegalActions"]
                        gold = request["Gold"]

                        print(f"Shop decision {decision_id}, Gold={gold}", flush=True)

                        for i, action in enumerate(actions):
                            print(
                                f"  [{i}] {action['Type']} "
                                f"{action.get('ItemType', '')} "
                                f"Id={action.get('ItemId', '')} "
                                f"Cost={action.get('Cost', 0)}",
                                flush=True
                            )

                        # Temporary testing policy:
                        # buy the first affordable non-potion item.
                        # If no such item exists, leave.
                        chosen_index = next(
                            (
                                i for i, action in enumerate(actions)
                                if action["Type"] in (
                                    "BuyCard",
                                    "BuyRelic",
                                    "RemoveCard"
                                )
                            ),
                            len(actions) - 1
                        )

                        response = {
                            "DecisionId": decision_id,
                            "ActionIndex": chosen_index,
                        }

                    elif request.get("Type") == "RestSiteDecision":
                        decision_id = request["DecisionId"]
                        actions = request["LegalActions"]

                        if not actions:
                            raise ValueError("No rest-site choices received")

                        print(f"Rest-site decision {decision_id}:", flush=True)

                        for i, action in enumerate(actions):
                            print(
                                f"  [{i}] {action['OptionId']} - {action['Name']}",
                                flush=True
                            )

                        # Prefer the configured action if it's available.
                        # Otherwise choose the first legal option.
                        chosen_index = next(
                            (
                                i for i, action in enumerate(actions)
                                if action["OptionId"] == REST_CHOICE
                            ),
                            0
                        )

                        print(
                            f"Rest-site policy chose: "
                            f"{actions[chosen_index]['OptionId']}",
                            flush=True
                        )

                        response = {
                            "DecisionId": decision_id,
                            "ActionIndex": chosen_index,
                        }


                    elif request.get("Type") == "MapDecision":
                        decision_id = request["DecisionId"]
                        actions = request["LegalActions"]

                        if not actions:
                            raise ValueError("No reachable map rooms received")

                        print(f"Map decision {decision_id}:", flush=True)

                        for i, action in enumerate(actions):
                            print(
                                f"  [{i}] Row={action['Row']}, "
                                f"Col={action['Column']}, "
                                f"Type={action['RoomType']}",
                                flush=True
                            )

                        # Temporary policy: first reachable room.
                        response = {
                            "DecisionId": decision_id,
                            "ActionIndex": 0,
                        }

                    elif request.get("Type") == "CardSelection":
                        response = handle_card_selection(request)

                        
                        print(
                            f"Card selection {request['DecisionId']}: "
                            f"selected indices {response['SelectedIndices']}",
                            flush=True
                            )

                    elif request.get("Type") == "BundleDecision":
                        decision_id = request["DecisionId"]
                        actions = request["LegalActions"]

                        if not actions:
                            raise ValueError("No card bundles received")

                        print(f"Bundle decision {decision_id}:", flush=True)

                        for i, action in enumerate(actions):
                            print(
                                f"  [{i}] {', '.join(action['CardIds'])}",
                                flush=True
                            )

                        # Temporary policy: choose the first bundle.
                        response = {
                            "DecisionId": decision_id,
                            "ActionIndex": 0,
                        }

                    elif request.get("Type") == "CardRewardDecision":
                        decision_id = request["DecisionId"]
                        actions = request["LegalActions"]

                        print("Card reward options:", flush=True)

                        for i, action in enumerate(actions):
                            print(f"  [{i}] {action['CardId']}", flush=True)

                        response = {
                            "DecisionId": decision_id,
                            "ActionIndex": 0,
                        }

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

                        # Compatibility fallback only. Unknown decision types
                        # may have neither PlayCard nor EndTurn, so never assume
                        # a combat-only action exists here. Fullrun PPO replaces
                        # this response below with the learned policy's choice.
                        potion_index = next(
                            (
                                i for i, action in enumerate(actions)
                                if action.get("Type") == "UsePotion"
                            ),
                            None
                        )

                        chosen_index = potion_index if potion_index is not None else 0
                        response = {
                            "DecisionId": decision_id,
                            "ActionIndex": chosen_index,
                        }

                    # All policy selection happens before recording/sending.
                    # The legacy handler above remains the compatibility fallback.
                    if args.policy == 'fullrunppo' and neural is not None:
                        overridden = (neural.select_cards(request) if request.get('Type') == 'CardSelection' and neural.feature_version in (5, 6, 7, 8) else neural.choose(request) if request.get('Type') != 'CardSelection' and isinstance(request.get('LegalActions'), list) and request['LegalActions'] else None)
                    elif ppo is not None and request.get('Type') == 'CombatDecision':
                        overridden = ppo.choose(request)
                    elif ppo is not None:
                        # Only combat uses PPO; legacy policies keep the run moving.
                        overridden = None
                    else:
                        overridden = (neural.choose(request) if neural is not None and request.get('Type') == 'CombatDecision'
                                      else choose(request, 'first', rng)) if args.policy == 'regentppo' else (neural.choose(request) if neural is not None and request.get('Type') != 'CardSelection' else choose(request, 'first' if args.policy == 'bc' else args.policy, rng))
                    if overridden is not None:
                        response = overridden
                    selected = response.get('ActionIndex', response.get('SelectedIndices'))
                    print(f'LIVE POLICY [{args.policy}] {request.get("Type")} '
                          f'decision={request.get("DecisionId")} choice={selected}', flush=True)

                    # Persist the decision before returning it to the game.
                    # This is a decision trace, not yet an RL transition with
                    # a verified post-action state or terminal reward.
                    recorder.record(request, response)

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
    purpose = request.get("Purpose", "Unknown")
    source = request.get("Source", "Unknown")

    print(
        f"Selection protocol v{request.get('ProtocolVersion', 0)}; "
        f"options: {request.get('OptionDetails', [])}",
        flush=True
    )

    print(
        f"Card selection: Purpose={purpose}, Source={source}",
        flush=True
    )

    if min_select < 0 or max_select < min_select:
        raise ValueError("Invalid selection bounds")

    if len(options) < min_select:
        raise ValueError("Not enough selectable cards")

    # Temporary policy: choose the minimum required amount.
    # A learned policy can replace this later.
    count = min(max_select, len(options))

    print(
        f"Card selection: choosing {count} of {len(options)} "
        f"cards (allowed {min_select}-{max_select})",
        flush=True
    )

    return {
        "DecisionId": request["DecisionId"],
        "SelectedIndices": list(range(count)),
    }

if __name__ == "__main__":
    main()

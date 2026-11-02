"""Regression: native event options must reach the PPO model, not a combat EndTurn fallback."""
import json
import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest


def test_native_event_decision_can_select_second_option(tmp_path):
    torch = pytest.importorskip('torch')
    from research.neural_policy import make_model
    from research.fullrun_encoder import encode, FEATURES

    request = {
        'Type': 'EventDecision', 'DecisionId': 41,
        'EventId': 'TreeEvent', 'EventName': 'The Tree',
        'RunObservation': {
            'Hp': 63, 'MaxHp': 75, 'Gold': 114, 'Floor': 2, 'Act': 1,
            'Deck': [{'CardId':'STRIKE_REGENT','UpgradeLevel':0}],
            'Relics': ['DIVINE_RIGHT'], 'PotionSlots': [],
        },
        'LegalActions': [
            {'Type':'ChooseOption', 'OptionIndex':0,'Name':'Exchange Gold',
             'OptionId':'','Description':'Lose 26 Gold. Gain 2 random Potions.'},
            {'Type':'ChooseOption', 'OptionIndex':1,'Name':'Hug the Tree',
             'OptionId':'','Description':'Lose 9 HP. Transform a card.'},
        ],
    }
    a, b = [encode(request, action) for action in request['LegalActions']]
    preferred_dimension = max(range(FEATURES), key=lambda i: b[i]-a[i])
    assert b[preferred_dimension] > a[preferred_dimension]
    model = make_model(FEATURES)
    with torch.no_grad():
        for p in model.parameters():p.zero_()
        model[0].weight[0, preferred_dimension] = 3.0
        model[2].weight[0, 0] = 2.0
        model[4].weight[0, 0] = 2.0
        logits = model(torch.tensor([a,b], dtype=torch.float32)).flatten()
        assert logits[1] > logits[0], 'Fixture model must prefer the second option'
    checkpoint = tmp_path / 'v8_event.pt'
    torch.save({'feature_version':8, 'state_dict':model.state_dict()}, checkpoint)

    # Use an available ephemeral port rather than conflicting with the game at 5050.
    with socket.socket() as port_check:
        port_check.bind(('127.0.0.1', 0))
        port = port_check.getsockname()[1]
    root = Path(__file__).resolve().parents[1]
    cmd = [sys.executable, '-u', str(root / 'agent_server.py'), '--policy',
           'fullrunppo', '--checkpoint', str(checkpoint), '--port', str(port),
           '--trace-dir', str(tmp_path / 'traces')]
    server = subprocess.Popen(cmd, cwd=root, stdout=subprocess.PIPE,
                              stderr=subprocess.STDOUT, text=True)
    try:
        ready = False
        for _ in range(150):
            if server.poll() is not None:
                break
            try:
                with socket.create_connection(('127.0.0.1',port),timeout=.2):
                    ready = True
                    break
            except (ConnectionRefusedError, TimeoutError, OSError):
                time.sleep(.1)
        assert ready, 'Policy server failed to start'
        with socket.create_connection(('127.0.0.1',port),timeout=10) as client:
            client.sendall((json.dumps(request)+'\n').encode('utf8'))
            client.settimeout(10)
            with client.makefile('r') as handle:
                answer = handle.readline()
        assert answer, 'Server did not return a decision'
        assert json.loads(answer) == {'DecisionId':41,'ActionIndex':1}
    finally:
        server.terminate()
        try: server.communicate(timeout=10)
        except subprocess.TimeoutExpired:
            server.kill()
            server.communicate(timeout=5)

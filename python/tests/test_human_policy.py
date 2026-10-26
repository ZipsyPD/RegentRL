import unittest
from research.human_policy import choose_human

class HumanPolicyTests(unittest.TestCase):
    def test_action_invalid_then_valid(self):
        inputs=iter(['oops','3','1'])
        req={'Type':'CombatDecision','DecisionId':4,'LegalActions':[{'Type':'EndTurn'},{'Type':'PlayCard','CardId':'STRIKE_REGENT'}]}
        ans=choose_human(req,input_fn=lambda _: next(inputs), output_fn=lambda _:None)
        self.assertEqual(ans,{'DecisionId':4,'ActionIndex':1})
    def test_card_multiselect(self):
        inputs=iter(['0,0','0,2'])
        req={'Type':'CardSelection','DecisionId':2,'Options':['a','b','c'],'MinSelect':2,'MaxSelect':2}
        ans=choose_human(req,input_fn=lambda _: next(inputs),output_fn=lambda _:None)
        self.assertEqual(ans,{'DecisionId':2,'SelectedIndices':[0,2]})
    def test_optional_zero_selection(self):
        req={'Type':'CardSelection','DecisionId':7,'Options':['a'],'MinSelect':0,'MaxSelect':1}
        self.assertEqual(choose_human(req,input_fn=lambda _: '',output_fn=lambda _:None)['SelectedIndices'],[])

if __name__ == '__main__': unittest.main()

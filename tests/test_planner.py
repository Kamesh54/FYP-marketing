from campaign_planner import CampaignPlannerAgent


def test_generate_proposals():
    planner = CampaignPlannerAgent()
    res = planner.generate_proposals("healthy meal prep", duration_days=3)
    assert 'proposals' in res and len(res['proposals']) == 3

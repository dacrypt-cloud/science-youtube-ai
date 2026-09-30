from science_studio.research.planner import plan_research, depth_for, interpret_idea

def test_interpret():
    d = interpret_idea("How does a mosquito transmit malaria?")
    assert "central_question" in d and d["central_question"]

def test_depth_controller():
    shallow = depth_for("What is water?", "8-10")
    deep = depth_for("How does Plasmodium molecular mechanism inside mosquito midgut ookinete oocyst sporozoite transmission work and why?", "15-20")
    order = ["shallow", "standard", "deep", "exhaustive"]
    assert order.index(deep) >= order.index(shallow)

def test_plan_no_stack():
    plan = plan_research("Why is malaria hard to eliminate?", duration="12-15", stack=None)
    assert len(plan["research_questions"]) >= 4
    assert plan["depth"] in ("shallow", "standard", "deep", "exhaustive")

"""Tests for model configuration integrity."""

from verd.models import MODELS, ROLES, MODEL_PARAMS, JUDGE_PARAMS


def test_all_tiers_exist():
    assert "verdl" in MODELS
    assert "verd" in MODELS
    assert "verdh" in MODELS


def test_all_debater_roles_are_valid():
    for tier_name, tier in MODELS.items():
        for debater in tier["debaters"]:
            role = debater.get("role")
            if role is not None:
                assert role in ROLES, f"{tier_name}: debater role '{role}' not in ROLES"


def test_tiers_have_required_keys():
    for tier_name, tier in MODELS.items():
        assert "debaters" in tier, f"{tier_name} missing debaters"
        assert "judge" in tier, f"{tier_name} missing judge"
        assert "rounds" in tier, f"{tier_name} missing rounds"
        assert len(tier["debaters"]) >= 2, f"{tier_name} needs at least 2 debaters"
        assert tier["rounds"] >= 1, f"{tier_name} needs at least 1 round"


def test_no_duplicate_models_in_tier():
    for tier_name, tier in MODELS.items():
        models = [d["model"] for d in tier["debaters"]]
        assert len(models) == len(set(models)), f"{tier_name} has duplicate debater models"


def test_verdh_has_fact_checker():
    roles = [d.get("role") for d in MODELS["verdh"]["debaters"]]
    assert "fact_checker" in roles, "verdh should include a fact_checker"


def test_judge_params_match_tiers():
    for tier_name in JUDGE_PARAMS:
        assert tier_name in MODELS, f"JUDGE_PARAMS has unknown tier '{tier_name}'"

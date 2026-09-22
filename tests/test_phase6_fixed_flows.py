import pytest

from top_heroes_auto.automation.phase6_fixed_flows import (
    FIXED_FLOWS,
    MANIFEST_VERSION,
    RANKING_CHEST,
    SHOP_DAILY,
    VIP_DAILY,
    CandidateDecision,
    FixedFlowSpec,
    FlowQualification,
    fixed_flow_for_task,
)


def test_manifest_is_versioned_and_contains_three_distinct_fixed_flows():
    assert MANIFEST_VERSION == "phase6-fixed-flows-v1"
    assert tuple(flow.id for flow in FIXED_FLOWS) == (
        "vip-daily",
        "shop-daily-gift",
        "ranking-daily-chest",
    )
    assert len({flow.action_role for flow in FIXED_FLOWS}) == 3


def test_manifest_contains_semantic_roles_not_coordinates_or_annotated_assets():
    for flow in FIXED_FLOWS:
        values = flow.route_roles + tuple(flow.forbidden_roles) + tuple(flow.discovery_roles)
        assert all(isinstance(value, str) and value for value in values)
        assert not hasattr(flow, "x") and not hasattr(flow, "y")
        assert all(".png" not in value.lower() for value in values)


@pytest.mark.parametrize("flow", FIXED_FLOWS)
def test_unqualified_fixed_flows_fail_closed_even_if_all_claim_roles_match(flow):
    assert not flow.qualification.activation_ready
    assert flow.decide(set(flow.claim_roles)) == CandidateDecision.UNKNOWN


def test_forbidden_evidence_wins_over_a_fully_qualified_free_candidate():
    qualified = FixedFlowSpec(
        id="test",
        task="test",
        route_roles=("entry",),
        page_role="page",
        action_role="claim",
        free_role="free",
        available_role="available",
        post_role="post",
        forbidden_roles=frozenset(("paid",)),
        discovery_roles=frozenset(("dot",)),
        qualification=FlowQualification(True, True, True, True),
    )
    assert qualified.decide(set(qualified.claim_roles)) == CandidateDecision.READY
    assert qualified.decide(set(qualified.claim_roles) | {"paid"}) == CandidateDecision.FORBIDDEN


def test_red_dot_is_discovery_only_and_never_makes_a_candidate_ready():
    matched = set(VIP_DAILY.claim_roles) | VIP_DAILY.discovery_roles
    assert VIP_DAILY.decide(matched) == CandidateDecision.UNKNOWN


def test_paid_shop_tabs_are_explicitly_forbidden_for_future_dispatch():
    assert {
        "shop-daily-pack-tab",
        "shop-weekly-pack-tab",
        "shop-construction-fund-tab",
        "shop-diamond-store-tab",
    } <= SHOP_DAILY.forbidden_roles


def test_only_existing_reward_tasks_map_to_packaged_fixed_flows():
    assert fixed_flow_for_task("vip-reward") is VIP_DAILY
    assert fixed_flow_for_task("free-pack") is SHOP_DAILY
    assert fixed_flow_for_task("free-recruit") is None
    assert RANKING_CHEST.task is None


def test_required_and_forbidden_roles_cannot_overlap():
    with pytest.raises(ValueError, match="required role"):
        FixedFlowSpec(
            id="bad",
            task=None,
            route_roles=("entry",),
            page_role="page",
            action_role="claim",
            free_role="free",
            available_role="available",
            post_role="post",
            forbidden_roles=frozenset(("claim",)),
            discovery_roles=frozenset(),
        )

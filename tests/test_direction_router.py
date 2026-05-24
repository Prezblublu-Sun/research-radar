"""Tests for ADR-0021: rl_world_model routing + RL×FEA/surrogate crossover
boost in pipeline/direction_router.py.

Covers:
  * Routing of papers with world-model / Dreamer terms into rl_world_model.
  * Generic RL (e.g. Atari) does NOT enter rl_world_model.
  * PINN-only papers stay in fea_surrogate (not rl_world_model).
  * Papers with an RL pairing AND surrogate/FE terms route into BOTH
    rl_world_model and fea_surrogate.
  * apply_crossover_boost bumps Low->Medium, Medium->High, leaves
    High/Exclude alone, ignores single-direction papers, ignores other
    two-direction overlaps, and is idempotent.

All tests load the live config/directions.yaml so the production rule set
is what is being exercised.

Run with:
    pytest tests/test_direction_router.py
"""
from __future__ import annotations

import pathlib
import sys

import pytest
import yaml

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pipeline import direction_router  # noqa: E402


CFG_PATH = ROOT / "config" / "directions.yaml"


@pytest.fixture(scope="module")
def cfg():
    return yaml.safe_load(CFG_PATH.read_text())


@pytest.fixture(scope="module")
def directions(cfg):
    return cfg["directions"]


@pytest.fixture(scope="module")
def exclusions(cfg):
    return cfg.get("exclusions", {})


def _paper(title: str, abstract: str) -> dict:
    return {"title": title, "abstract": abstract}


# ============================================================================
# Routing
# ============================================================================

def test_world_model_paper_routes_into_rl_world_model(directions, exclusions):
    p = _paper(
        "Dreamer: World models for sample-efficient control",
        "We learn a world model with latent dynamics for planning with "
        "learned models and report results on continuous control tasks.",
    )
    direction_router.route(p, directions, exclusions)
    assert "rl_world_model" in (p.get("directions") or [])


def test_generic_rl_atari_does_not_route_into_rl_world_model(directions, exclusions):
    p = _paper(
        "Deep reinforcement learning for Atari games",
        "We train an agent to play Atari games with reinforcement learning "
        "and report new state-of-the-art scores on the ALE benchmark.",
    )
    direction_router.route(p, directions, exclusions)
    assert "rl_world_model" not in (p.get("directions") or [])


def test_pinn_only_paper_stays_in_fea_surrogate(directions, exclusions):
    p = _paper(
        "Physics-informed neural network for elasticity",
        "We present a PINN that solves the linear elasticity PDE with a "
        "neural operator (DeepONet) for surrogate modeling of mechanics.",
    )
    direction_router.route(p, directions, exclusions)
    dirs = p.get("directions") or []
    assert "fea_surrogate" in dirs
    assert "rl_world_model" not in dirs


def test_rl_crossover_paper_routes_into_both_directions(directions, exclusions):
    p = _paper(
        "Model-based reinforcement learning over a finite element surrogate",
        "We combine model-based reinforcement learning with a finite "
        "element surrogate model for design optimization of an implant. "
        "The world model is trained on simulation data and used for "
        "trajectory optimization. Active learning samples new simulations.",
    )
    direction_router.route(p, directions, exclusions)
    dirs = set(p.get("directions") or [])
    assert "rl_world_model" in dirs
    assert "fea_surrogate" in dirs


# ============================================================================
# apply_crossover_boost
# ============================================================================

def _crossover_paper(priority: str) -> dict:
    return {
        "directions": ["rl_world_model", "fea_surrogate"],
        "llm": {"priority": priority},
    }


def test_boost_low_becomes_medium():
    p = _crossover_paper("Low")
    n = direction_router.apply_crossover_boost([p])
    assert n == 1
    assert p["llm"]["priority"] == "Medium"
    assert p["llm"]["priority_pre_boost"] == "Low"
    assert p["llm"]["priority_boosted"] is True
    assert "ADR-0021" in p["llm"]["boost_reason"]


def test_boost_medium_becomes_high():
    p = _crossover_paper("Medium")
    n = direction_router.apply_crossover_boost([p])
    assert n == 1
    assert p["llm"]["priority"] == "High"
    assert p["llm"]["priority_pre_boost"] == "Medium"
    assert p["llm"]["priority_boosted"] is True


def test_boost_high_stays_high_and_not_marked():
    p = _crossover_paper("High")
    n = direction_router.apply_crossover_boost([p])
    assert n == 0
    assert p["llm"]["priority"] == "High"
    assert "priority_boosted" not in p["llm"]
    assert "priority_pre_boost" not in p["llm"]


def test_boost_exclude_stays_exclude_and_not_marked():
    p = _crossover_paper("Exclude")
    n = direction_router.apply_crossover_boost([p])
    assert n == 0
    assert p["llm"]["priority"] == "Exclude"
    assert "priority_boosted" not in p["llm"]


def test_boost_skips_paper_in_only_rl_world_model():
    p = {
        "directions": ["rl_world_model"],
        "llm": {"priority": "Low"},
    }
    n = direction_router.apply_crossover_boost([p])
    assert n == 0
    assert p["llm"]["priority"] == "Low"
    assert "priority_boosted" not in p["llm"]


def test_boost_skips_other_two_direction_overlap():
    p = {
        "directions": ["hip_implant", "am_biomedical"],
        "llm": {"priority": "Low"},
    }
    n = direction_router.apply_crossover_boost([p])
    assert n == 0
    assert p["llm"]["priority"] == "Low"
    assert "priority_boosted" not in p["llm"]


def test_boost_is_idempotent():
    p = _crossover_paper("Low")
    direction_router.apply_crossover_boost([p])
    n2 = direction_router.apply_crossover_boost([p])
    assert n2 == 0
    assert p["llm"]["priority"] == "Medium"
    assert p["llm"]["priority_pre_boost"] == "Low"

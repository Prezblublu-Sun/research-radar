# ADR-0021: New direction `rl_world_model` + RL×FEA/surrogate crossover boost

**Status**: Proposed (2026-05-23)
**Related**: ADR-0014 (scorer), ADR-0015 (v2 routing/buckets),
direction config (config/directions.yaml), direction_router.route()

## Context

The user's research centres on FE-based implant/biomechanics design,
surrogate modelling, and additive manufacturing (existing directions:
hip_implant, fea_surrogate, am_biomedical, ai_bioprinting). A methods
area not yet tracked is reinforcement learning and world models —
model-based RL, learned dynamics/simulators, latent imagination
(Dreamer/MuZero/PlaNet/TD-MPC lineage).

Most of pure RL/world-model research (games, generic robotics, language)
is only methodologically interesting to this user. But a specific
intersection is directly valuable: RL / world models applied to
engineering simulation — e.g. RL searching a design space defined by an
FE surrogate, world models learning FEA dynamics to accelerate
iteration, model-based RL over physics simulators. That intersection is
exactly "apply RL to MY simulation/design problem," which is High-value.

PINN already lives in fea_surrogate (physics-informed neural network,
neural operator, DeepONet, FNO). The new direction must NOT duplicate
PINN — it covers RL + world models only. Physics-informed world models
naturally straddle both directions, which is fine.

## Decision 1 — Add direction `rl_world_model`

Add to config/directions.yaml a fifth direction "RL & World Models".

Routing design avoids drowning in generic RL: the bare phrase
"reinforcement learning" is NOT a strong_keyword (that would pull in
thousands of unrelated game/robotics/LLM papers per month). Instead:

  strong_keywords (world-model / model-based specific, low false-positive):
    world model, model-based reinforcement learning, latent dynamics,
    Dreamer, MuZero, learned simulator, model predictive control,
    recurrent state-space model, latent imagination,
    planning with learned models, trajectory optimization

  must_pair_with (generic "reinforcement learning" only counts when paired):
    [reinforcement learning, world model]
    [reinforcement learning, dynamics model]
    [reinforcement learning, model-based]
    [reinforcement learning, simulation]
    [reinforcement learning, surrogate]
    [reinforcement learning, finite element]
    [reinforcement learning, design optimization]
    [world model, physics]
    [world model, simulation]

The surrogate/finite-element/design-optimization pairings ensure the
high-value engineering-crossover papers are reliably routed in (they
then get boosted by Decision 2).

PINN/neural-operator keywords are deliberately omitted — they remain in
fea_surrogate. A physics-informed world-model paper will match BOTH
directions (router is multi-direction; directions[] holds all matches,
direction = highest scorer). That dual-membership is intended and is the
trigger for Decision 2.

sources: arxiv_categories cs.LG/cs.AI/cs.RO; openalex concepts/keywords
for RL + world models. llm_prompt_focus instructs the scorer to assess
whether the paper connects model-based RL/world models to engineering
simulation (surrogate/FEA/physics/design optimization) vs being a pure
methods paper, surfacing an "engineering tie-in" tag.

## Decision 2 — RL×FEA/surrogate crossover boost (the ONLY boost rule)

A deterministic POST-PROCESSING step, applied after score_batch in
run_daily (after line ~127, before bucket writing), NOT inside the LLM
prompt. Rationale: "raise one level on crossover" must be exact,
auditable, and testable — not left to LLM improvisation.

Trigger: a paper whose directions[] contains BOTH "rl_world_model" AND
"fea_surrogate" (reusing the router's multi-direction membership, so the
crossover criterion is consistent with routing).

Rule (one-level bump, capped, Exclude not rescued):
    Low     -> Medium
    Medium  -> High
    High    -> High   (cap)
    Exclude -> Exclude (a hard Exclude has a real reason; not rescued)

Traceability: set on the paper's llm dict
    priority_boosted = true
    boost_reason = "RL × FEA/surrogate crossover (ADR-0021)"
and preserve the original via
    priority_pre_boost = <original priority>
so the UI/audit can show which papers were boosted and from what.

This is the ONLY boost rule. It does NOT generalise to arbitrary
two-direction overlaps (e.g. hip_implant×am_biomedical is NOT boosted).
If other crossovers ever warrant boosting, each needs its own ADR.

## Scope boundaries

  - Forward-only: applies to run_daily (the cron) from deployment onward.
    The existing corpus is NOT re-routed or re-scored. Historical RL/
    world-model papers will not retroactively join the new direction or
    receive the boost. (Re-routing 100k papers + re-scoring is out of
    scope and not worth the token cost for a methods-adjacent direction.)
  - run_historical (backfill) shares route()/score_batch, so if a future
    backfill runs it will also route into rl_world_model — but the boost
    post-processing lives in run_daily; if backfill should also boost,
    that is a follow-up (keep the rule in one shared helper to avoid
    divergence — see Implementation note).
  - Only the RL×FEA/surrogate crossover is boosted. No other pair.
  - Exclude and High are never changed by the boost.

## Implementation note

Put the boost in a single small helper (e.g.
direction_router.apply_crossover_boost(scored) or a function in run_daily)
so there is ONE definition. run_daily calls it after score_batch. If
backfill later needs it, it calls the same helper — no copy-paste.

The crossover check reads paper["directions"] (the full match list),
which route() already populates. No new routing logic needed.

## Overlap analysis with existing directions

  - vs fea_surrogate: intended overlap on physics-informed world models /
    RL-over-surrogate. Both directions match; boost fires. PINN-only
    papers stay fea_surrogate (no RL signal -> not in rl_world_model).
  - vs hip_implant / am_biomedical / ai_bioprinting: minimal. world-model/
    MBRL vocabulary does not collide with implant/AM/bioprinting keywords.

## Testing

  - Routing: an RL+world-model paper routes into rl_world_model; a generic
    "reinforcement learning for Atari" paper does NOT (no strong_keyword,
    no satisfied must_pair_with). A PINN-only paper does NOT enter
    rl_world_model (stays fea_surrogate).
  - A paper matching both RL pairing AND surrogate/FE routes into BOTH
    directions (directions[] contains both).
  - Boost: a paper in {rl_world_model, fea_surrogate} with priority Low ->
    Medium (+ priority_boosted, boost_reason, priority_pre_boost set);
    Medium -> High; High -> High (unchanged flags still set? — set
    priority_boosted only when an actual change happens); Exclude ->
    Exclude (untouched, no boost flag).
  - A paper in only ONE of the two directions is NOT boosted.
  - A paper in two OTHER directions (e.g. hip_implant+am_biomedical) is
    NOT boosted.
  - Idempotence: running the boost twice does not double-bump (guard on
    priority_boosted already set, or compute from priority_pre_boost).

## Consequences

  - One new direction surfaced in routing, scoring, and the site nav.
  - A small, transparent, auditable re-rank of genuinely cross-cutting
    RL×simulation papers into the user's attention (Medium/High) without
    altering the scorer's base judgement or touching other directions.
  - search-index / page rendering gain a fifth direction — verify the UI
    handles 5 directions (colors, nav, filters) before deploy.

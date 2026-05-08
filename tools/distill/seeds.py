"""Seed prompts for synthetic-data generation. The data pipeline expands
each seed into 30-50 variations (different domains/specifics), then runs
the teacher (Qwen3.6 + Hammerstein framework) on each.

30 seeds × ~70 expansions = ~2000 (query, response) pairs total.
Per Hammerstein audit: 'frame as behavior cloning, not reasoning training.'
"""

from __future__ import annotations

# Five templates × six seeds each = 30 seeds total. Each seed is a
# template-shaped prompt that's representative of real strategic-reasoning
# queries Ray would actually submit.

SEEDS_AUDIT_THIS_PLAN = [
    "Audit this plan: rebuild {SYSTEM} from scratch using {NEW_TECH} instead of patching the existing {LEGACY}.",
    "Audit this plan: ship {FEATURE} as a separate microservice rather than extending the monolith.",
    "Audit this plan: migrate {DATABASE} to {NEW_DB} over a single weekend cutover.",
    "Audit this plan: replace {VENDOR} with a self-hosted alternative to cut $X/month in costs.",
    "Audit this plan: introduce {ABSTRACTION} across the codebase to consolidate duplicated patterns.",
    "Audit this plan: deprecate {OLD_API} in favor of {NEW_API}, with a 30-day transition window.",
]

SEEDS_SCOPE_THIS_IDEA = [
    "Scope this idea: a small CLI tool that {DOES_X} for {USER_GROUP}.",
    "Scope this idea: a {WEB|MOBILE} app that helps {AUDIENCE} with {PAIN_POINT}.",
    "Scope this idea: an open-source library that wraps {EXISTING_TOOL} to add {MISSING_FEATURE}.",
    "Scope this idea: a SaaS that ingests {DATA_SOURCE} and outputs {ARTIFACT} for {BUYER_PERSONA}.",
    "Scope this idea: a side project that converts {INPUT_FORMAT} to {OUTPUT_FORMAT} via {METHOD}.",
    "Scope this idea: a marketplace connecting {SUPPLY_SIDE} with {DEMAND_SIDE} around {NICHE}.",
]

SEEDS_IS_THIS_WORTH_DOING = [
    "Is this worth doing: spending {DURATION} learning {TECHNOLOGY} for the {PROJECT} I'm working on?",
    "Is this worth doing: porting {EXISTING_CODE} from {LANG_A} to {LANG_B} for performance?",
    "Is this worth doing: writing tests for {LEGACY_MODULE} before {UPCOMING_CHANGE}?",
    "Is this worth doing: launching a beta of {PRODUCT} now or polishing for two more weeks?",
    "Is this worth doing: building {INTERNAL_TOOL} or buying {COMMERCIAL_ALTERNATIVE}?",
    "Is this worth doing: contributing {FEATURE} upstream to {OSS_PROJECT} or maintaining a fork?",
]

SEEDS_WHAT_SHOULD_WE_DO_NEXT = [
    "What should we do next: {OPTION_A}, {OPTION_B}, or {OPTION_C} given that {CONSTRAINT}?",
    "What's the highest-leverage move on {PROJECT} given that {DEADLINE} is approaching?",
    "We have {N} priority tasks and {M} hours: which {K} are worth shipping this week?",
    "Three candidates for next sprint: {A}, {B}, {C}. Pick one and explain.",
    "Given {RESOURCE_LIMIT}, what's the single move that compounds most over the next month?",
    "What do we do with {STUCK_PROJECT}: revive, archive, or pivot?",
]

SEEDS_REVIEW_FROM_DIFFERENT_ANGLE = [
    "Review from a different angle: we decided to {DECISION}, but what if {COUNTER_ASSUMPTION} is wrong?",
    "Review from a different angle: the team consensus is {VIEW_X}, but a strict reviewer would say what?",
    "Review from a different angle: we've been treating {PROBLEM} as a {CATEGORY_A} issue. What if it's {CATEGORY_B}?",
    "Review from a different angle: what would {PERSONA_X} say about {PLAN}?",
    "Review from a different angle: we ruled out {OPTION} early. What if that was wrong?",
    "Review from a different angle: what's the strongest argument against {CURRENT_DIRECTION}?",
]

ALL_SEEDS = {
    "audit-this-plan": SEEDS_AUDIT_THIS_PLAN,
    "scope-this-idea": SEEDS_SCOPE_THIS_IDEA,
    "is-this-worth-doing": SEEDS_IS_THIS_WORTH_DOING,
    "what-should-we-do-next": SEEDS_WHAT_SHOULD_WE_DO_NEXT,
    "review-from-different-angle": SEEDS_REVIEW_FROM_DIFFERENT_ANGLE,
}

# Domain-specific fillers used during expansion. Combined with the seed
# placeholders to produce concrete, varied prompts.
DOMAINS = [
    "software engineering / dev tools",
    "wargame design / game mechanics",
    "small business / freelance ops",
    "indie game development",
    "writing / content creation",
    "side-project portfolio management",
    "machine learning / AI tooling",
    "personal productivity systems",
    "web development / SaaS",
    "open-source maintenance",
    "career / job-signaling decisions",
    "creative work / artistic projects",
]


if __name__ == "__main__":
    total = sum(len(v) for v in ALL_SEEDS.values())
    print(f"Total seeds: {total}")
    print(f"Domains for expansion: {len(DOMAINS)}")
    print(f"Estimated expansions per seed (×{len(DOMAINS)} domains × ~6 specifics): "
          f"~{6 * len(DOMAINS)} per seed")
    print(f"Estimated total prompts: ~{total * 6 * len(DOMAINS)}")

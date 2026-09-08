"""What a model switch actually costs, once the prompt cache is priced in.

Prompt caches are **model-scoped**: switching models mid-conversation throws
away the warm prefix and pays to rebuild it on the new model. Anthropic's own
guidance is blunt about it -- "model switch has no escape hatch" -- so a router
that ignores this is quietly billing you for re-warms it never counted.

The numbers that matter (Claude API, from the prompt-caching reference):

* a cache **read** costs ~0.1x the base input price;
* a cache **write** costs 1.25x for the 5-minute TTL, 2x for the 1-hour TTL;
* a cache entry is a prefix match, and each model keeps its own.

That last point is the one people miss. Leaving model A for a few steps does
not destroy A's cache. When you come back, the old prefix is still byte
identical, so it reads as a hit and you only write what was appended while you
were away -- provided you return inside the TTL and the excursion appended
fewer than the ~20 positions the server looks back over. So a *short excursion*
to a cheap model is much cheaper than a permanent switch, and this module
prices all three options:

    stay      -- keep the turn on the current model
    switch    -- move to the new model for the rest of the turn
    excursion -- a bounded hop to the cheaper model, then back
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from .config import Config, tier_name

# Server-side lookback: an excursion that appends more positions than this
# pushes the old entry out and forfeits the cheap return.
LOOKBACK_POSITIONS = 20


@dataclass(frozen=True)
class CacheModel:
    read_multiplier: float = 0.10
    write_multiplier: float = 2.00      # 1-hour TTL; 1.25 for the 5-minute one
    ttl_seconds: int = 3600

    @classmethod
    def for_ttl(cls, ttl: str) -> "CacheModel":
        if str(ttl).lower() in ("5m", "300", "ephemeral"):
            return cls(write_multiplier=1.25, ttl_seconds=300)
        return cls()


@dataclass(frozen=True)
class Analysis:
    """One option, priced. All costs are dollars for the rest of the turn."""

    option: str                  # stay | switch | excursion
    from_tier: int
    to_tier: int
    context_tokens: int
    horizon: float               # expected remaining requests in this turn
    rewarm_cost: float           # paid once, to rebuild the prefix elsewhere
    saving_per_request: float    # saved on each request after the re-warm
    breakeven_requests: float    # inf when the switch never pays for itself
    net_saving: float            # over `horizon` requests; negative means worse
    detail: str = ""

    @property
    def worth_it(self) -> bool:
        return self.net_saving > 0


def _prices(cfg: Config, tier: int) -> tuple[float, float]:
    """(input, output) dollars per token for a tier."""
    name = tier_name(tier)
    return (
        cfg.pricing_per_mtok_in.get(name, 0.0) / 1e6,
        cfg.pricing_per_mtok_out.get(name, 0.0) / 1e6,
    )


def analyse_switch(
    cfg: Config,
    from_tier: int,
    to_tier: int,
    context_tokens: int,
    horizon: float,
    output_tokens: int = 500,
    cache: CacheModel | None = None,
) -> Analysis:
    """Price moving to `to_tier` for the rest of the turn, against staying put.

    Staying is cheap per request because the prefix is already warm on the
    current model. Switching pays a full write on the new model up front and
    then reads cheaply -- so the question is always whether enough requests
    remain to amortise that write.
    """
    cache = cache or CacheModel.for_ttl(cfg.cache_ttl)
    in_from, out_from = _prices(cfg, from_tier)
    in_to, out_to = _prices(cfg, to_tier)
    C = max(0, int(context_tokens))

    rewarm = C * cache.write_multiplier * in_to
    per_request = (
        C * cache.read_multiplier * (in_from - in_to)
        + output_tokens * (out_from - out_to)
    )

    if per_request <= 0:
        # The new model is not cheaper per request. Any switch to it is a
        # quality decision, and the re-warm is the price of that decision.
        return Analysis(
            "switch", from_tier, to_tier, C, horizon, rewarm, per_request,
            math.inf, -rewarm + per_request * horizon,
            f"upgrade: costs ${rewarm:.4f} to re-warm, saves nothing per request",
        )

    breakeven = rewarm / per_request
    net = per_request * horizon - rewarm
    return Analysis(
        "switch", from_tier, to_tier, C, horizon, rewarm, per_request, breakeven, net,
        f"pays for itself after {breakeven:.1f} requests; {horizon:.1f} expected",
    )


def analyse_excursion(
    cfg: Config,
    from_tier: int,
    to_tier: int,
    context_tokens: int,
    steps: float,
    appended_tokens: int = 2000,
    output_tokens: int = 500,
    cache: CacheModel | None = None,
) -> Analysis:
    """Price a bounded hop to a cheaper model, then a return to the current one.

    The return is cheap: the old prefix is still cached on the original model,
    so only the tokens appended during the excursion are rewritten.
    """
    cache = cache or CacheModel.for_ttl(cfg.cache_ttl)
    in_from, out_from = _prices(cfg, from_tier)
    in_to, out_to = _prices(cfg, to_tier)
    C = max(0, int(context_tokens))

    hop_cost = C * cache.write_multiplier * in_to
    return_cost = appended_tokens * cache.write_multiplier * in_from
    rewarm = hop_cost + return_cost
    per_request = (
        C * cache.read_multiplier * (in_from - in_to)
        + output_tokens * (out_from - out_to)
    )
    net = per_request * steps - rewarm
    breakeven = rewarm / per_request if per_request > 0 else math.inf

    detail = (
        f"{steps:.0f}-step hop: ${hop_cost:.4f} to warm {tier_name(to_tier)} "
        f"+ ${return_cost:.4f} to rejoin {tier_name(from_tier)}"
    )
    if steps > LOOKBACK_POSITIONS:
        detail += f"; over the {LOOKBACK_POSITIONS}-position lookback, return is a full re-warm"
        return_cost = C * cache.write_multiplier * in_from
        rewarm = hop_cost + return_cost
        net = per_request * steps - rewarm
    return Analysis("excursion", from_tier, to_tier, C, steps, rewarm,
                    per_request, breakeven, net, detail)


def best_option(
    cfg: Config,
    from_tier: int,
    to_tier: int,
    context_tokens: int,
    horizon: float,
    excursion_steps: float = 3.0,
    **kwargs: float,
) -> Analysis:
    """The cheapest of stay / switch / excursion, as an Analysis."""
    stay = Analysis("stay", from_tier, from_tier, int(context_tokens), horizon,
                    0.0, 0.0, 0.0, 0.0, "keep the warm prefix")
    if from_tier == to_tier:
        return stay
    options = [
        stay,
        analyse_switch(cfg, from_tier, to_tier, context_tokens, horizon, **kwargs),
    ]
    if to_tier < from_tier:
        options.append(analyse_excursion(
            cfg, from_tier, to_tier, context_tokens, excursion_steps, **kwargs))
    return max(options, key=lambda a: a.net_saving)


class TurnLength:
    """How many more requests this turn is likely to need.

    Switch economics turn entirely on the horizon, so guessing it badly is the
    main way this module misleads. It starts from a prior and replaces it with
    the observed distribution once the decision log has one.
    """

    def __init__(self, prior_mean: float = 6.0) -> None:
        self.prior_mean = max(1.0, prior_mean)
        self._lengths: list[int] = []

    def observe(self, length: int) -> None:
        if length > 0:
            self._lengths.append(int(length))
            if len(self._lengths) > 4096:
                del self._lengths[: len(self._lengths) // 2]

    @property
    def samples(self) -> int:
        return len(self._lengths)

    def expected_remaining(self, step: int) -> float:
        """E[length - step | length > step], from data when there is enough."""
        step = max(0, int(step))
        if len(self._lengths) < 30:
            # Memoryless prior: expected remaining does not depend on the step.
            return self.prior_mean
        longer = [n for n in self._lengths if n > step]
        if not longer:
            return 1.0
        return max(1.0, sum(n - step for n in longer) / len(longer))

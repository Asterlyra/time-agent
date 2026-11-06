"""The five arms of Study 3.

Every arm shares one interface and, for C/E/O, one enforcement mechanism: the
harness refuses a fetch that cannot finish with enough time left, and forces a
submission once the remaining budget falls to the reserve. The arms differ only
in *where the reserve comes from* — none, nothing, the agent's own declaration,
the harness's empirical estimate, or the true distribution.

Keeping a single enforcement implementation is what makes `C` versus `E` a clean
contrast between "same rule, agent-chosen threshold" and "same rule, harness-chosen
threshold".
"""
import math
import statistics

DENY_NO_COMMIT = '需要在第一次 fetch 之前先提交 {"type":"commit","reserve_s":<秒数>}，声明你为提交预留的时间。'
DENY_NO_TIME = ('按当前实测耗时，这次调用无法在截止前再完成一次提交，已拒绝。'
                '可以改取一个更便宜（体量更小）的编号，或立即提交。')


def _quantile(values, q):
    if not values:
        return None
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    index = min(len(ordered) - 1, max(0, int(round(q * (len(ordered) - 1)))))
    return ordered[index]


class BasePolicy:
    arm = 'I0'
    # Every arm accepts the `commit` action so that the action space is identical;
    # only arm C needs it, and only arm C enforces the declared number.
    allow_commit = True

    def __init__(self, task, collected, durations):
        self.task = task
        self.collected = collected          # item_id -> points, host-side truth
        self.durations = durations          # list of (size, seconds) actually elapsed
        self.declared = None

    # --- informational surface -------------------------------------------
    def size_of(self, item_id):
        return self.task['private']['size_of'][item_id]

    def value_of(self, item_id):
        return self.task['private']['values'][item_id]

    def observed_by_size(self):
        out = {}
        for size in 'SML':
            values = [seconds for name, seconds in self.durations if name == size]
            if values:
                out[size] = {'n': len(values),
                             'mean_s': round(statistics.mean(values), 2),
                             'p90_s': round(_quantile(values, .9), 2)}
        return out

    def remaining_items(self):
        return [item for item in self.task['public']['items']
                if item['id'] not in self.collected]

    def observe(self, context):
        return {}

    # --- enforcement ------------------------------------------------------
    def admit(self, context, item_id, duration):
        return True, ''

    def force_submit(self, context):
        return False

    def record_commit(self, value):
        self.declared = value

    def record_call(self, item_id, duration_s):
        """Called once a call has actually completed: bank the item, log the cost."""
        self.durations.append((self.size_of(item_id), duration_s))
        self.collected[item_id] = self.value_of(item_id)


class ArmI0(BasePolicy):
    arm = 'I0'


class ArmI1(BasePolicy):
    """Everything the harness knows, including the one number the agent cannot see.

    A model never observes how long its own inference takes; it only sees elapsed
    time in which that inference is mixed with the tool. The harness measures it
    directly, so `your_typical_request_s` is not derivable from the trace without
    arithmetic the model has already been shown not to do. This is what makes the
    arm a test of non-redundancy rather than a restatement of the clock.
    """
    arm = 'I1'

    def observe(self, context):
        estimates = self.observed_by_size()
        density = []
        for item in self.remaining_items():
            size = self.size_of(item['id'])
            known = estimates.get(size, {}).get('mean_s')
            density.append({'item': item['id'], 'value': item['value'], 'size': size,
                            'estimated_mean_s': known})
        density.sort(key=lambda row: (-(row['value'] / row['estimated_mean_s'])
                                      if row['estimated_mean_s'] else -row['value']))
        return {'cost_estimates_by_size': estimates,
                'your_typical_request_s': round(context['request_estimate_s'], 1),
                'most_efficient_remaining': density[:3]}


class EnforcingPolicy(BasePolicy):
    """Shared admission + forced-submission logic; subclasses supply the reserve."""

    def reserve_s(self, context):
        raise NotImplementedError

    def expected_call_s(self, item_id, context):
        """Conservative cost estimate, pooled so that sparse sizes stay safe.

        A 90th percentile from one or two draws can be far *below* the true
        quantile, which would make an enforcing arm less safe than the agent it is
        supposed to protect. Taking the maximum of the per-size quantile and the
        pooled quantile over every completed call removes that failure mode.
        """
        estimates = self.observed_by_size()
        all_values = [seconds for _size, seconds in self.durations]
        pooled = _quantile(all_values, .9) if all_values else 0.0
        known = estimates.get(self.size_of(item_id))
        per_size = known['p90_s'] if known else 0.0
        return max(per_size, pooled)

    def admit(self, context, item_id, duration):
        """Allow a call only if, after it finishes, a submission still fits."""
        reserve = self.reserve_s(context)
        if reserve is None:
            return True, ''
        if context['remaining'] - self.expected_call_s(item_id, context) < reserve:
            return False, DENY_NO_TIME
        return True, ''

    def force_submit(self, context):
        """End the episode when nothing affordable is left, not only at the reserve.

        Without the second clause there is a dead zone just above the reserve in
        which every fetch is refused and the episode can only spin until the step
        limit; the agent would then score zero despite having banked items.
        """
        reserve = self.reserve_s(context)
        if reserve is None:
            return False
        if context['remaining'] <= reserve:
            return True
        items = [item['id'] for item in self.remaining_items()]
        if not items:
            return True
        cheapest = min(self.expected_call_s(item, context) for item in items)
        return context['remaining'] - cheapest < reserve + 1e-6

    def observe(self, context):
        return {'harness_policy': {'arm': self.arm, 'reserve_s': round(self.reserve_s(context) or 0.0, 1),
                                   'note': 'harness 会在剩余时间不足时拒绝调用并强制提交'}}


class ArmC(EnforcingPolicy):
    """The agent declares its own reserve; the harness applies exactly that."""

    arm = 'C'
    allow_commit = True

    def reserve_s(self, context):
        return self.declared

    def admit(self, context, item_id, duration):
        if self.declared is None:
            return False, DENY_NO_COMMIT
        return super().admit(context, item_id, duration)


class ArmE(EnforcingPolicy):
    """The harness sets the reserve from its own observations."""

    arm = 'E'

    def reserve_s(self, context):
        """Cover one more *submission request*, which is the model's own latency.

        The harness can only force a submission between requests, so the reserve
        must be large enough that the submission itself completes. Request latency
        is heavy-tailed too, hence the p90 term.
        """
        median = context['request_estimate_s']
        p90 = context.get('request_p90_s', median)
        return max(1.5 * p90, median + 4.0, 6.0)


class ArmO(EnforcingPolicy):
    """A planner that knows the true per-size distribution."""

    arm = 'O'

    def reserve_s(self, context):
        median = context['request_estimate_s']
        p90 = context.get('request_p90_s', median)
        return max(1.25 * p90, median + 3.0, 5.0)

    def expected_call_s(self, item_id, context):
        means = self.task['private']['size_means']
        sigma = self.task['private']['sigma']
        mu = means[self.size_of(item_id)]
        # 75th percentile of the log-normal draw
        return mu * math.exp(0.6745 * sigma)

    def observe(self, context):
        return super().observe(context)


ARMS = {'I0': ArmI0, 'I1': ArmI1, 'C': ArmC, 'E': ArmE, 'O': ArmO}


def make_policy(arm, task, collected, durations):
    if arm not in ARMS:
        raise ValueError('unknown arm')
    return ARMS[arm](task, collected, durations)

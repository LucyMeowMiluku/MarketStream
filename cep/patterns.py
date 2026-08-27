# =============================================================================
# function：
# =============================================================================
"""Anomaly patterns expressed as finite-state automata.

Each automaton recognises an ordered sequence of primitive events. These are
the "complex events" of the CEP layer — multi-step market behaviours that a
point-wise detector cannot express. Severities are chosen so a confirmed
sequence outranks a lone primitive (see ``cep.cep_detector``).

**Positive-sequence patterns** (fire when a sequence completes):

* ``volume_led_breakout`` — volume surge → price jump.
* ``news_driven_selloff`` — sentiment drop → price fall.
* ``flash_reversal`` — sharp move → immediate retrace.
* ``panic_compound`` — volume surge → sentiment drop → price fall.

**Negation patterns** (fire on event *absence*):

* ``failed_breakout`` — volume surge → NO price jump within 3 windows.
* ``sustained_selloff`` — price fall → NO rebound within 2 windows.

**Kleene patterns** (fire after repeated events):

* ``sustained_accumulation`` — volume surge ×3+ → price jump.
"""

from cep.automaton import (
    NegationEdge,
    NFAEventAutomaton,
    RepeatEdge,
    Transition,
)
from cep.events import (
    PRICE_JUMP_DOWN,
    PRICE_JUMP_UP,
    SENTIMENT_DROP,
    VOLUME_SURGE,
)
from cep.guards import feature_abs_gt


def build_default_automata(
    max_gap: int = 3,
) -> tuple[list[NFAEventAutomaton], list[NFAEventAutomaton]]:
    """Construct the default pattern automata.

    Returns ``(base_automata, meta_automata)``.  Base automata run first;
    when one reaches accept it emits a synthetic ``PATTERN:<name>`` event.
    Meta-automata run second on the enriched event set, enabling higher-order
    patterns that compose sub-pattern completions.
    """
    # 目标：将低阶市场事件组合成有时间边界的复杂事件。
    # 关键设计：max_gap 是默认等待窗口，特定转移可以用更严格的局部窗口覆盖它。
    # 解决的问题：过早过期会漏掉完整序列，无界等待又会将相隔很远的无关事件误配。
    # 参考依据：[R07] 参考了复杂事件的序列关联思想；以下金融模式与参数是项目设计。
    base = [
        # --- Positive-sequence patterns ---
        # 目标：捕捉“成交量先放大，价格随后快速变化”的量价顺序。
        # 关键设计：上涨和下跌都可完成模式，因为此处检测的是放量后的显著价格响应。
        NFAEventAutomaton(
            name="volume_led_breakout",
            transitions=[
                Transition(0, VOLUME_SURGE, 1),
                Transition(1, PRICE_JUMP_UP, 2),
                Transition(1, PRICE_JUMP_DOWN, 2),
            ],
            accept_state=2,
            severity=0.85,
            max_gap=2,
        ),
        # 目标：要求负面情绪先出现，然后在有界窗口内观察到价格下跌。
        # 解决的问题：避免只因为某个窗口的情绪值较低就直接判定抛售。
        NFAEventAutomaton(
            name="news_driven_selloff",
            transitions=[
                Transition(0, SENTIMENT_DROP, 1),
                Transition(1, PRICE_JUMP_DOWN, 2),
            ],
            accept_state=2,
            severity=0.90,
            max_gap=max_gap,
        ),
        # 目标：识别快速上涨后下跌，或快速下跌后上涨的短时反转。
        # 关键设计：状态 1/2 分别记住首次移动方向，反向事件必须在 1 个窗口内出现。
        NFAEventAutomaton(
            name="flash_reversal",
            transitions=[
                Transition(0, PRICE_JUMP_UP, 1),
                Transition(0, PRICE_JUMP_DOWN, 2),
                Transition(1, PRICE_JUMP_DOWN, 3, max_gap=1),
                Transition(2, PRICE_JUMP_UP, 3, max_gap=1),
            ],
            accept_state=3,
            severity=0.80,
            max_gap=2,
        ),
        # 目标：将放量、情绪走弱和价格下跌三步证据组合为复合恐慌模式。
        # 关键设计：情绪可以比默认窗口晚 1 步，但价格确认必须在随后 2 个窗口内完成。
        NFAEventAutomaton(
            name="panic_compound",
            transitions=[
                Transition(0, VOLUME_SURGE, 1),
                Transition(1, SENTIMENT_DROP, 2, max_gap=max_gap + 1),
                Transition(2, PRICE_JUMP_DOWN, 3, max_gap=2),
            ],
            accept_state=3,
            severity=1.0,
            max_gap=max_gap,
        ),
        # --- Negation patterns ---
        # 目标：检测“期待事件没有出现”，而不是只检测已发生的事件。
        # 关键设计：severity=0.50 可以推进后续组合，但 score=-0.50 不会单独突破 < -0.50 的告警阈值。
        # 解决的问题：“缺失”在正常数据中很常见，限制严重度可避免大量独立误报。
        # 量能激增后若连续 2 个窗口都没有向上突破，则记录突破失败。
        NFAEventAutomaton(
            name="failed_breakout",
            transitions=[
                Transition(0, VOLUME_SURGE, 1),
            ],
            accept_state=2,
            severity=0.50,
            max_gap=max_gap,
            negations=[
                NegationEdge(
                    from_state=1,
                    absent_event=PRICE_JUMP_UP,
                    to_state=2,
                    timeout=2,
                ),
            ],
        ),
        # 价格跌幅必须先超过 3%，随后连续 2 个窗口没有向上反弹，才确认持续抛售。
        # 关键设计：guard 先排除幅度过小的普通波动，NegationEdge 再检查反弹是否缺失。
        NFAEventAutomaton(
            name="sustained_selloff",
            transitions=[
                Transition(
                    0,
                    PRICE_JUMP_DOWN,
                    1,
                    guard=feature_abs_gt("price_change_rate", 0.03),
                ),
            ],
            accept_state=2,
            severity=0.50,
            max_gap=max_gap,
            negations=[
                NegationEdge(
                    from_state=1,
                    absent_event=PRICE_JUMP_UP,
                    to_state=2,
                    timeout=2,
                ),
            ],
        ),
        # --- Kleene patterns ---
        # 目标：要求量能激增至少重复 3 个窗口，再等待价格确认。
        # 解决的问题：单次放量可能是噪声，RepeatEdge 用持续性条件减少偶发匹配。
        NFAEventAutomaton(
            name="sustained_accumulation",
            transitions=[
                Transition(0, VOLUME_SURGE, 1),
                Transition(1, PRICE_JUMP_UP, 2),
                Transition(1, PRICE_JUMP_DOWN, 2),
            ],
            accept_state=2,
            severity=0.90,
            max_gap=2,
            repeats=[
                RepeatEdge(state=1, event=VOLUME_SURGE, min_count=3),
            ],
        ),
    ]

    # 关键变量：基础模式命中后会以 PATTERN:<name> 的合成事件形式传给元自动机。
    # 解决的问题：元模式不需要重复理解基础模式内部的所有低阶转移。
    PATTERN_FLASH = "PATTERN:flash_reversal"
    PATTERN_BREAKOUT = "PATTERN:volume_led_breakout"
    PATTERN_SELLOFF = "PATTERN:news_driven_selloff"

    meta = [
        # --- Hierarchical / compositional patterns ---
        # 目标：闪电反转后又出现量能激增，用成交量对反转模式做二次确认。
        NFAEventAutomaton(
            name="reversal_confirmed",
            transitions=[
                Transition(0, PATTERN_FLASH, 1),
                Transition(1, VOLUME_SURGE, 2),
            ],
            accept_state=2,
            severity=0.95,
            max_gap=5,
        ),
        # 目标：先命中放量突破，后命中新闻驱动抛售，以识别跨基础模式的反转。
        # 关键设计：10 个窗口是两个完整模式之间的最大关联距离，防止无关历史命中被重新组合。
        NFAEventAutomaton(
            name="pump_and_dump",
            transitions=[
                Transition(0, PATTERN_BREAKOUT, 1),
                Transition(1, PATTERN_SELLOFF, 2),
            ],
            accept_state=2,
            severity=1.0,
            max_gap=10,
        ),
    ]

    # 返回顺序是不变量：调用方必须先运行 base，将命中补入事件集后再运行 meta。
    return base, meta

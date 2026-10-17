"""Authoritative game rules. Coins are binary64; diamonds are signed int64."""
from __future__ import annotations

import math
import random
import sys
import time

F64_MAX = sys.float_info.max
GOLD_CAP = math.nextafter(F64_MAX, 0.0)
INT64_MAX = (1 << 63) - 1
EXCHANGE_THRESHOLD = 1_000_000_000 * 10**12  # Strictly MORE than one billion 兆.
EXCHANGE_UNIT = 10**12
MAX_LEVEL = 870
LOG_CAP = math.log10(GOLD_CAP)
GROWTH = (math.log10(50 * 10**12) - 3.5) / 29
RNG = random.SystemRandom()

FISH = [
    dict(id="lantern", name="独眼灯笼鱼", latin="MONOCULUS LUCERNA", rarity="常见", color="#b7d3a2", weight=40, unlock=1, bonus=1, kind="angler", length="32—68 cm", description="它的灯不会照亮海底，只会照亮你的梦。"),
    dict(id="bone", name="玻璃骨鲈", latin="OS VITREUM", rarity="常见", color="#94c5b5", weight=28, unlock=1, bonus=1.15, kind="skeleton", length="18—41 cm", description="透过它的身体，你能看见昨天沉没的船。"),
    dict(id="eyes", name="千目鲷", latin="OCULUS MILLE", rarity="稀有", color="#c1aaeb", weight=15, unlock=1, bonus=1.8, kind="eyes", length="46—92 cm", description="闭上眼睛也没有用。它总有一只眼睛在看着你。"),
    dict(id="jelly", name="低语水母", latin="MEDUSA SUSURRUS", rarity="稀有", color="#a7b4ee", weight=10, unlock=5, bonus=2.2, kind="jelly", length="70—120 cm", description="水下没有声音。那为什么，你听见了自己的名字？"),
    dict(id="eel", name="缝口海鳗", latin="ANGUILLA SUTURA", rarity="史诗", color="#ddb18c", weight=5, unlock=12, bonus=3, kind="eel", length="2.1—4.8 m", description="每一道缝线里，都藏着一封没有送出的遗书。"),
    dict(id="void", name="无名之物", latin="[ SIGNAL REDACTED ]", rarity="传说", color="#e2c16d", weight=2, unlock=25, bonus=5, kind="void", length="无法测量", description="图鉴里原本没有这一页。它是什么时候出现的？"),
    dict(id="moon", name="倒悬月魟", latin="LUNA INVERSA", rarity="史诗", color="#cfa6cc", weight=4, unlock=40, bonus=3.5, kind="ray", length="3.2—6.1 m", description="它在没有月亮的夜里，投下一道月光。"),
    dict(id="ancient", name="深渊回声", latin="ABYSSUS AETERNA", rarity="传说", color="#dc987f", weight=1, unlock=80, bonus=6, kind="ancient", length="∞ ?", description="声呐回来了。船上的每一个人，都少了一次心跳。"),
]
GEAR = {
    "net": dict(name="自动拖网", max=12, unlock=5),
    "sonar": dict(name="异变声呐", max=10, unlock=1),
    "charm": dict(name="深渊护符", max=10, unlock=30),
}
# A larger diamonds-per-兆 result always has a smaller probability.
RATES = ((1, 60.0), (10, 25.0), (100, 10.0), (1000, 4.0), (10000, 0.9), (1000000, 0.1))


class RuleError(Exception):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


def bounded(value):
    value = float(value)
    if math.isnan(value) or value < 0:
        raise ValueError("Invalid coin value")
    return min(value, GOLD_CAP)


def add_gold(a, b):
    a, b = bounded(a), bounded(b)
    return GOLD_CAP if b >= GOLD_CAP - a else min(a + b, GOLD_CAP)


def from_log(log_value):
    # Avoid evaluating 10**308.2547, which can overflow due to rounding.
    return GOLD_CAP if log_value >= LOG_CAP else min(10.0**log_value, GOLD_CAP)


def typical(level):
    return from_log(3.5 + (level - 1) * GROWTH)


def level_cost(level):
    return min(typical(level) * 0.35, GOLD_CAP)


def new_player(now=None):
    now = time.time() if now is None else now
    return dict(gold=0.0, diamonds=0, level=1, catches=0, total_gold=0.0,
                gear={k: 0 for k in GEAR}, collection={}, history=[],
                auto=False, auto_at=now, last_cast=0.0, created_at=now,
                exchanges=0, best=0.0, version=1)


def gear_cost(p, key):
    rank = p["gear"][key]
    if key == "charm":
        return 10 * 5**rank
    return from_log(math.log10(typical(p["level"])) + math.log10(1.4 if key == "net" else 0.8) + rank * 0.30)


def catch_fish(p, rng=None, source="manual", now=None):
    rng = rng or RNG
    eligible = [f for f in FISH if f["unlock"] <= p["level"]]
    weights = [f["weight"] * (1 + p["gear"]["sonar"] * 0.22 if f["rarity"] not in ("常见",) else 1) for f in eligible]
    fish = rng.choices(eligible, weights=weights, k=1)[0]
    log_mid = 3.5 + (p["level"] - 1) * GROWTH
    spread = 2.5 + (0.15 - 2.5) * min((p["level"] - 1) / 29, 1)
    log_reward = log_mid + rng.uniform(-spread, spread)
    log_reward += math.log10(fish["bonus"]) + p["gear"]["charm"] * math.log10(2)
    reward = from_log(log_reward)
    if p["level"] == 1:
        reward = min(1_000_000.0, max(10.0, reward))
    reward = bounded(reward)
    p["gold"] = add_gold(p["gold"], reward)
    p["total_gold"] = add_gold(p["total_gold"], reward)
    p["catches"] += 1
    p["best"] = max(p["best"], reward)
    is_new = fish["id"] not in p["collection"]
    p["collection"][fish["id"]] = p["collection"].get(fish["id"], 0) + 1
    item = dict(fish=fish["id"], gold=reward, new=is_new, source=source,
                time=time.time() if now is None else now,
                size=round(rng.uniform(0.4, 9.8), 2))
    p["history"] = [item] + p["history"][:19]
    return item


def net_interval(p):
    return max(1.0, 4.0 - p["gear"]["net"] * 0.25)


def manual_catch(p, now=None):
    now = time.time() if now is None else now
    if now - p["last_cast"] < 0.65:
        raise RuleError("鱼线还在回收，请稍候", 429)
    p["last_cast"] = now
    return dict(catch=catch_fish(p, now=now))


def set_net(p, enabled, now=None):
    if type(enabled) is not bool:
        raise RuleError("拖网开关必须为布尔值")
    if not p["gear"]["net"]:
        raise RuleError("先在船坞购买自动拖网")
    if p["auto"] != enabled:
        p["auto"], p["auto_at"] = enabled, time.time() if now is None else now
    return dict(auto=p["auto"], message="自动拖网已开启" if enabled else "自动拖网已暂停")


def settle_auto(p, now=None):
    now = time.time() if now is None else now
    if not p["auto"] or not p["gear"]["net"]:
        p["auto_at"] = now
        return 0
    interval = net_interval(p)
    # Offline income is bounded to one hour, and each fish uses the same rules.
    elapsed = min(max(now - p["auto_at"], 0), 3600.0)
    count = int(elapsed // interval)
    for _ in range(count):
        catch_fish(p, source="auto", now=now)
    p["auto_at"] = now - (elapsed - count * interval)
    return count


def upgrade_player(p, mode="one"):
    if mode not in ("one", "max"):
        raise RuleError("未知的升级方式")
    bought = 0
    while p["level"] < MAX_LEVEL:
        cost = level_cost(p["level"])
        if p["gold"] < cost:
            break
        p["gold"] = max(0.0, p["gold"] - cost)
        p["level"] += 1
        bought += 1
        if mode == "one":
            break
    if not bought:
        raise RuleError("已抵达深渊尽头" if p["level"] == MAX_LEVEL else "金币不足，先试着捕一条鱼")
    return dict(levels=bought, message=f"潜航员等级提升至 Lv.{p['level']}")


def upgrade_gear(p, key):
    if key not in GEAR:
        raise RuleError("未知的装备")
    spec = GEAR[key]
    if p["level"] < spec["unlock"]:
        raise RuleError(f"Lv.{spec['unlock']} 解锁{spec['name']}")
    if p["gear"][key] >= spec["max"]:
        raise RuleError("该装备已满级")
    cost = gear_cost(p, key)
    currency = "diamonds" if key == "charm" else "gold"
    if p[currency] < cost:
        raise RuleError("钻石不足" if currency == "diamonds" else "金币不足")
    p[currency] -= cost
    p["gear"][key] += 1
    if key == "net" and p["gear"][key] == 1:
        p["auto"] = True
        p["auto_at"] = time.time()
    return dict(message=f"{spec['name']}已升级")


def exchange(p, fraction, rng=None):
    if p["level"] < 30:
        raise RuleError("黑市兑换在 Lv.30 解锁")
    if type(fraction) is not int or fraction not in (25, 50, 100):
        raise RuleError("兑换比例只能为 25、50 或 100")
    rng = rng or RNG
    if p["gold"] > EXCHANGE_THRESHOLD:
        # The threshold applies to holdings, regardless of the selected fraction.
        spent, rate, minted = p["gold"], None, INT64_MAX
        p["gold"] = 0.0
    else:
        units = math.floor((p["gold"] * (fraction / 100)) / EXCHANGE_UNIT)
        if units < 1:
            raise RuleError("所选份额不足 1 兆金币")
        spent = float(units * EXCHANGE_UNIT)
        rate = rng.choices([r[0] for r in RATES], weights=[r[1] for r in RATES], k=1)[0]
        minted = units * rate
        p["gold"] = max(0.0, p["gold"] - spent)
    # Use integer arithmetic throughout. Discard the excess rather than wrap.
    awarded = min(minted, INT64_MAX - p["diamonds"])
    destroyed = minted - awarded
    p["diamonds"] += awarded
    p["exchanges"] += 1
    return dict(spent=spent, rate=rate, minted=str(minted), awarded=str(awarded),
                destroyed=str(destroyed), special=rate is None,
                message=f"兑换成功，获得 {awarded:,} 钻石" + ("，超额部分已销毁" if destroyed else ""))


def public_state(p):
    gear = {}
    for key, spec in GEAR.items():
        cost = gear_cost(p, key)
        gear[key] = dict(**spec, rank=p["gear"][key], cost=str(cost) if key == "charm" else cost,
                         currency="diamonds" if key == "charm" else "gold")
    return dict(gold=p["gold"], diamonds=str(p["diamonds"]), level=p["level"],
                catches=p["catches"], total_gold=p["total_gold"], best=p["best"],
                collection=p["collection"], history=p["history"], auto=p["auto"],
                interval=net_interval(p), gear=gear, cost=level_cost(p["level"]),
                typical=typical(p["level"]), max_level=MAX_LEVEL,
                exchange_unlocked=p["level"] >= 30, exchanges=p["exchanges"],
                limits=dict(gold=GOLD_CAP, f64_max=F64_MAX, diamonds=str(INT64_MAX),
                            exchange_threshold=EXCHANGE_THRESHOLD),
                rates=[dict(rate=r, probability=w) for r, w in RATES])

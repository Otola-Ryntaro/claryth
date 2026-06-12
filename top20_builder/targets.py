"""Concrete representative ingredients for the interaction-hub top 20."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Target:
    id: str
    rank: int
    label: str
    group_label: str
    document_terms: tuple[str, ...]
    match_terms: tuple[str, ...]
    excluded_brand_terms: tuple[str, ...] = ()


TARGETS = (
    Target("warfarin", 1, "ワルファリン", "抗凝固薬", ("ワルファリンカリウム",), ("ワルファリン", "ワルファリンカリウム")),
    Target("clarithromycin", 2, "クラリスロマイシン", "マクロライド系抗菌薬", ("クラリスロマイシン",), ("クラリスロマイシン", "クラリス", "クラリシッド")),
    Target("ritonavir", 3, "リトナビル", "強力CYP3A阻害薬", ("リトナビル",), ("リトナビル", "ノービア")),
    Target("rifampicin", 4, "リファンピシン", "酵素誘導薬", ("リファンピシン",), ("リファンピシン", "リファジン")),
    Target("carbamazepine", 5, "カルバマゼピン", "酵素誘導型抗てんかん薬", ("カルバマゼピン",), ("カルバマゼピン", "テグレトール")),
    Target("itraconazole", 6, "イトラコナゾール", "アゾール系抗真菌薬", ("イトラコナゾール",), ("イトラコナゾール", "イトリゾール")),
    Target("amiodarone", 7, "アミオダロン", "抗不整脈薬", ("アミオダロン",), ("アミオダロン", "アンカロン")),
    Target("apixaban", 8, "アピキサバン", "DOAC", ("アピキサバン",), ("アピキサバン", "エリキュース")),
    Target("tacrolimus", 9, "タクロリムス", "カルシニューリン阻害薬（全身投与）", ("タクロリムス",), ("タクロリムス", "プログラフ", "グラセプター"), ("軟膏",)),
    Target("methotrexate", 10, "メトトレキサート", "葉酸代謝拮抗薬", ("メトトレキサート",), ("メトトレキサート", "リウマトレックス")),
    Target("digoxin", 11, "ジゴキシン", "強心配糖体", ("ジゴキシン",), ("ジゴキシン", "ジゴシン")),
    Target("colchicine", 12, "コルヒチン", "抗炎症薬", ("コルヒチン",), ("コルヒチン",)),
    Target("atorvastatin", 13, "アトルバスタチン", "スタチン", ("アトルバスタチン",), ("アトルバスタチン", "リピトール")),
    Target("azelnidipine", 14, "アゼルニジピン", "Ca拮抗薬", ("アゼルニジピン",), ("アゼルニジピン", "カルブロック")),
    Target("suvorexant", 15, "スボレキサント", "睡眠薬・鎮静薬", ("スボレキサント",), ("スボレキサント", "ベルソムラ")),
    Target("quetiapine", 16, "クエチアピン", "抗精神病薬・QT関連薬", ("クエチアピン",), ("クエチアピン", "セロクエル")),
    Target("sertraline", 17, "セルトラリン", "セロトニン系薬", ("セルトラリン",), ("セルトラリン", "ジェイゾロフト")),
    Target("loxoprofen", 18, "ロキソプロフェン", "NSAIDs（内服）", ("ロキソプロフェン",), ("ロキソプロフェン", "ロキソニン"), ("テープ", "パップ", "ゲル", "ローション")),
    Target("eplerenone", 19, "エプレレノン", "MRA・RAAS系薬", ("エプレレノン",), ("エプレレノン", "セララ")),
    Target("theophylline", 20, "テオフィリン", "メチルキサンチン", ("テオフィリン",), ("テオフィリン", "テオドール", "ユニフィル")),
)

TARGET_BY_ID = {target.id: target for target in TARGETS}
DEFAULT_TARGET_ID = "clarithromycin"

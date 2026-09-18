from flask import Flask, request, render_template_string, send_file
from vehicles import vehicles
from pdf_report import create_pdf
from openai import OpenAI
import os
import math

app = Flask(__name__)


# =========================
# 業種別ルール
# =========================

BUSINESS_RULES = {
    "訪問介護": {
        "distance": 3,
        "visits": 5,
        "luggage": 4,
        "current_vehicle": 2,
        "license": 1
    },
    "配送": {
        "distance": 5,
        "visits": 3,
        "luggage": 6,
        "current_vehicle": 2,
        "license": 1
    },
    "営業": {
        "distance": 5,
        "visits": 3,
        "luggage": 2,
        "current_vehicle": 2,
        "license": 1
    },
    "訪問販売": {
        "distance": 4,
        "visits": 4,
        "luggage": 3,
        "current_vehicle": 2,
        "license": 1
    },
    "その他": {
        "distance": 3,
        "visits": 3,
        "luggage": 3,
        "current_vehicle": 2,
        "license": 1
    }
}


# =========================
# 診断
# =========================


def simulate_welfare(
    employees,
    work_days,
    subsidy_per_employee,
    current_time_per_day,
    bike_time_per_day
):
    monthly_company_cost = employees * subsidy_per_employee
    annual_company_cost = monthly_company_cost * 12

    time_saved_per_day = max(
        current_time_per_day - bike_time_per_day,
        0
    )

    annual_time_saved_per_employee = (
        time_saved_per_day * work_days * 12 / 60
    )

    annual_time_saved_all = (
        annual_time_saved_per_employee * employees
    )

    return {
        "employees": employees,
        "work_days": work_days,
        "subsidy_per_employee": subsidy_per_employee,
        "monthly_company_cost": monthly_company_cost,
        "annual_company_cost": annual_company_cost,
        "time_saved_per_day": time_saved_per_day,
        "annual_time_saved_per_employee": annual_time_saved_per_employee,
        "annual_time_saved_all": annual_time_saved_all
    }

def diagnose(
    business,
    distance,
    visits,
    current_vehicle,
    luggage,
    slope,
    parking,
    charging
):

    rule = BUSINESS_RULES.get(
        business,
        BUSINESS_RULES["その他"]
    )

    results = []

    for vehicle in vehicles:

        score = 0
        reasons = []
        cautions = []

        # 航続距離
        if distance <= vehicle["range_km"] * 0.6:

            score += rule["distance"] + 2

            reasons.append(
                f"航続距離に比較的大きな余裕があります（約{vehicle['range_km']}km）"
            )

        elif distance <= vehicle["range_km"]:

            score += rule["distance"]

            reasons.append(
                f"1日の移動距離に対応可能な範囲です（約{vehicle['range_km']}km）"
            )

        else:

            score -= 5

            cautions.append(
                "1日の移動距離に対して航続距離が不足する可能性があります"
            )

        # 訪問件数
        if visits >= 8:

            score += rule["visits"]

            reasons.append(
                f"訪問件数が多く、移動手段変更による効果を検証しやすい条件です（{visits}件）"
            )

        elif visits >= 4:

            score += max(1, rule["visits"] - 1)

            reasons.append(
                f"複数回の訪問があり、電動二輪との相性を検証できます（{visits}件）"
            )

        else:

            score += 1

        # 現在の移動手段
        if current_vehicle == "車":

            score += rule["current_vehicle"]

            reasons.append(
                "現在が車移動のため、移動時間・駐車面の改善を検証できます"
            )

        elif current_vehicle == "公共交通":

            score += 1

        # 荷物
        if luggage == "少ない":

            score += rule["luggage"]

            reasons.append(
                "荷物が少なく、二輪導入と相性を確認しやすい条件です"
            )

        elif luggage == "普通":

            score += max(1, rule["luggage"] - 1)

            reasons.append(
                "荷物量は大きな障壁になりにくい条件です"
            )

            cautions.append(
                "実際の荷物サイズ・重量は現場で確認してください"
            )

        else:

            cautions.append(
                "荷物が多いため、積載方法・重量・収納スペースの確認が必要です"
            )

        # 免許
        if not vehicle["license_required"]:

            score += rule["license"]

            reasons.append(
                "免許条件の面で導入検討しやすい車両です"
            )

        else:

            cautions.append(
                "運転免許・利用条件の確認が必要です"
            )

        # 坂道
        if slope == "多い":

            cautions.append(
                "坂道が多いため、実際のルートで走行性能を確認してください"
            )

        elif slope == "普通":

            cautions.append(
                "坂道があるため、実際のルートで走行テストを推奨します"
            )

        # 駐車
        if parking == "難しい":

            score += 2

            reasons.append(
                "駐車が難しい環境のため、二輪化による駐車負担軽減を検証できます"
            )

        elif parking == "普通":

            reasons.append(
                "駐車環境によっては二輪化のメリットを検証できます"
            )

        # 充電環境
        if charging == "既に利用可能":
            score += 2
            reasons.append(
                "充電環境が既に確保されており、導入後の運用を始めやすい条件です"
            )

        elif charging == "導入時に用意可能":
            score += 1
            reasons.append(
                "現在は充電環境がなくても、導入時に整備できれば運用可能です"
            )

        elif charging == "用意が難しい":
            score -= 2
            cautions.append(
                "充電環境の確保が難しいため、導入前に充電方法・保管場所を確認する必要があります"
            )

        elif charging == "要確認":
            cautions.append(
                "充電環境について現地確認が必要です"
            )
        results.append({
            "vehicle": vehicle,
            "score": score,
            "reasons": reasons,
            "cautions": cautions
        })

    results.sort(
        key=lambda x: x["score"],
        reverse=True
    )

    return results


# =========================
# AI診断コメント
# =========================

def make_comment(
    business,
    distance,
    visits,
    current_vehicle,
    luggage,
    slope,
    parking,
    charging,
    results
):

    top = results[0]

    comment = (
        f"{business}の業務条件では、電動二輪の導入可能性を検討できるケースです。"
        f"1日の移動距離は{distance}km、訪問件数は{visits}件で、"
        f"現在の移動手段は{current_vehicle}です。"
    )

    comment += (
        f"荷物は「{luggage}」、坂道は「{slope}」、"
        f"駐車環境は「{parking}」、充電環境は「{charging}」という条件です。"
    )

    comment += (
        f"今回の条件では、{top['vehicle']['name']}が"
        f"条件一致度{top['score']}点となりました。"
    )

    comment += (
        "ただし、これは現時点でのルールベース診断による参考結果です。"
        "実際の導入判断では、現場ルート・荷物・駐車・充電環境を実証実験で確認することを推奨します。"
    )

    return comment


# =========================
# AIに渡す診断データ
# =========================

def build_ai_input(
    business,
    distance,
    visits,
    current_vehicle,
    luggage,
    slope,
    parking,
    charging,
    results
):
    top = results[0]

    lines = []

    lines.append("【二輪導入診断データ】")
    lines.append("")
    lines.append("■ 業務条件")
    lines.append(f"業種：{business}")
    lines.append(f"1日の移動距離：{distance}km")
    lines.append(f"1日の訪問件数：{visits}件")
    lines.append(f"現在の移動手段：{current_vehicle}")
    lines.append(f"荷物：{luggage}")
    lines.append("")

    lines.append("■ ルート・運用条件")
    lines.append(f"坂道：{slope}")
    lines.append(f"駐車環境：{parking}")
    lines.append(f"充電環境：{charging}")
    lines.append("")

    lines.append("■ 車両比較")

    for i, result in enumerate(results, start=1):
        v = result["vehicle"]
        sim = result.get("sim", {})

        max_load = (
            f'{v["max_load_kg"]}kg'
            if v["max_load_kg"]
            else "要確認"
        )

        license = (
            "必要"
            if v["license_required"]
            else "不要"
        )

        payback = sim.get("payback_years")

        payback_text = (
            f"{payback:.1f}年"
            if payback
            else "算出不可"
        )

        lines.append(f"{i}. {v['name']}")
        lines.append(f"条件一致度：{result['score']}点")
        lines.append(f"航続距離：約{v['range_km']}km")
        lines.append(f"重量：{v['weight_kg']}kg")
        lines.append(f"価格：{v['price_yen']:,}円" if v["price_yen"] is not None else "価格：要確認")
        lines.append(f"充電時間：{v['charge_time']}")
        lines.append(f"最大積載：{max_load}")
        lines.append(f"免許：{license}")
        lines.append(
            f"月間コスト差：約{sim.get('monthly_cost_difference', 0):,.0f}円"
        )
        lines.append(
            f"年間移動時間削減：約{sim.get('annual_time_difference_hours', 0):.1f}時間"
        )
        lines.append(
            f"年間コスト差：約{sim.get('annual_cost_difference', 0):,.0f}円"
        )
        lines.append(
            f"年間合計効果：約{sim.get('annual_total_effect', 0):,.0f}円"
        )
        lines.append(
            f"参考回収期間：約{payback_text}"
        )
        lines.append(
            f"適合理由：{' / '.join(result['reasons'])}"
        )
        lines.append(
            f"注意点：{' / '.join(result['cautions']) if result['cautions'] else '現時点で大きな注意点なし'}"
        )
        lines.append("")

    lines.append("■ 試算についての重要事項")
    lines.append(
        "年間合計効果は、燃料費等のコスト差と時間価値を組み合わせた参考試算であり、実際の利益やキャッシュ削減額を保証するものではない。"
    )
    lines.append(
        "参考回収期間は簡易計算であり、保険・税金・整備費・消耗品費などを含まない。"
    )
    lines.append(
        "車両の航続距離などの性能値は使用条件によって変動するため、実際の導入前に確認が必要。"
    )

    return "\n".join(lines)


# =========================
# AI用システムプロンプト
# =========================

AI_SYSTEM_PROMPT = """
あなたは企業の業務改善を支援するアナリストです。

電動二輪の導入を検討している企業に対して、
与えられた診断データをもとに分析コメントを作成してください。

【重要ルール】
・与えられたデータ以外の事実を勝手に推測しない
・不明な情報は「要確認」とする
・電動二輪の導入を無条件に推奨しない
・シミュレーション結果は参考値として扱う
・車両性能を保証する表現をしない
・メリットだけでなくリスクや注意点も説明する
・企業担当者が理解しやすい文章にする
・過度に長くしない
・最終的な導入判断は企業側が行うものとして説明する

以下の順番で回答してください。

1. この業務で電動二輪を検討できる理由
2. 期待できるメリット
3. 注意すべきリスク
4. 実証実験で確認すべきこと
5. 企業担当者への提案
"""


# =========================
# OpenAIによるAI診断コメント生成
# =========================

def generate_ai_comment(ai_input):
    api_key = os.getenv("OPENAI_API_KEY")

    if not api_key:
        return "現在はAI API導入前のため、診断ロジックによる結果を表示しています。今後、AI APIを接続し、診断結果をもとに企業ごとの分析・提案コメントを自動生成します。"

    client = OpenAI(api_key=api_key)

    response = client.responses.create(
        model="gpt-5.6-luna",
        instructions=AI_SYSTEM_PROMPT,
        input=ai_input
    )

    return response.output_text


# =========================
# 導入判定
# =========================

def make_adoption_judgment(
    distance,
    visits,
    luggage,
    slope,
    parking,
    charging,
    results
):

    top = results[0]

    score = top["score"]

    danger = False

    if distance > top["vehicle"]["range_km"]:
        danger = True

    if charging == "用意が難しい":
        danger = True

    if luggage == "多い":
        danger = True

    if danger:

        status = "🟡 条件付きで検証"

        explanation = (
            "現時点では導入に確認すべき条件があります。"
            "まず小規模な実証実験で運用可能性を確認する段階です。"
        )

    elif score >= 13:

        status = "🟢 試験導入候補"

        explanation = (
            "業務条件と電動二輪の相性を確認しやすい条件です。"
            "まずは小規模な試験導入から検証できます。"
        )

    else:

        status = "🟡 条件付きで検証"

        explanation = (
            "一定の導入メリットが考えられますが、"
            "実際のルートや運用条件を確認してから判断する段階です。"
        )

    return {
        "status": status,
        "explanation": explanation
    }


# =========================
# 実証実験プラン
# =========================

def make_pilot_plan(
    business,
    visits,
    current_vehicle,
    luggage,
    slope,
    parking,
    charging
):

    if visits >= 8:

        staff = "訪問件数の多いスタッフ1名"

    elif visits >= 4:

        staff = "日常的に訪問業務を行うスタッフ1名"

    else:

        staff = "代表的な業務を担当するスタッフ1名"

    period = "1週間"

    if current_vehicle == "車":

        comparison = "現在の車移動 vs 電動二輪"

    else:

        comparison = f"現在の{current_vehicle} vs 電動二輪"

    records = [
        "1日の移動時間",
        "1日の走行距離",
        "訪問件数",
        "充電回数",
        "駐車にかかった時間",
        "荷物の積載状況",
        "スタッフの使いやすさ評価"
    ]

    checks = []

    if slope in ["普通", "多い"]:

        checks.append(
            "坂道での走行性能"
        )

    if parking == "難しい":

        checks.append(
            "訪問先での駐車・停車のしやすさ"
        )

    if charging == "用意が難しい":

        checks.append(
            "充電・保管方法"
        )

    if luggage == "多い":

        checks.append(
            "荷物の積載量・収納方法"
        )

    return {
        "staff": staff,
        "period": period,
        "comparison": comparison,
        "records": records,
        "checks": checks
    }


# =========================
# KPI生成
# =========================

def make_kpis(
    car_time,
    bike_time,
    visits
):

    time_difference = car_time - bike_time

    kpis = []

    # 移動時間
    if time_difference > 0:

        kpis.append({
            "name": "移動時間",
            "target": f"1日あたり{time_difference:.0f}分以上の短縮",
            "why": "移動時間の削減効果を確認"
        })

    else:

        kpis.append({
            "name": "移動時間",
            "target": "車移動と同等以上",
            "why": "業務効率を維持できるか確認"
        })

    # 訪問件数
    kpis.append({
        "name": "訪問件数",
        "target": f"{visits}件の業務を問題なく完了",
        "why": "二輪化しても業務量を維持できるか確認"
    })

    # 駐車
    kpis.append({
        "name": "駐車・停車",
        "target": "訪問先でスムーズに停車できる",
        "why": "二輪化による駐車面のメリットを確認"
    })

    # スタッフ評価
    kpis.append({
        "name": "スタッフ評価",
        "target": "5段階で平均3.5以上",
        "why": "現場スタッフが継続利用できるか確認"
    })

    # 運用
    kpis.append({
        "name": "運用トラブル",
        "target": "業務を止める重大トラブル0件",
        "why": "実際の業務で継続利用できるか確認"
    })

    return kpis


# =========================
# コスト・時間シミュレーション
# =========================

def simulate(
    distance,
    work_days,
    fuel_efficiency,
    gas_price,
    car_time,
    charge_cost,
    bike_time,
    labor_cost,
    vehicle
):

    monthly_distance = distance * work_days

    car_fuel = monthly_distance / fuel_efficiency

    car_cost = car_fuel * gas_price

    charge_count = math.ceil(
        monthly_distance / vehicle["range_km"]
    )

    bike_cost = charge_count * charge_cost

    monthly_cost_difference = car_cost - bike_cost

    annual_cost_difference = (
        monthly_cost_difference * 12
    )

    daily_time_difference = (
        car_time - bike_time
    )

    monthly_time_difference = (
        daily_time_difference * work_days
    )

    annual_time_difference_hours = (
        monthly_time_difference * 12 / 60
    )

    annual_time_value = (
        annual_time_difference_hours *
        labor_cost
    )

    annual_total_effect = (
        annual_cost_difference +
        annual_time_value
    )

    if annual_total_effect > 0 and vehicle["price_yen"] is not None:

        payback_years = (
            vehicle["price_yen"] /
            annual_total_effect
        )

    else:

        payback_years = None

    return {
        "monthly_distance": monthly_distance,
        "car_fuel": car_fuel,
        "car_cost": car_cost,
        "charge_count": charge_count,
        "bike_cost": bike_cost,
        "monthly_cost_difference": monthly_cost_difference,
        "annual_cost_difference": annual_cost_difference,
        "daily_time_difference": daily_time_difference,
        "annual_time_difference_hours": annual_time_difference_hours,
        "annual_time_value": annual_time_value,
        "annual_total_effect": annual_total_effect,
        "payback_years": payback_years
    }


# =========================
# HTML
# =========================

HTML = """

<!DOCTYPE html>

<html lang="ja">

<head>

<meta charset="UTF-8">

<title>二輪×AI 導入診断</title>

<style>
* {
    box-sizing: border-box;
}

body {
    font-family: -apple-system, BlinkMacSystemFont, "Helvetica Neue", Arial, sans-serif;
    background:
        radial-gradient(circle at top right, rgba(80, 120, 255, 0.12), transparent 35%),
        linear-gradient(180deg, #f7f9fc 0%, #eef2f7 100%);
    color: #151922;
    margin: 0;
    padding: 32px 20px 60px;
}

.container {
    max-width: 1000px;
    margin: auto;
}

.hero {
    position: relative;
    overflow: hidden;
    background: linear-gradient(135deg, #111827 0%, #252d3d 55%, #3b465c 100%);
    color: white;
    padding: 55px 50px;
    margin-bottom: 24px;
    border-radius: 24px;
    box-shadow: 0 18px 45px rgba(17, 24, 39, 0.20);
}

.hero::after {
    content: "AI";
    position: absolute;
    right: 35px;
    bottom: -45px;
    font-size: 180px;
    font-weight: 900;
    color: rgba(255,255,255,0.04);
    line-height: 1;
}

.hero-label {
    font-size: 12px;
    font-weight: 800;
    letter-spacing: 3px;
    opacity: 0.65;
    margin-bottom: 16px;
}

.hero h1 {
    position: relative;
    z-index: 1;
    font-size: 46px;
    margin: 0 0 22px;
    letter-spacing: -2px;
}

.hero-title {
    position: relative;
    z-index: 1;
    font-size: 30px;
    font-weight: 700;
    line-height: 1.4;
    margin: 0 0 18px;
}

.hero-description {
    position: relative;
    z-index: 1;
    color: rgba(255,255,255,0.72);
    font-size: 15px;
    line-height: 1.8;
    margin: 0 0 25px;
}

.hero-badge {
    position: relative;
    z-index: 1;
    display: inline-block;
    padding: 8px 13px;
    border: 1px solid rgba(255,255,255,0.2);
    border-radius: 999px;
    font-size: 11px;
    letter-spacing: 1.5px;
    color: rgba(255,255,255,0.65);
}


h1 {
    font-size: 38px;
    letter-spacing: -1px;
    margin: 10px 0 8px;
}

h2 {
    margin-top: 0;
    font-size: 22px;
}

h3 {
    margin-top: 0;
}

.container > p {
    color: #667085;
    margin-top: 0;
    margin-bottom: 28px;
}

.card {
    background: rgba(255, 255, 255, 0.92);
    padding: 28px;
    margin-bottom: 22px;
    border-radius: 20px;
    border: 1px solid rgba(20, 30, 50, 0.06);
    box-shadow: 0 10px 30px rgba(20, 30, 50, 0.07);
}

label {
    display: block;
    font-weight: 600;
    margin-top: 12px;
    margin-bottom: 6px;
}

input,
select {
    width: 100%;
    padding: 13px 14px;
    margin-bottom: 14px;
    border: 1px solid #d8dee9;
    border-radius: 10px;
    background: #fff;
    font-size: 15px;
    color: #151922;
    outline: none;
    transition: 0.2s;
}

input:focus,
select:focus {
    border-color: #5b6cff;
    box-shadow: 0 0 0 3px rgba(91, 108, 255, 0.12);
}

button {
    width: 100%;
    padding: 16px;
    margin-top: 8px;
    font-size: 17px;
    font-weight: 700;
    background: linear-gradient(135deg, #111827, #30384a);
    color: white;
    border: none;
    border-radius: 12px;
    cursor: pointer;
    box-shadow: 0 8px 20px rgba(17, 24, 39, 0.18);
    transition: 0.2s;
}

button:hover {
    transform: translateY(-1px);
    box-shadow: 0 10px 24px rgba(17, 24, 39, 0.24);
}

.ai {
    background: linear-gradient(135deg, #eef4ff, #f7f9ff);
    border: 1px solid #dbe5ff;
    border-left: 5px solid #536dfe;
    padding: 24px;
    border-radius: 16px;
    line-height: 1.8;
}

.judgment {
    font-size: 26px;
    font-weight: 800;
    padding: 24px;
    border-radius: 16px;
    background: linear-gradient(135deg, #effcf4, #f7fffa);
    border: 1px solid #d7f0df;
}

.effect {
    background: linear-gradient(135deg, #f5f5ff, #fafaff);
    border: 1px solid #e4e3ff;
    border-left: 5px solid #6c63ff;
    padding: 24px;
    border-radius: 16px;
}

.kpi {
    background: #fff;
    border: 1px solid #e3e7ee;
    padding: 18px;
    margin-top: 12px;
    border-radius: 12px;
}

.pilot {
    background: linear-gradient(135deg, #fff9ed, #fffdf8);
    border: 1px solid #f5dfb4;
    border-left: 5px solid #f39c12;
    padding: 24px;
    border-radius: 16px;
}

.vehicle {
    background: #fff;
    border: 1px solid #e3e7ee;
    padding: 22px;
    margin-top: 15px;
    border-radius: 16px;
    transition: 0.2s;
}

.vehicle:hover {
    transform: translateY(-2px);
    box-shadow: 0 8px 24px rgba(20, 30, 50, 0.08);
}

.big-number {
    font-size: 32px;
    font-weight: 800;
    letter-spacing: -1px;
}

.small {
    color: #667085;
    font-size: 14px;
}

hr {
    border: 0;
    border-top: 1px solid #e8ebf0;
    margin: 28px 0;
}

@media (max-width: 600px) {
    body {
        padding: 20px 12px 40px;
    }

    h1 {
        font-size: 29px;
    }

    .card {
        padding: 20px;
        border-radius: 16px;
    }
}

.result-main {
    padding: 32px;
}

.result-label {
    font-size: 11px;
    font-weight: 800;
    letter-spacing: 2.5px;
    color: #536dfe;
    margin-bottom: 8px;
}

.result-main h2 {
    font-size: 28px;
    margin-bottom: 20px;
}

.result-explanation {
    font-size: 15px;
    line-height: 1.8;
    color: #475467;
    margin-bottom: 0;
}


.effect-card {
    padding: 32px;
}

.effect-subtitle {
    color: #667085;
    font-size: 14px;
    margin-top: -8px;
    margin-bottom: 28px;
}

.impact-grid {
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 14px;
    margin-bottom: 28px;
}

.impact-item {
    background: #f7f8fc;
    border: 1px solid #e5e8f0;
    border-radius: 16px;
    padding: 24px 16px;
    text-align: center;
}

.impact-number {
    font-size: 32px;
    font-weight: 800;
    letter-spacing: -1px;
    color: #111827;
}

.impact-number span {
    font-size: 15px;
    font-weight: 700;
    margin-left: 3px;
}

.impact-label {
    margin-top: 8px;
    font-size: 12px;
    color: #667085;
    line-height: 1.5;
}

.effect-detail {
    display: grid;
    grid-template-columns: 1fr auto 1fr;
    align-items: center;
    gap: 14px;
}

.effect-detail-box {
    padding: 20px;
    border: 1px solid #e5e8f0;
    border-radius: 14px;
}

.effect-detail-box h3 {
    margin-top: 0;
    font-size: 15px;
}

.effect-detail-box p {
    margin: 8px 0;
    font-size: 13px;
    color: #667085;
}

.effect-detail-box strong {
    color: #111827;
}

.effect-arrow {
    font-size: 22px;
    font-weight: 700;
    color: #98a2b3;
}

.annual-effect {
    margin-top: 18px;
    padding: 18px 20px;
    background: #111827;
    color: white;
    border-radius: 14px;
    display: flex;
    justify-content: space-between;
    align-items: center;
}

.annual-effect span {
    font-size: 13px;
    font-weight: 600;
}

.annual-effect strong {
    font-size: 24px;
}

@media (max-width: 700px) {
    .impact-grid {
        grid-template-columns: 1fr;
    }

    .effect-detail {
        grid-template-columns: 1fr;
    }

    .effect-arrow {
        display: none;
    }
}

</style>

</head>


<body>

<div class="container">

<div class="hero">
    <div class="hero-label">MOBILITY × AI</div>
    <h1>二輪導入AI</h1>
    <p class="hero-title">その業務に、<br>電動二輪という選択肢を。</p>
    <p class="hero-description">
        業務データを入力するだけで、<br>
        電動二輪の導入可能性・期待効果・リスクを分析します。
    </p>
    <div class="hero-badge">AI BUSINESS DIAGNOSIS</div>
</div>

<div class="card">

<div class="section-heading">
    <div class="step-label">STEP 01</div>
    <h2>業務条件</h2>
    <p>現在の業務について教えてください。<br>入力されたデータをもとに、二輪導入の可能性を分析します。</p>
</div>

<form method="POST">

<label>業種</label>

<select name="business">

{% for b in businesses %}

<option value="{{ b }}">

{{ b }}

</option>

{% endfor %}

</select>


<label>1日の移動距離（km）</label>

<input
type="number"
step="0.1"
name="distance"
required
>


<label>1日の訪問件数</label>

<input
type="number"
name="visits"
required
>


<label>現在の移動手段</label>

<select name="current_vehicle">

<option value="車">車</option>
<option value="バイク">バイク</option>
<option value="自転車">自転車</option>
<option value="公共交通">公共交通</option>

</select>


<label>荷物の量</label>

<select name="luggage">

<option value="少ない">少ない</option>
<option value="普通">普通</option>
<option value="多い">多い</option>

</select>


<div class="section-heading step-two">
    <div class="step-label">STEP 02</div>
    <h2>ルート・運用条件</h2>
    <p>実際の走行・運用環境について教えてください。</p>
</div>


<label>坂道の多さ</label>

<select name="slope">

<option value="少ない">少ない</option>
<option value="普通">普通</option>
<option value="多い">多い</option>

</select>


<label>駐車環境</label>

<select name="parking">

<option value="しやすい">しやすい</option>
<option value="普通">普通</option>
<option value="難しい">難しい</option>

</select>


<label>充電環境</label>

<select name="charging">

<option value="既に利用可能">既に利用可能</option>

<option value="導入時に用意可能">導入時に用意可能</option>

<option value="用意が難しい">用意が難しい</option>

<option value="要確認">要確認</option>

</select>


<h2>③ コスト・時間</h2>


<label>月の稼働日数</label>

<input
type="number"
name="work_days"
value="20"
required
>


<label>自動車の燃費（km/L）</label>

<input
type="number"
step="0.1"
name="fuel_efficiency"
value="15"
required
>


<label>ガソリン価格（円/L）</label>

<input
type="number"
name="gas_price"
value="180"
required
>


<label>1日の自動車移動時間（分）</label>

<input
type="number"
name="car_time"
value="60"
required
>


<label>1回の充電電気代（円）</label>

<input
type="number"
name="charge_cost"
value="10"
required
>


<label>二輪での1日の移動時間（分）</label>

<input
type="number"
name="bike_time"
value="40"
required
>


<label>1時間あたりの人件費（円）</label>

<input
type="number"
name="labor_cost"
value="2000"
required
>


<h2>④ 福利厚生シミュレーション</h2>

<label>対象社員数</label>

<input

type="number"

name="employees"

value="10"

min="1"

required

>


<label>1人あたりの会社補助（月額・円）</label>

<input

type="number"

name="subsidy_per_employee"

value="5000"

min="0"

required

>


<label>福利厚生としての利用日数（月）</label>

<input

type="number"

name="welfare_work_days"

value="20"

min="1"

required

>


<div class="diagnosis-info">
    <div class="diagnosis-info-title">AI ANALYSIS</div>
    <div class="diagnosis-info-text">
        業務条件・ルート条件・車両データを分析し、<br>
        導入可能性と期待できる効果を整理します。
    </div>
</div>

<button type="submit">

AI診断を実行する →

</button>

</form>

</div>


{% if results %}
<!-- =========================
     PDF提案書
========================= -->

<div class="card">

<h2>📄 提案書</h2>

<p>
今回の診断結果をPDF形式の提案書として出力できます。
</p>

<form method="POST" action="/download_pdf">

<input type="hidden" name="business" value="{{ data.business }}">

<input type="hidden" name="distance" value="{{ data.distance }}">

<input type="hidden" name="visits" value="{{ data.visits }}">

<input type="hidden" name="current_vehicle" value="{{ data.current_vehicle }}">

<input type="hidden" name="luggage" value="{{ data.luggage }}">

<input type="hidden" name="slope" value="{{ data.slope }}">

<input type="hidden" name="parking" value="{{ data.parking }}">

<input type="hidden" name="charging" value="{{ data.charging }}">

<input type="hidden" name="work_days" value="{{ data.work_days }}">

<input type="hidden" name="fuel_efficiency" value="{{ data.fuel_efficiency }}">

<input type="hidden" name="gas_price" value="{{ data.gas_price }}">

<input type="hidden" name="car_time" value="{{ data.car_time }}">

<input type="hidden" name="charge_cost" value="{{ data.charge_cost }}">

<input type="hidden" name="bike_time" value="{{ data.bike_time }}">

<input type="hidden" name="labor_cost" value="{{ data.labor_cost }}">

<button type="submit">
📄 PDF提案書を作成
</button>

</form>

</div>

<!-- =========================
     導入判定
========================= -->

<div class="card result-main">

<div class="result-label">AI DIAGNOSIS</div>

<h2>導入可能性</h2>

<div class="judgment">

{{ judgment.status }}

</div>

<p class="result-explanation">

{{ judgment.explanation }}

</p>

</div>


<!-- =========================
     AIコメント
========================= -->

<div class="card">

<h2>💡 AI診断コメント</h2>

<div class="ai">

{{ comment }}

</div>

</div>


<!-- =========================
     導入効果
========================= -->

<div class="card">

<h2>📊 導入効果</h2>

<div class="effect">

<h3>🚗 現在の移動</h3>

<p>

1日の移動時間：

<strong>

{{ car_time }}

分

</strong>

</p>

<p>

月間燃料費：

<strong>

{{ "{:,.0f}".format(results[0].sim.car_cost) }}

円

</strong>

</p>


<hr>


<h3>🛵 電動二輪導入後</h3>

<p>

1日の移動時間：

<strong>

{{ bike_time }}

分

</strong>

</p>

<p>

月間充電費：

<strong>

{{ "{:,.0f}".format(results[0].sim.bike_cost) }}

円

</strong>

</p>


<hr>


<h3>💡 期待できる変化</h3>

<p>

1日あたり移動時間：

<span class="big-number">

{{ "{:.0f}".format(results[0].sim.daily_time_difference) }}

分

</span>

短縮

</p>

<p>

年間移動時間：

<span class="big-number">

{{ "{:.1f}".format(results[0].sim.annual_time_difference_hours) }}

時間

</span>

削減

</p>

<p>

年間コスト差：

<strong>

{{ "{:,.0f}".format(results[0].sim.annual_cost_difference) }}

円

</strong>

</p>

<p>

年間合計効果：

<span class="big-number">

{{ "{:,.0f}".format(results[0].sim.annual_total_effect) }}

円

</span>

</p>

</div>

<p class="small">

※時間価値を含む参考シミュレーションです。
実際の人件費削減額とは異なります。

</p>

</div>


<!-- =========================
     福利厚生シミュレーション
========================= -->

<div class="card">

<h2>🏢 福利厚生シミュレーション</h2>

<p>
電動二輪を福利厚生として導入した場合、
会社の負担額と社員の移動時間への効果を試算します。
</p>

<div class="effect">

<h3>👥 対象社員</h3>

<p>
対象社員数：
<strong>
{{ welfare.employees }}人
</strong>
</p>

<p>
福利厚生利用日数：
<strong>
{{ welfare.work_days }}日 / 月
</strong>
</p>

<hr>

<h3>💰 会社側の負担</h3>

<p>
1人あたり会社補助：
<strong>
{{ "{:,.0f}".format(welfare.subsidy_per_employee) }}円 / 月
</strong>
</p>

<p>
月間会社負担：
<span class="big-number">
{{ "{:,.0f}".format(welfare.monthly_company_cost) }}
円
</span>
</p>

<p>
年間会社負担：
<span class="big-number">
{{ "{:,.0f}".format(welfare.annual_company_cost) }}
円
</span>
</p>

<hr>

<h3>⏱️ 社員の移動時間への効果</h3>

<p>
1日あたり：
<strong>
{{ "{:.0f}".format(welfare.time_saved_per_day) }}分
</strong>
短縮
</p>

<p>
1人あたり年間：
<span class="big-number">
{{ "{:.1f}".format(welfare.annual_time_saved_per_employee) }}
時間
</span>
削減
</p>

<p>
対象社員全体：
<span class="big-number">
{{ "{:.1f}".format(welfare.annual_time_saved_all) }}
時間
</span>
削減
</p>

</div>

<p class="small">
※会社補助額と移動時間をもとにした参考シミュレーションです。
</p>

</div>


<!-- =========================
     KPI
========================= -->

<div class="card">

<h2>🎯 実証実験の成功KPI</h2>

<p>

AIが導入仮説だけでなく、

<strong>

「何を達成したら導入を検討できるか」

</strong>

まで設定します。

</p>


{% for kpi in kpis %}

<div class="kpi">

<h3>

{{ loop.index }}. {{ kpi.name }}

</h3>

<p>

<strong>目標：</strong>

{{ kpi.target }}

</p>

<p class="small">

{{ kpi.why }}

</p>

</div>

{% endfor %}

</div>


<!-- =========================
     実証実験
========================= -->

<div class="card">

<h2>🚀 実証実験プラン</h2>

<div class="pilot">

<h3>対象</h3>

<p>

{{ pilot.staff }}

</p>


<h3>期間</h3>

<p>

{{ pilot.period }}

</p>


<h3>比較方法</h3>

<p>

{{ pilot.comparison }}

</p>


<h3>記録するデータ</h3>

<ul>

{% for item in pilot.records %}

<li>

{{ item }}

</li>

{% endfor %}

</ul>


{% if pilot.checks %}

<h3>重点確認ポイント</h3>

<ul>

{% for item in pilot.checks %}

<li>

{{ item }}

</li>

{% endfor %}

</ul>

{% endif %}

</div>

</div>


<!-- =========================
     車両比較
========================= -->

<div class="card">

<h2>🚲 車両比較</h2>


{% for r in results %}

<div class="vehicle">

<h3>

{{ loop.index }}位：{{ r.vehicle.name }}

</h3>


<p>

<strong>

条件一致度：

</strong>

{{ r.score }}点

</p>


<p>

航続距離：

{{ r.vehicle.range_km }}km

<br>

重量：

{{ r.vehicle.weight_kg }}kg

<br>

価格：

{{ "{:,}".format(r.vehicle.price_yen) if r.vehicle.price_yen is not none else "要確認" }}

<br>

充電時間：

{{ r.vehicle.charge_time }}

<br>

最大積載：

{% if r.vehicle.max_load_kg %}

{{ r.vehicle.max_load_kg }}kg

{% else %}

要確認

{% endif %}

<br>

免許：

{% if r.vehicle.license_required %}

必要

{% else %}

不要

{% endif %}

</p>


<h4>適合理由</h4>

<ul>

{% for reason in r.reasons %}

<li>

{{ reason }}

</li>

{% endfor %}

</ul>


{% if r.cautions %}

<h4>確認ポイント</h4>

<ul>

{% for caution in r.cautions %}

<li>

{{ caution }}

</li>

{% endfor %}

</ul>

{% endif %}

</div>

{% endfor %}

</div>


<!-- =========================
     コスト
========================= -->

<div class="card">

<h2>💰 コスト・時間シミュレーション</h2>


{% for r in results %}

<h3>

{{ r.vehicle.name }}

</h3>

<p>

月間移動距離：

{{ "{:.0f}".format(r.sim.monthly_distance) }}

km

<br>

自動車の月間燃料費：

{{ "{:,.0f}".format(r.sim.car_cost) }}

円

<br>

二輪の月間充電費：

{{ "{:,.0f}".format(r.sim.bike_cost) }}

円

<br>

月間コスト差：

{{ "{:,.0f}".format(r.sim.monthly_cost_difference) }}

円

<br>

年間時間削減：

{{ "{:.1f}".format(r.sim.annual_time_difference_hours) }}

時間

<br>

年間時間価値：

{{ "{:,.0f}".format(r.sim.annual_time_value) }}

円

<br>

年間合計効果：

{{ "{:,.0f}".format(r.sim.annual_total_effect) }}

円

</p>


{% if r.sim.payback_years %}

<p>

<strong>

参考回収期間：

{{ "{:.1f}".format(r.sim.payback_years) }}

年

</strong>

</p>

{% endif %}

<hr>

{% endfor %}


<p class="small">

※条件一致度は、このプロトタイプ独自のルールによる参考値です。

<br>

※年間時間価値は「削減できた時間を人件費相当として評価した場合」の参考値です。

<br>

※回収期間は簡易シミュレーションです。
保険・税金・メンテナンス・消耗品・車両残価などは含んでいません。

<br>

※実際の導入判断は実証実験による確認を前提とします。

</p>

</div>


{% endif %}

</div>

</body>

</html>

"""


# =========================
# Flask
# =========================

@app.route("/", methods=["GET", "POST"])
def index():
    results = None
    comment = None
    judgment = None
    pilot = None
    kpis = None
    data = None

    if request.method == "POST":

        business = request.form["business"]

        distance = float(
            request.form["distance"]
        )

        visits = int(
            request.form["visits"]
        )

        current_vehicle = request.form[
            "current_vehicle"
        ]

        luggage = request.form[
            "luggage"
        ]

        slope = request.form[
            "slope"
        ]

        parking = request.form[
            "parking"
        ]

        charging = request.form[
            "charging"
        ]

        work_days = int(
            request.form["work_days"]
        )

        fuel_efficiency = float(
            request.form["fuel_efficiency"]
        )

        gas_price = float(
            request.form["gas_price"]
        )

        car_time = float(
            request.form["car_time"]
        )

        charge_cost = float(
            request.form["charge_cost"]
        )

        bike_time = float(
            request.form["bike_time"]
        )

        labor_cost = float(
            request.form["labor_cost"]
        )

        employees = int(
            request.form["employees"]
        )

        subsidy_per_employee = float(
            request.form["subsidy_per_employee"]
        )

        welfare_work_days = int(
            request.form["welfare_work_days"]
        )


        data = {
            "business": business,
            "distance": distance,
            "visits": visits,
            "current_vehicle": current_vehicle,
            "luggage": luggage,
            "slope": slope,
            "parking": parking,
            "charging": charging,
            "work_days": work_days,
            "fuel_efficiency": fuel_efficiency,
            "gas_price": gas_price,
            "car_time": car_time,
            "charge_cost": charge_cost,
            "bike_time": bike_time,
            "labor_cost": labor_cost,
            "employees": employees,
            "subsidy_per_employee": subsidy_per_employee,
            "welfare_work_days": welfare_work_days
        }


        # 診断
        results = diagnose(
            business,
            distance,
            visits,
            current_vehicle,
            luggage,
            slope,
            parking,
            charging
        )


        # AI診断コメント
        ai_input = build_ai_input(
            business,
            distance,
            visits,
            current_vehicle,
            luggage,
            slope,
            parking,
            charging,
            results
        )

        comment = generate_ai_comment(ai_input)


        # 導入判定
        judgment = make_adoption_judgment(
            distance,
            visits,
            luggage,
            slope,
            parking,
            charging,
            results
        )


        # 実証実験
        pilot = make_pilot_plan(
            business,
            visits,
            current_vehicle,
            luggage,
            slope,
            parking,
            charging
        )


        # KPI
        kpis = make_kpis(
            car_time,
            bike_time,
            visits
        )


        # 福利厚生シミュレーション
        welfare = simulate_welfare(
            employees,
            welfare_work_days,
            subsidy_per_employee,
            car_time,
            bike_time
        )

        # 車両ごとのシミュレーション
        for r in results:

            r["sim"] = simulate(
                distance,
                work_days,
                fuel_efficiency,
                gas_price,
                car_time,
                charge_cost,
                bike_time,
                labor_cost,
                r["vehicle"]
            )


    return render_template_string(
        HTML,
        businesses=list(BUSINESS_RULES.keys()),
        results=results,
        comment=comment,
        judgment=judgment,
        pilot=pilot,
        kpis=kpis,
        welfare=welfare if data else None,
        data=data,
        car_time=car_time if data else "",
        bike_time=bike_time if data else ""
    )



# =========================
# PDFダウンロード
# =========================

@app.route("/download_pdf", methods=["POST"])
def download_pdf():

    business = request.form["business"]
    distance = float(request.form["distance"])
    visits = int(request.form["visits"])
    current_vehicle = request.form["current_vehicle"]
    luggage = request.form["luggage"]

    slope = request.form["slope"]
    parking = request.form["parking"]
    charging = request.form["charging"]

    work_days = int(request.form["work_days"])
    fuel_efficiency = float(request.form["fuel_efficiency"])
    gas_price = float(request.form["gas_price"])
    car_time = float(request.form["car_time"])
    charge_cost = float(request.form["charge_cost"])
    bike_time = float(request.form["bike_time"])
    labor_cost = float(request.form["labor_cost"])

    score_results = diagnose(
        business,
        distance,
        visits,
        current_vehicle,
        luggage,
        slope,
        parking,
        charging
    )

    results = []

    for r in score_results:

        v = r["vehicle"]

        monthly_distance = distance * work_days

        car_fuel = monthly_distance / fuel_efficiency
        car_cost = car_fuel * gas_price

        bike_charges = math.ceil(monthly_distance / v["range_km"])
        bike_cost = bike_charges * charge_cost

        monthly_cost_difference = car_cost - bike_cost

        annual_cost_difference = monthly_cost_difference * 12

        daily_time_difference = car_time - bike_time

        annual_time_difference_hours = (
            daily_time_difference * work_days * 12
        ) / 60

        annual_time_value = (
            annual_time_difference_hours * labor_cost
        )

        annual_effect = (
            annual_cost_difference + annual_time_value
        )

        payback_years = (
            v["price_yen"] / annual_effect
            if annual_effect > 0
            else None
        )

        results.append({
            "vehicle": v,
            "score": r["score"],
            "reasons": r["reasons"],
            "cautions": r["cautions"],
            "monthly_cost_difference": monthly_cost_difference,
            "annual_time_difference_hours": annual_time_difference_hours,
            "annual_effect": annual_effect,
            "payback_years": payback_years,
            "sim": {
                "monthly_distance": monthly_distance,
                "annual_time_difference_hours": annual_time_difference_hours,
                "annual_cost_difference": annual_cost_difference,
                "annual_total_effect": annual_effect,
                "payback_years": payback_years
            }
        })

    judgment = make_adoption_judgment(
        distance,
        visits,
        luggage,
        slope,
        parking,
        charging,
        results
    )
    pilot = make_pilot_plan(
        business,
        visits,
        current_vehicle,
        luggage,
        slope,
        parking,
        charging
    )
    kpis = make_kpis(car_time, bike_time, visits)

    pdf_path = create_pdf(
        business,
        distance,
        visits,
        current_vehicle,
        luggage,
        slope,
        parking,
        charging,
        results,
        judgment,
        pilot,
        kpis
    )

    return send_file(
        pdf_path,
        as_attachment=True,
        download_name="二輪導入提案書.pdf"
    )


if __name__ == "__main__":

    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5001)), debug=False)

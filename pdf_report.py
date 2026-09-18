from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.lib.units import mm

import os


# 日本語フォント
pdfmetrics.registerFont(
    UnicodeCIDFont("HeiseiKakuGo-W5")
)


def create_pdf(
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
):

    filename = "二輪導入診断_提案書.pdf"

    c = canvas.Canvas(
        filename,
        pagesize=A4
    )

    width, height = A4

    y = height - 25 * mm


    def text(value, size=11, gap=8):

        nonlocal y

        c.setFont(
            "HeiseiKakuGo-W5",
            size
        )

        c.drawString(
            20 * mm,
            y,
            str(value)
        )

        y -= gap * mm

        # ページ下部なら新しいページ
        if y < 20 * mm:

            c.showPage()

            c.setFont(
                "HeiseiKakuGo-W5",
                size
            )

            y = height - 20 * mm


    # =========================
    # タイトル
    # =========================

    text(
        "二輪導入診断・提案書",
        22,
        13
    )

    text(
        f"対象業務：{business}",
        14,
        10
    )

    text(
        "業務条件・車両条件・導入効果をもとにした診断結果",
        10,
        12
    )


    # =========================
    # 導入判定
    # =========================

    text(
        "1. 導入判定",
        16,
        10
    )

    text(
        judgment["status"],
        14,
        9
    )

    text(
        judgment["explanation"],
        10,
        9
    )


    # =========================
    # 業務条件
    # =========================

    text(
        "2. 現在の業務条件",
        16,
        10
    )

    text(f"業種：{business}")
    text(f"1日の移動距離：{distance}km")
    text(f"1日の訪問件数：{visits}件")
    text(f"現在の移動手段：{current_vehicle}")
    text(f"荷物：{luggage}")
    text(f"坂道：{slope}")
    text(f"駐車環境：{parking}")
    text(f"充電環境：{charging}")


    # =========================
    # 車両比較
    # =========================

    text(
        "3. 車両比較",
        16,
        10
    )

    for i, result in enumerate(results):

        vehicle = result["vehicle"]

        text(
            f"{i + 1}位：{vehicle['name']}",
            13,
            8
        )

        text(
            f"条件一致度：{result['score']}点"
        )

        text(
            f"航続距離：約{vehicle['range_km']}km"
        )

        text(
            f"車両重量：{vehicle['weight_kg']}kg"
        )

        text(
            f"価格：{vehicle['price_yen']:,}円" if vehicle["price_yen"] is not None else "価格：要確認"

        )

        text(
            f"充電時間：{vehicle['charge_time']}"
        )

        if vehicle["max_load_kg"]:

            text(
                f"最大積載重量：{vehicle['max_load_kg']}kg"
            )

        else:

            text(
                "最大積載重量：要確認"
            )

        text("")


    # =========================
    # 導入効果
    # =========================

    text(
        "4. 導入効果",
        16,
        10
    )

    top = results[0]

    sim = top["sim"]

    text(
        f"月間移動距離：{sim['monthly_distance']:.0f}km"
    )

    text(
        f"年間移動時間削減：約{sim['annual_time_difference_hours']:.1f}時間"
    )

    text(
        f"年間コスト差：約{sim['annual_cost_difference']:,.0f}円"
    )

    text(
        f"年間合計効果：約{sim['annual_total_effect']:,.0f}円"
    )

    if sim["payback_years"]:

        text(
            f"参考回収期間：約{sim['payback_years']:.1f}年"
        )


    # =========================
    # KPI
    # =========================

    text(
        "5. 実証実験の成功KPI",
        16,
        10
    )

    for kpi in kpis:

        text(
            f"{kpi['name']}：{kpi['target']}",
            10,
            8
        )


    # =========================
    # 実証実験プラン
    # =========================

    text(
        "6. 実証実験プラン",
        16,
        10
    )

    text(
        f"対象：{pilot['staff']}"
    )

    text(
        f"期間：{pilot['period']}"
    )

    text(
        f"比較：{pilot['comparison']}"
    )

    text("記録項目：")

    for item in pilot["records"]:

        text(
            f"・{item}",
            10,
            7
        )


    # =========================
    # 注意事項
    # =========================

    text(
        "7. 注意事項",
        16,
        10
    )

    text(
        "・条件一致度はプロトタイプ独自の参考値です。",
        9,
        7
    )

    text(
        "・実際の導入判断は実証実験を前提とします。",
        9,
        7
    )

    text(
        "・回収期間は簡易シミュレーションです。",
        9,
        7
    )

    text(
        "・保険、税金、メンテナンス等は含まれていません。",
        9,
        7
    )


    c.save()

    return filename

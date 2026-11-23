"""產生「公式驗證.xlsx」：用 Excel 公式從原始資料重算每個指標，旁邊放 Python 的結果，逐格標 ✔ / ✘。

先執行 python verify_formulas.py 甲班 --dump（存下同一份資料快照），再執行：
    python build_verify_excel.py 甲班
"""
from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from openpyxl import Workbook
from openpyxl.comments import Comment
from openpyxl.formatting.rule import CellIsRule
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

TW = timezone(timedelta(hours=8))
F = "Arial"
HEAD = PatternFill("solid", fgColor="1F3A5F")
PYFILL = PatternFill("solid", fgColor="EEF3FA")
thin = Side(style="thin", color="D0D7E2")
BORDER = Border(bottom=thin)
TOL = "0.0501"  # Python 顯示到小數 1 位；Excel 是未四捨五入的值，最多差 0.05


def rnd(pid: str) -> str:
    s = (pid or "").strip().upper()
    m = re.match(r"^TEST(\d+)-", s)
    return f"TEST{int(m.group(1))}" if m else ("TEST1" if s.startswith("TEST") else "FORMAL")


def ts(v: str) -> datetime:
    return datetime.fromisoformat(v.replace("Z", "+00:00")).astimezone(TW).replace(tzinfo=None)


def header(ws, row, cols, widths=None):
    for i, c in enumerate(cols, 1):
        cell = ws.cell(row=row, column=i, value=c)
        cell.font = Font(name=F, bold=True, color="FFFFFF", size=10)
        cell.fill = HEAD
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    ws.row_dimensions[row].height = 34
    for i, w in enumerate(widths or [], 1):
        ws.column_dimensions[get_column_letter(i)].width = w
    ws.freeze_panes = f"A{row + 1}"  # 用字串設定，避免多建立一列空白


def style_rows(ws, r0, r1, ncol, py_cols=(), fmts=None):
    for r in range(r0, r1 + 1):
        for c in range(1, ncol + 1):
            cell = ws.cell(row=r, column=c)
            cell.font = Font(name=F, size=10, color="0000FF" if c in py_cols else "000000")
            cell.border = BORDER
            if c in py_cols:
                cell.fill = PYFILL
            if fmts and c in fmts:
                cell.number_format = fmts[c]


def check_fmt(ws, rng):
    ws.conditional_formatting.add(rng, CellIsRule(operator="equal", formula=['"✔"'], font=Font(name=F, color="0A7A3E", bold=True)))
    ws.conditional_formatting.add(rng, CellIsRule(operator="equal", formula=['"✘"'], font=Font(name=F, color="C62828", bold=True),
                                                  fill=PatternFill("solid", fgColor="FDECEA")))


def main(db: str) -> None:
    src = Path(__file__).resolve().parent.parent / "verify" / db
    events = json.loads((src / "events.json").read_text(encoding="utf-8"))
    flows = json.loads((src / "flows.json").read_text(encoding="utf-8"))
    py = json.loads((src / "python_result.json").read_text(encoding="utf-8"))
    lines = {f"{l['group_id']}|{l['batch']}": l for l in py["lines"]}

    done = [e for e in events if (e.get("status") or "COMPLETED") == "COMPLETED"]
    skipped = len(events) - len(done)
    done.sort(key=lambda e: (e["group_id"].strip(), rnd(e["product_id"]), e["station_id"].strip(), e["start_time"]))

    wb = Workbook()
    info = wb.active
    info.title = "說明"

    # ------------------------------------------------ 原始資料（每一列一筆完工紀錄）
    ws = wb.create_sheet("原始資料")
    cols = ["組別", "產品編號", "工站", "開工時間", "完工時間", "作業秒數", "狀態",
            "場次（公式）", "產線鍵", "工站鍵", "產線首件開工", "同站前一件完工", "空檔秒數", "計入等待"]
    header(ws, 1, cols, [7, 12, 7, 20, 20, 9, 11, 11, 13, 17, 20, 20, 10, 9])
    for i, e in enumerate(done, start=2):
        ws.append([e["group_id"].strip(), e["product_id"], e["station_id"].strip(), ts(e["start_time"]), ts(e["finish_time"]),
                   float(e["duration_sec"] or 0), e["status"],
                   # 場次：TEST2-P01 → TEST2；舊版 TEST-P01 → TEST1；沒有 TEST → FORMAL（同老師 getTestRoundFromProductId）
                   f'=IF(LEFT(UPPER(B{i}),4)<>"TEST","FORMAL",IF(MID(B{i},5,1)="-","TEST1","TEST"&LEFT(MID(B{i},5,10),FIND("-",MID(B{i},5,10))-1)))',
                   f'=A{i}&"|"&H{i}',
                   f'=I{i}&"|"&C{i}',
                   f"=_xlfn.MINIFS($D:$D,$I:$I,I{i})",
                   f"=IF(J{i - 1}=J{i},E{i - 1},K{i})",       # 同站第一件 → 用產線首件開工時間
                   f"=(D{i}-L{i})*86400",
                   f"=IF(AND(M{i}>0,M{i}<600),M{i},0)"])       # 0~600 秒才算等待（同老師）
    n_ev = len(done) + 1
    style_rows(ws, 2, n_ev, 14, fmts={4: "yyyy-mm-dd hh:mm:ss.000", 5: "yyyy-mm-dd hh:mm:ss.000",
                                       11: "yyyy-mm-dd hh:mm:ss.000", 12: "yyyy-mm-dd hh:mm:ss.000", 13: "0.000", 14: "0.000"})

    # ------------------------------------------------ 各工站
    st_rows = []
    for key, l in lines.items():
        for st in l["stations"]:
            st_rows.append((key, st, l["station_stats"][st]))
    w2 = wb.create_sheet("各工站")
    cols = ["產線鍵", "工站", "工站序號", "筆數", "總作業秒數", "平均 CT", "總等待秒數", "稼動率",
            "瓶頸判斷", "Python 平均 CT", "Python 總等待", "Python 稼動率", "Python 筆數", "CT", "等待", "稼動率", "筆數"]
    header(w2, 1, cols, [13, 7, 8, 7, 11, 10, 11, 9, 15, 11, 11, 11, 9, 6, 6, 7, 6])
    for i, (key, st, s) in enumerate(st_rows, start=2):
        w2.append([key, st,
                   f"=VALUE(MID(B{i},3,5))",
                   f'=COUNTIFS(原始資料!$J:$J,A{i}&"|"&B{i})',
                   f'=SUMIFS(原始資料!$F:$F,原始資料!$J:$J,A{i}&"|"&B{i})',
                   f"=E{i}/D{i}",
                   f'=SUMIFS(原始資料!$N:$N,原始資料!$J:$J,A{i}&"|"&B{i})',
                   f"=IF(E{i}+G{i}>0,E{i}/(E{i}+G{i}),0)",
                   # 這條線平均 CT 最大、且是同分中第一個（工站編號最小）→ 標 "產線鍵|1"
                   f'=A{i}&"|"&IF(F{i}=_xlfn.MAXIFS($F:$F,$A:$A,A{i}),COUNTIFS($A$2:A{i},A{i},$F$2:F{i},F{i}),0)',
                   s["avg_ct"], s["wait_sec"], s["util_pct"] / 100, s["qty"],
                   f'=IF(ABS(F{i}-J{i})<={TOL},"✔","✘")',
                   f'=IF(ABS(G{i}-K{i})<={TOL},"✔","✘")',
                   f'=IF(ABS(H{i}-L{i})<=0.000501,"✔","✘")',
                   f'=IF(D{i}=M{i},"✔","✘")'])
    n_st = len(st_rows) + 1
    style_rows(w2, 2, n_st, 17, py_cols=(10, 11, 12, 13), fmts={5: "0.0", 6: "0.000", 7: "0.000", 8: "0.0%", 10: "0.0", 11: "0.0", 12: "0.0%"})
    check_fmt(w2, f"N2:Q{n_st}")

    # ------------------------------------------------ 各場次
    w3 = wb.create_sheet("各場次")
    cols = ["產線鍵", "組別", "場次", "流程（station_flow）", "終點站（依流程）", "產出站", "總耗時（秒）", "產出組數",
            "節拍時間（秒/組）", "瓶頸 CT", "瓶頸站", "平衡率", "等待合計（秒）",
            "Python 總耗時", "Python 產出組數", "Python 節拍", "Python 瓶頸站", "Python 瓶頸 CT", "Python 平衡率", "Python 等待合計",
            "總耗時", "產出", "節拍", "瓶頸站", "瓶頸CT", "平衡率", "等待"]
    header(w3, 1, cols, [13, 6, 8, 26, 10, 8, 11, 8, 11, 9, 8, 8, 11, 11, 9, 10, 9, 9, 9, 11, 7, 6, 6, 7, 7, 7, 6])
    for i, (key, l) in enumerate(lines.items(), start=2):
        w3.append([key, l["group_id"], l["batch"], "、".join(l["flow"]) or "（未設定）", l["final_station"],
                   # 終點站有完工紀錄 → 用終點站；沒有 → 用有資料的最後一站試算（同老師）
                   f'=IF(COUNTIFS(原始資料!$J:$J,A{i}&"|"&E{i})>0,E{i},"ST"&TEXT(_xlfn.MAXIFS(各工站!$C:$C,各工站!$A:$A,A{i}),"00"))',
                   f"=(_xlfn.MAXIFS(原始資料!$E:$E,原始資料!$I:$I,A{i})-_xlfn.MINIFS(原始資料!$D:$D,原始資料!$I:$I,A{i}))*86400",
                   f'=COUNTIFS(原始資料!$J:$J,A{i}&"|"&F{i})',
                   f'=IF(AND(H{i}>0,G{i}>0),G{i}/H{i},"")',
                   f"=_xlfn.MAXIFS(各工站!$F:$F,各工站!$A:$A,A{i})",
                   f'=INDEX(各工站!$B:$B,MATCH(A{i}&"|1",各工站!$I:$I,0))',
                   f"=SUMIFS(各工站!$F:$F,各工站!$A:$A,A{i})/(COUNTIFS(各工站!$A:$A,A{i})*J{i})",
                   f"=SUMIFS(原始資料!$N:$N,原始資料!$I:$I,A{i})",
                   l["total_sec"], l["output_sets"], l["takt_sec"], l["bottleneck"], l["bottleneck_ct"],
                   l["balance_pct"] / 100, l["wait_sec"],
                   f'=IF(ABS(G{i}-N{i})<={TOL},"✔","✘")',
                   f'=IF(H{i}=O{i},"✔","✘")',
                   f'=IF(OR(I{i}="",P{i}=""),IF(AND(I{i}="",P{i}=""),"✔","✘"),IF(ABS(I{i}-P{i})<={TOL},"✔","✘"))',
                   f'=IF(K{i}=Q{i},"✔","✘")',
                   f'=IF(ABS(J{i}-R{i})<={TOL},"✔","✘")',
                   f'=IF(ABS(L{i}-S{i})<=0.000501,"✔","✘")',
                   f'=IF(ABS(M{i}-T{i})<={TOL},"✔","✘")'])
        if l["long_span"]:
            w3.cell(row=i, column=7).comment = Comment("這一場的資料跨越超過 3 小時，可能混了不同天的上課紀錄；公式本身沒問題。", "驗證")
    n_ln = len(lines) + 1
    for r in range(2, n_ln + 1):
        w3.cell(row=r, column=4).alignment = Alignment(wrap_text=True, vertical="top")
    style_rows(w3, 2, n_ln, 27, py_cols=tuple(range(14, 21)),
               fmts={7: "0.000", 9: "0.000", 10: "0.000", 12: "0.0%", 13: "0.000", 14: "0.0", 16: "0.0", 18: "0.0", 19: "0.0%", 20: "0.0"})
    w3.cell(row=1, column=5).comment = Comment("終點站由 station_flow 的流程判斷：沒有往下一站連線的工站（多個時取編號最大）。"
                                               "這一步是圖形判斷，不適合用 Excel 公式，所以直接填入；人工驗算見 verify_formulas.py 的 A1–A4。", "驗證")
    check_fmt(w3, f"U2:AA{n_ln}")

    # ------------------------------------------------ 說明
    info.column_dimensions["A"].width = 26
    info.column_dimensions["B"].width = 90
    rows = [
        ("公式驗證", ""),
        ("資料來源", f"{db}資料庫（Supabase），讀取時間 {datetime.now(TW):%Y-%m-%d %H:%M}（台灣時間），唯讀"),
        ("資料筆數", f"event 共 {len(events)} 筆，其中完工（COMPLETED）{len(done)} 筆列入計算，未完工 {skipped} 筆不計"),
        ("驗證方法", "每個指標都用 Excel 公式從「原始資料」重算（黑字），旁邊放 Python 程式的結果（藍字、淺藍底），最右邊比對是否一致。"),
        ("容許誤差", "Python 顯示到小數 1 位，Excel 是未四捨五入的值，所以允許相差 0.05 以內（四捨五入最多造成的差距）；件數、工站名稱必須完全相同。"),
        ("", ""),
        ("公式", ""),
        ("場次", "產品編號 TEST2-P01 → 第 2 次測試；舊版 TEST-P01 → 第 1 次測試；沒有 TEST → 正式實作"),
        ("平均 Cycle Time", "該站作業秒數總和 ÷ 筆數"),
        ("瓶頸站", "平均 Cycle Time 最大的工站（同分取編號小的）"),
        ("平衡率", "各站平均 CT 總和 ÷（工站數 × 瓶頸 CT）"),
        ("等待時間", "同站上一件完工 → 下一件開工的空檔；第一件用產線首件開工時間；只計 0～600 秒"),
        ("稼動率", "總作業秒數 ÷（總作業秒數 + 總等待秒數）"),
        ("總耗時", "該場最晚完工 − 最早開工"),
        ("產出組數", "終點站的完工筆數；終點站還沒完工時，用有資料的最後一站試算"),
        ("節拍時間", "總耗時 ÷ 產出組數（同老師監控中心）"),
        ("", ""),
        ("比對結果", ""),
        ("各工站（項）", f'=COUNTIF(各工站!N2:Q{n_st},"✔")&" 項一致，"&COUNTIF(各工站!N2:Q{n_st},"✘")&" 項不一致"'),
        ("各場次（項）", f'=COUNTIF(各場次!U2:AA{n_ln},"✔")&" 項一致，"&COUNTIF(各場次!U2:AA{n_ln},"✘")&" 項不一致"'),
        ("", ""),
        ("其他驗證", "verify_formulas.py 另外做了：(A) 人工驗算的小例子、(B) pandas 獨立重算、(C) 照抄老師監控中心 JavaScript 的算法，三者都與 Python 一致。"),
    ]
    for r, (a, b) in enumerate(rows, start=1):
        info.cell(row=r, column=1, value=a).font = Font(name=F, bold=True, size=14 if r == 1 else 10)
        c = info.cell(row=r, column=2, value=b)
        c.font = Font(name=F, size=10, bold=a.startswith("各"))
        c.alignment = Alignment(wrap_text=True, vertical="top")
    out = Path(__file__).resolve().parent.parent / "verify" / f"公式驗證_{db}.xlsx"
    wb.save(out)
    print(out)


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "甲班")

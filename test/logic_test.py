
########################################################################
#メルカリ出品前に利益と利益率を計算するツールのテスト
#使い方;
#コマンドラインにpython app.py
#実行後、http://127.0.0.1:5000/へアクセス
########################################################################

# テスト用関数
# 通常は実行されない
#if __name__ == "__main__":以下の
#test_judgeのコメントアウトを外した場合、有効化される
def test_judge():
    print("=== test_judge(テスト開始) ===")
    test_cases = [
        (-100, "赤字です"),
        (0, "利益が少なめです。(要塞検討)"),
        (200, "利益が少なめです。(要塞検討)"),
        (300, "出品候補です"),
        (1000, "出品候補です"),
        ]

    for profit, expected in test_cases:
        result, judge_class = judge_profit(profit)
        print(f"profit={profit} -> {result} color:{judge_class} (期待値: {expected})")

        #想定外の結果が出た場合、NGと表示する
        if result != expected:
            print("   - > NG")

    print("=== test_judge(テスト終了) ===")
   
    print("=== calc_profit(テスト開始) ===")
    print(judge_profit(calc_profit(3000, 900, 600, 0.1)))
    print(judge_profit(calc_profit(5000, 300, 500, FEE_RATE)))
    print(judge_profit(calc_profit(2000, 3000, 300, FEE_RATE)))
    print("=== calc_profit(テスト終了) ===")

    return
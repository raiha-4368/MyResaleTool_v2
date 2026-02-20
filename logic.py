import os
import io
import csv
import sqlite3
import uuid
import logging
from datetime import datetime
from pathlib import Path

########################################################################
#メルカリ出品前に利益と利益率を計算するツールのロジック
#使い方;
#コマンドラインにpython app.py
#実行後、http://127.0.0.1:5000/へアクセス
########################################################################
#現状は固定値
#メルカリ手数料10%を想定
FEE_RATE = 0.1 

#エラーメッセージ定義
ERROR_POSITYVE = "数値は正の値を入力してください"
ERROR_TOO_LOW = "価格が原価+送料を下回っています"
ERROR_NOT_NUMBER = "価格・原価・送料は数値で入力してください"

#ソート機能用(ホワイトリストでの固定とするための定義)
ALLOWED_SORT = {
    "date": "date",
    "profit": "profit"
}
#昇順/降順[ASC(昇順) or DESC(降順)]
ALLOWED_ORDER = {
    "asc": "ASC",
    "desc": "DESC"
}
ALLOWED_FILTER = {
    "red": "red",
    "yellow": "yellow",
    "gureen": "green"
}


DB_PATH = "db/resale_tool.db"

TABLE_NAME = "history_data"

CREATE_TABLE_QUERY = """CREATE TABLE IF NOT EXISTS history_data (
               id INTEGER PRIMARY KEY AUTOINCREMENT,
               name TEXT NOT NULL,
               price INTEGER NOT NULL,
               cost_price INTEGER NOT NULL, 
               shipping INTEGER NOT NULL,
               unique_id INTEGER NOT NULL,
               date TIMESTAMP DEFAULT CURRENT_TIMESTAMP)"""

INSERT_QUERY = "INSERT INTO history_data (name, price, cost_price, shipping, unique_id) VALUES (?, ?, ?, ?, ?)"

# そのまますべて出力
SELECT_ALL_QUERY = "SELECT id, name, price, cost_price, shipping FROM history_data;"

#unique_idでの絞り込みのみを行う
SELECT_QUERY = "SELECT id, name, price, cost_price, shipping FROM history_data WHERE unique_id = ?"

#絞り込みを行わずすべて表示し、計算する
SELECT_QUERY_PROFIT = """
                        SELECT id, name, price, cost_price, shipping, profit, profit_rate, unique_id, date, judge, judge_color 
                        FROM (
                            SELECT *,
                                ROUND(profit * 100.0/ price, 2)AS profit_rate,
                                CASE
                                    WHEN profit > 300 THEN '出品候補です'
                                    WHEN profit > 0 THEN '利益が少なめです。(要塞検討)'
                                    ELSE '赤字です'
                                    END AS judge,
                                CASE
                                    WHEN profit > 300 THEN 'green'
                                    WHEN profit > 0 THEN 'yellow'
                                    ELSE 'red'
                                END AS judge_color
                            FROM(
                                SELECT *,
                                    (price - cost_price - shipping - (price * 0.1)) AS profit
                                    FROM history_data
                                    ) AS step1
                            ) AS step2
                        """

#1件だけ削除
DELETE_QUERY = "DELETE FROM history_data WHERE ID = ?"

#DELETE_ALL_QUERYでテーブル内のデータをすべて削除、RESET_IDで自動採番をリセット
DELETE_ALL_QUERY = "DELETE FROM history_data;"
RESET_ID = "DELETE FROM sqlite_sequence WHERE name ='history_data';"

#自動採番のIDごと全てリセット(SQliteでは存在しないコマンド)
#DELETE_ALL_QUERY = "TRUNCATE TABLE history_data;"

#ソート用
#新しいもの順
SORT_DATE = "ORDER BY date"
#利益順
SORT_PROFIT = "ORDER BY profit"

#フィルタ用(ソートと併用する場合はこちらを先に書く決まり)
FILTER_COLOR = "WHERE judge_color = ?"

#unique_idで絞り込み
FILTER_UNIQUE = "WHERE unique_id = ?"

#app.pyからlog設定を取得
logger = logging.getLogger("resale_app." + __name__)

# =====================================
# DBへの接続、SQLの実行を行う
# =====================================
def query_exe(sql, placeholder=None, fetch=False):
    logger.info("query_exe: falepath=%s", DB_PATH)
    conn = sqlite3.connect(DB_PATH)
    try:
        #辞書型設定
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        #placeholderがTrueならそのまま、Falseなら空を渡す
        cursor.execute(sql,placeholder or ())
        if fetch:
        # memo
        #fetchone() 1件だけ
        #fetchall() 全件
            return cursor.fetchall()
        else:
        #commitはselect文には不要のため分岐処理
            conn.commit()
            return None
    finally:
        conn.close()

# =====================================
# CREATE TABLE実行(なければ作成される)
# =====================================
def check_table():
  logger.info("check_table: path=%s", DB_PATH)
  query_exe(CREATE_TABLE_QUERY)
  return

# =====================================
# 数値の正当性をチェック
# =====================================
def input_check(price, cost_price, shipping):
    #数値の正当性をチェック
    error = None
    #priceが0の場合、みなし値を入れて処理を継続する形に変更。マイナスの値の場合エラーとするようにする
    if price < 0 or cost_price <= 0 or shipping <= 0:
        error = ERROR_POSITYVE
    # priceが0ではなく、価格が原価と送料を下回った場合エラーとする
    elif price != 0 and price < cost_price + shipping:
        error = ERROR_TOO_LOW
    return error

# =====================================
# 入力値に対する処理をindexから分離し、importでも使えるようにした関数
# =====================================
def input_exe(name, price, cost_price, shipping):
    logger.info("def input_exe 開始")
    try:
        name = str(name)
        price = int(price)
        cost_price = int(cost_price)
        shipping = int(shipping)
        result = None

        logger.info("入力受付: name=%s, price=%s, cost=%s, shipping=%s", name,price,cost_price,shipping)

        # 入力値チェック
        error = input_check(price, cost_price, shipping)

        #この時点でerrorがなければ処理を続行
        if not error:
            logger.info("入力値正常性確認完了")
            check_table()

            # priceが0だった場合、原価の1.2倍で計算
            if price == 0:
                price = (cost_price + shipping) * 1.2
                logger.info("価格自動調整: price=%s", price)


            unique_id = str(uuid.uuid4())
            placeholder = (name, price, cost_price, shipping, unique_id)
            query_exe(INSERT_QUERY, placeholder)
            query = SELECT_QUERY_PROFIT + " " + FILTER_UNIQUE
            result = query_exe(query, [unique_id], fetch=True)


            logger.info("result =")
            for r in result:
                logger.info("id : = %s", r['id'])
                logger.info("name : = %s", r['name'])
                logger.info("price : = %s", r['price'])
                logger.info("cost_price : = %s", r['cost_price'])
                logger.info("shipping : = %s", r['shipping'])
                logger.info("profit : = %s", r['profit'])
                logger.info("profit_rate : = %s", r['profit_rate'])
                logger.info("judge : = %s", r['judge'])
                logger.info("judge_color : = %s", r['judge_color'])
                logger.info("unique_id : = %s", r['unique_id'])
                logger.info("date : = %s", r['date'])

    except ValueError:
        error = ERROR_NOT_NUMBER
        logger.info("数値変換エラー")
     
    if error:
        logger.info("%s",error)

    return result, error

# =====================================
# フィルター及びソートを行う(想定される値)
# filter_key = (red, yellow, green)
# sort_key = (date, profit)
# order_key = (ASC, DESC)
# =====================================
def history_filter_and_sort(filter_key, sort_key, order_key):
    #フィルタとソートを同時に実行、文字列の結合による動的なQUERYの作成
    query = SELECT_QUERY_PROFIT
    placeholder = []

    #入力値のチェック(それぞれ想定入力値以外をデフォルトに変換)
    filter_key = ALLOWED_FILTER.get(filter_key, "")
    sort_key = ALLOWED_SORT.get(sort_key, "date")
    order_key = ALLOWED_ORDER.get(order_key, "ASC")

    #フィルタ設定
    if filter_key in ("red", "yellow", "gureen"):
        placeholder.append(filter_key)
        query += " "+ FILTER_COLOR
 
    #ソート設定
    if sort_key == "date":
        query += SORT_DATE + " " + order_key
    elif sort_key == "profit":
        query += SORT_PROFIT + " " + order_key

    logger.info("ソート＆フィルタ実行クエリ: %s", query)
    logger.info("プレースホルダ %s", placeholder)
    result = query_exe(query, placeholder, True)

    return result

# =====================================
# select_all
# =====================================
def select_exe():
    records = query_exe(SELECT_QUERY_PROFIT, fetch=True)
    return records

# =====================================
# delete_all
# =====================================
def delete_exe(d_flag, d_id):
    logger.info("def delete_exe %s,%s", d_flag, d_id)
    error = None

    #d_flagの文字列で処理を判定
    if d_flag == "ALL_DELETE":
        query_exe(DELETE_ALL_QUERY)
        query_exe(RESET_ID)
    elif d_flag  == "DELETE" and d_id:
        query_exe(DELETE_QUERY, [d_id])
    else:
        error  = "削除対象がただしく設定されていません。"
    
    logger.info("error: %s",error)
    return error


# =====================================
# select_allしてからそれをcsvファイルに書き込み
# =====================================
def download_exe(filename):
    query = SELECT_QUERY_PROFIT + " " + FILTER_UNIQUE
    records = query_exe(query, fetch=True)
    logger.info("def download_exe 開始")
    #outputディレクトリがなければ作成
    os.makedirs("output", exist_ok=True)
    
    #新規書き込みw,追記モードaで使い分け
    with open(filename, mode='w', newline="", encoding="utf-8") as f:
        write = csv.DictWriter(f, fieldnames=records[0].keys())
        #サイズが0なら見出し行を付ける処理
        if os.path.getsize(filename) == 0:
            write.writeheader()
        #1行だけ書き込む処理
        # write.writerow(records)
        #複数行を書き込む処理
        write.writerows(records)
    logger.info(f"CSV出力完了:{filename}")

    # ファイルが存在する場合のみ削除
    # ダウンロード後消そうと思ったけど、ここに書いちゃ意味無かった奴
    # if os.path.exists(filename):
    #     Path(filename).unlink()
    #     logger.info("%sを削除しました", filename)
    # else:
    #     logger.info("ファイルが見つかりません")
    return 

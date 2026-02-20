import os
import io
import csv
import logging
from logging.handlers import RotatingFileHandler

#======================================
# logging 設定
#======================================
# Logger 作成
logger = logging.getLogger("resale_app")
logger.setLevel(logging.INFO)

# handler 作成
log_handler = RotatingFileHandler(
        "logs/app.log",
        maxBytes = 1024 * 1024, # 1MBでローテーション
        backupCount = 3,        # 古いログを3世代保持
        encoding = "utf-8"
    )

# formatter
log_formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(message)s"
    )
log_handler.setFormatter(log_formatter)

# handler 登録(重複防止)
if not logger.handlers:
    logger.addHandler(log_handler)

#hundlerを設定した場合、basicConfigは設定しない(重複する)
# logging.basicConfig(
#     level=logging.INFO,
#     format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
#     filename="logs/app.log",
#     encoding="utf-8"
# )

import logic
from flask import Flask, render_template, request,send_file, redirect, url_for
from flask import session

########################################################################
#メルカリ出品前に利益と利益率を計算するツール
#使い方;
#コマンドラインにpython app.py
#実行後、http://127.0.0.1:5000/へアクセス
########################################################################

app = Flask(__name__)

#セッションでの情報保持用(必須)
app.secret_key = "dev-secret-key"

#エラーメッセージ定義
ERROR_REQUIRED = "すべての項目を入力してください"

#ソート機能用
#csvファイルのカラム名とhtmlのページの齟齬を埋めるためのもの
SORT_MAP = {
    "profit": "利益",
    "date": "日時"
}

@app.route('/', methods=["GET","POST"])
def index():
    logger.info("def index 開始")
    
    #infoかdebugどっちがいいかは要検討
    logger.debug("URL: %s", request.url)

    result = None
    error = None

    import_result = session.pop("import_result", None)
    import_success = session.pop("import_success", False)
    #今使えていないかもしれないerror
    error = session.pop("import_error", None)

    if request.method == "POST":
        name = request.form.get("name")
        price = request.form.get("price")
        cost_price = request.form.get("cost_price")
        shipping = request.form.get("shipping")
        #必須項目の空欄チェック
        if not name or not cost_price or not shipping:
            error = ERROR_REQUIRED
            logger.warning("未入力エラー")
        elif not price and cost_price:
            logger.info("売値設定がない状態で原価入力された場合、いくら足せば利益が出るのか計算する")
            result,error = logic.input_exe(name, 0, cost_price, shipping)

        else:
            #入力値に対する処理を行う
            result,error = logic.input_exe(name, price, cost_price, shipping)

    return render_template("index.html", 
                            result=result,
                            error=error,
                            import_success=import_success,
                            import_records=import_result,)

@app.route("/history")
def history():
    """
    history の Docstring
    過去の入力履歴であるoutput.csvを読み込み、それを並び替えもしくは特定条件で絞り込みを行う
    押されたURLによってページ遷移を行い、読み込み、切り替えを行う
    """
    logger.info("def history開始")
    logger.info("URL: %s", request.url)

    records = logic.select_exe()

    # #渡されたURLのsort=の部分を取得。デフォルトは日付
    sort_parm = request.args.get("sort") or "date"

    # #sort_pramを鍵として、SORT_MAPから値を取得(取得できなければデフォルトを日時とする)
    sort_key = SORT_MAP.get(sort_parm, "日時")

    # #渡されたURLのfilter部分を取得。デフォルト値は指定なし
    filter_key = request.args.get("filter", None)

    # 昇順/降順を取得
    order_key = request.args.get("order", "asc")

    logger.info("sort_parm:%s",sort_parm)
    logger.info("sort_key:%s",sort_key)
    logger.info("filter_key:%s",filter_key)
    logger.info("order_key:%s",order_key)

    # ソート&フィルター処理
    records = logic.history_filter_and_sort(filter_key, sort_parm, order_key)

    return render_template(
        "history.html",
         records=records,
         current_sort=sort_parm,
         current_filter=filter_key,
         current_order=order_key)

@app.route("/delete_all")
def delete_all():
    logger.info("def delete_all 開始")
    logic.delete_exe("ALL_DELETE", None)
    logger.info("ALL_DELETE_QUERY実行、履歴データ削除完了")
    return redirect(url_for("history"))

@app.route("/delete")
def delete():
    logger.info("def delete 開始")
    #日付を取得
    target_id = request.args.get("id")
    logger.info("レコード削除: target_id= %s", target_id)

    logic.delete_exe("DELETE", target_id)

    #redirect(url_for("history"))は
    #今の関数で画面を描かない、もとのURLに戻して再読み込みの意味がある
    #request.referrerでソートやフィルターの状態を持ちこしてhistoryに戻る
    return redirect(request.referrer or url_for("history"))

@app.route("/download")
def download_csv():
    logger.info("def download_csv 開始")

    path = "output/download.csv"
    logger.info("CSVダウンロード実行")
    logic.download_exe(path)

    # ファイル削除案、失敗(flaskがファイルを使用している状態で消そうとしてしまう為)
    # @after_this_request
    # def remove_file(response):
    #     logger.info("def remove_file 開始")
    #     try:
    #         os.remove(path)
    #     except Exception as error:
    #         app.logger.error(f"Error removing or closing downloaded file: {error}")
    #     return response

    return send_file(
        path,
        as_attachment=True,
        download_name = "profit_history.csv",
        mimetype = "text/csv"
    )

@app.route('/import', methods=["POST"])
def import_csv():
    logger.info("def import_csv 開始")
    file = request.files.get("file")

    results = []
    error = None

    logger.info("CSV import 開始: %s", file.filename)

    if not file:
        logger.error("ファイルがアップロードされていません。")
        return redirect("/")
    
    stream = io.StringIO(file.stream.read().decode("utf-8"), newline=None)
    rows = csv.DictReader(stream)
    logger.info("ファイルにあるデータ: %s", rows)
    count = 0
    for row in rows:
        try:
            logger.info("row確認: %s", row)

            name = str(row["name"])
            price= int(row["price"])
            cost_price= int(row["cost_price"])
            shipping= int(row["shipping"])

            #入力値に対する処理を行う
            result, error = logic.input_exe(name, price, cost_price, shipping)
            for r in result:
                row_dict = dict(r)       # 辞書に変換
                results.append(row_dict) 

            count += 1
        except Exception as e:
            logger.error("インポート失敗 row=%s, error=%s", row, e)
        
        logger.info("CSV import finished: %s rows", count)

    session["import_result"] = results
    session["import_success"] = True
    session["import errror"] = error

#    render_template("index.html", import_success=True, imported_records=results, error=error)
    return redirect(url_for("index"))

#↓これは一番最後に書いて無きゃいけなさそう
if __name__ == "__main__":
    os.makedirs("logs", exist_ok=True)

    app.run(debug=True)




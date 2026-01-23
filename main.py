import streamlit as st
import pandas as pd
import gspread
from google.oauth2 import service_account
import time
from datetime import datetime, timedelta

# --- 認証の設定関数 ---
def get_gspread_client():
    try:
        key_dict = dict(st.secrets["gcp_service_account"])
        if "private_key" in key_dict:
            key_dict["private_key"] = key_dict["private_key"].replace("\\n", "\n")
        scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
        creds = service_account.Credentials.from_service_account_info(key_dict, scopes=scopes)
        return gspread.authorize(creds)
    except Exception as e:
        st.error(f"認証エラー: 設定の読み込みに失敗しました。\n{e}")
        return None

# --- データの読み込み関数 ---
def load_data():
    client = get_gspread_client()
    if not client:
        return pd.DataFrame(), None, None
    try:
        # メインシートを開く
        sheet = client.open("inventory_data").sheet1 
        data = sheet.get_all_records()
        df = pd.DataFrame(data)
        
        # ログシートを開く（なければエラーになるのでtryで囲む）
        try:
            log_sheet = client.open("inventory_data").worksheet("log")
        except:
            st.error("スプレッドシートに 'log' という名前のシートを作成してください！")
            return pd.DataFrame(), None, None

        # 列不足の保険
        if "ジャンル" not in df.columns: df["ジャンル"] = "未分類"
        if "必要在庫数" not in df.columns: df["必要在庫数"] = 0
        if "月間使用量" not in df.columns: df["月間使用量"] = 0 # 新機能

        # 数値変換
        cols = ["個数", "必要在庫数", "月間使用量"]
        for c in cols:
            df[c] = pd.to_numeric(df[c], errors='coerce').fillna(0)
        
        return df, sheet, log_sheet
    except Exception as e:
        st.error(f"シートの読み込みエラー: {e}")
        return pd.DataFrame(), None, None

# --- 色分けルール ---
def highlight_stock_status(row):
    if row["個数"] < row["必要在庫数"]:
        return ['color: red; font-weight: bold'] * len(row)
    elif row["個数"] > 0 and row["個数"] >= (row["必要在庫数"] * 2):
        return ['color: #1E90FF; font-weight: bold'] * len(row)
    else:
        return [''] * len(row)

# --- ログ記録関数 ---
def add_log(log_sheet, item_name, change_amount, action_type):
    # 日本時間（簡易的）
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    # logシートの末尾に追加
    log_sheet.append_row([now, item_name, change_amount, action_type])

# --- アプリのメイン処理 ---
st.title("📦 在庫管理アプリ")

# データを読み込む（log_sheetも取得）
df, sheet, log_sheet = load_data()

# ---------------------------------------------------------
# サイドバー設定
# ---------------------------------------------------------
st.sidebar.title("メニュー")

st.sidebar.subheader("🔍 表示切り替え")
if not df.empty:
    all_genres = ["すべて"] + list(df["ジャンル"].unique())
    selected_genre = st.sidebar.selectbox("ジャンルを選択", all_genres)
else:
    selected_genre = "すべて"

st.sidebar.markdown("---")
is_admin = False
if st.sidebar.checkbox("管理者モード（編集）"):
    password = st.sidebar.text_input("管理者パスワード", type="password")
    if password == st.secrets["admin_password"]:
        st.sidebar.success("ログイン中")
        is_admin = True
    elif password:
        st.sidebar.error("パスワードが違います")

# ---------------------------------------------------------
# メイン画面：在庫一覧
# ---------------------------------------------------------
if selected_genre == "すべて":
    df_display = df
else:
    df_display = df[df["ジャンル"] == selected_genre]

st.info("在庫の増減は自動的にログに記録され、管理者が「使用量」を集計できます。")

if not df.empty:
    # 必要な列だけ表示
    display_cols = ["商品名", "個数", "ジャンル", "必要在庫数", "月間使用量"]
    # カラムが存在するか確認してから表示
    valid_cols = [c for c in display_cols if c in df_display.columns]
    st.dataframe(df_display[valid_cols].style.apply(highlight_stock_status, axis=1))

# ---------------------------------------------------------
# 入出庫エリア（ログ記録機能付き）
# ---------------------------------------------------------
st.markdown("---")
st.subheader("📝 在庫数の更新")

if not df.empty:
    with st.form(key='update_stock_form'):
        col1, col2 = st.columns(2)
        with col1:
            target_name = st.selectbox("商品を選択", df_display["商品名"].unique())
        with col2:
            new_quantity = st.number_input("現在の在庫数", min_value=0, step=1)

        update_btn = st.form_submit_button("在庫数を更新")

        if update_btn:
            try:
                # 変更前の値を取得
                old_quantity = df[df["商品名"] == target_name]["個数"].values[0]
                diff = new_quantity - old_quantity # 変動数（増えたらプラス、減ったらマイナス）
                
                # シート更新
                cell = sheet.find(target_name)
                sheet.update_cell(cell.row, 2, new_quantity)
                
                # ★ログに記録（差分がある時だけ）
                if diff != 0:
                    action = "入庫" if diff > 0 else "出庫(使用)"
                    add_log(log_sheet, target_name, diff, action)

                st.success(f"「{target_name}」を更新しました！（{diff}個）")
                time.sleep(1)
                st.rerun()
            except Exception as e:
                st.error(f"更新エラー: {e}")
else:
    st.warning("データがありません。")

# ---------------------------------------------------------
# 管理者専用エリア
# ---------------------------------------------------------
if is_admin:
    st.markdown("---")
    st.markdown("### 🔧 管理者メニュー")
    
    tab1, tab2, tab3 = st.tabs(["商品の追加", "商品の削除", "📊 月間使用量の集計"])

    # 【追加機能】
    with tab1:
        with st.form(key='add_form'):
            col_a, col_b = st.columns(2)
            with col_a: name = st.text_input("商品名")
            with col_b: genre = st.text_input("ジャンル")
            col_c, col_d = st.columns(2)
            with col_c: quantity = st.number_input("初期在庫", min_value=0)
            with col_d: required = st.number_input("必要在庫", min_value=0)
            
            if st.form_submit_button("追加する"):
                if name and genre:
                    sheet.append_row([name, quantity, genre, required, 0]) # 月間使用量は0で初期化
                    st.success(f"追加しました")
                    time.sleep(1)
                    st.rerun()

    # 【削除機能】
    with tab2:
        delete_target = st.selectbox("削除選択", df["商品名"].unique(), key='del')
        if st.button("削除実行"):
            cell = sheet.find(delete_target)
            sheet.delete_rows(cell.row)
            st.success("削除しました")
            time.sleep(1)
            st.rerun()

    # 【★新機能：月間使用量の計算】
    with tab3:
        st.write("履歴（log）シートから、直近30日間の使用量（減った数）を計算して、メインシートに記録します。")
        
        if st.button("集計を実行して記録する"):
            with st.spinner("集計中...少々お待ちください"):
                try:
                    # 1. ログを全取得
                    logs = log_sheet.get_all_records()
                    log_df = pd.DataFrame(logs)
                    
                    # 2. 日付でフィルタリング（直近30日）
                    log_df["日時"] = pd.to_datetime(log_df["日時"])
                    cutoff_date = datetime.now() - timedelta(days=30)
                    recent_logs = log_df[log_df["日時"] >= cutoff_date]
                    
                    # 3. 商品ごとに「マイナスの変動（使用）」だけを合計
                    # 変動数がマイナスのものだけ抽出して、絶対値にする
                    usage_df = recent_logs[recent_logs["変動数"] < 0].copy()
                    usage_df["使用数"] = usage_df["変動数"].abs() # マイナスをプラスに変換
                    
                    # 集計：商品名ごとの合計
                    summary = usage_df.groupby("商品名")["使用数"].sum()
                    
                    # 4. メインシートに書き込み
                    # 行ごとにチェックして書き込む（少し時間がかかります）
                    cell_list = []
                    # 商品名の一覧を取得
                    items = sheet.col_values(1)[1:] # 1行目は見出しなので飛ばす
                    
                    for i, item_name in enumerate(items):
                        row_num = i + 2 # スプレッドシートの行番号（2行目から開始）
                        usage_amount = 0
                        
                        if item_name in summary:
                            usage_amount = int(summary[item_name])
                        
                        # E列（5列目）を更新
                        sheet.update_cell(row_num, 5, usage_amount)
                    
                    st.success("集計完了！メイン画面の「月間使用量」が更新されました。")
                    time.sleep(2)
                    st.rerun()
                    
                except Exception as e:
                    st.error(f"集計エラー: {e}")
                    
import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime, timedelta

# --- 設定 ---
# ★注意: スプレッドシートの名前が合っているか確認してください
SHEET_NAME = "inventory" 
# 認証用ファイル名
# ▼ ここからコピー ▼
from google.oauth2 import service_account
import json

# StreamlitのSecretsから鍵情報を読み込む
key_dict = dict(st.secrets["gcp_service_account"])
key_dict["private_key"] = key_dict["private_key"].replace("\\n", "\n")
creds = service_account.Credentials.from_service_account_info(key_dict)
gc = gspread.authorize(creds)
# ▲ ここまでコピー ▲
# 簡易パスワード
LOGIN_PASSWORD = "1234"

# --- 認証と接続 ---
def get_gspread_client():
    try:
        scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
        creds = ServiceAccountCredentials.from_json_keyfile_name(JSON_FILE, scope)
        client = gspread.authorize(creds)
        return client
    except Exception as e:
        st.error(f"認証エラー: {JSON_FILE} の読み込みに失敗しました。\n{e}")
        return None

# --- データ取得 ---
def load_data():
    client = get_gspread_client()
    if not client: return None, None
    try:
        sheet = client.open(SHEET_NAME).sheet1
        data = sheet.get_all_records()
        df = pd.DataFrame(data)
        return df, sheet
    except Exception as e:
        st.error(f"スプレッドシート '{SHEET_NAME}' が見つかりません: {e}")
        return None, None

# --- データ更新（在庫数） ---
def update_stock(sheet, row_idx, new_value, col_name="現在在庫数"):
    try:
        # ヘッダー行(1) + 0始まりindex + 1 = row_idx + 2
        cell = sheet.find(col_name)
        sheet.update_cell(row_idx + 2, cell.col, new_value)
        st.toast(f"在庫を {new_value} 個に更新しました！") 
    except Exception as e:
        st.error(f"更新エラー: {e}")

# --- 新規追加 ---
def add_new_item(sheet, genre, name, current, required, last_date, interval):
    try:
        date_str = last_date.strftime('%Y/%m/%d')
        sheet.append_row([genre, name, current, required, date_str, interval])
        st.success(f"「{name}」を追加しました！")
        return True
    except Exception as e:
        st.error(f"追加エラー: {e}")
        return False

# --- アプリのメインレイアウト ---
st.set_page_config(page_title="在庫管理アプリ", layout="wide")

# セッション状態の初期化
if 'logged_in' not in st.session_state:
    st.session_state['logged_in'] = False

# --- ログイン画面 ---
if not st.session_state['logged_in']:
    st.title("🔐 ログイン")
    password = st.text_input("パスワードを入力", type="password")
    if st.button("ログイン"):
        if password == LOGIN_PASSWORD:
            st.session_state['logged_in'] = True
            st.rerun()
        else:
            st.error("パスワードが違います")
    st.stop()

# --- メインアプリ画面 ---
df, sheet = load_data()

# サイドバー：モード切替
st.sidebar.title("メニュー")
mode = st.sidebar.radio("モード選択", ["在庫入力 (メンバー)", "商品登録・設定 (管理者)"])

if df is not None:
    # === ユーザーモード（在庫入力） ===
    if mode == "在庫入力 (メンバー)":
        st.title("📦 在庫管理")
        
        if df.empty:
            st.info("まだデータがありません。「管理者」メニューから商品を登録してください。")
        else:
            # ジャンルフィルタ
            if "ジャンル" in df.columns:
                genres = ["すべて"] + list(df["ジャンル"].unique())
                selected_genre = st.selectbox("ジャンルで絞り込み", genres)
                view_df = df if selected_genre == "すべて" else df[df["ジャンル"] == selected_genre]
            else:
                view_df = df

            # カード形式で表示
            for index, row in view_df.iterrows():
                with st.container():
                    st.markdown("---")
                    col1, col2 = st.columns([3, 2])
                    
                    # 左側：商品情報
                    with col1:
                        st.subheader(row.get("品名", "名称不明"))
                        st.caption(f"ジャンル: {row.get('ジャンル', '-')}")
                        
                        current_stock = int(row.get("現在在庫数", 0))
                        required_stock = int(row.get("必要在庫数", 0))
                        
                        if current_stock < required_stock:
                            st.error(f"⚠️ 在庫不足! (あと {required_stock - current_stock} 個必要)")
                        else:
                            st.success("在庫あり")

                    # 右側：操作パネル
                    with col2:
                        st.metric("現在在庫", f"{current_stock} 個")
                        
                        # 数値入力ボックス
                        amount = st.number_input(
                            "数量", 
                            min_value=1, 
                            value=1, 
                            step=1, 
                            key=f"amount_{index}", 
                            label_visibility="collapsed"
                        )

                        b_col1, b_col2 = st.columns(2)
                        with b_col1:
                            # 出庫ボタン
                            if st.button(f"使った\n(-{amount})", key=f"minus_{index}"):
                                new_val = max(0, current_stock - amount)
                                update_stock(sheet, index, new_val)
                                st.rerun()
                        with b_col2:
                            # 入庫ボタン
                            if st.button(f"入荷\n(+{amount})", key=f"plus_{index}"):
                                new_val = current_stock + amount
                                update_stock(sheet, index, new_val)
                                st.rerun()

    # === 管理者モード ===
    # === 管理者モード ===
    elif mode == "商品登録・設定 (管理者)":
        st.title("🛠 管理画面")

        st.markdown("### ➕ 新しい商品の登録")
        with st.form("add_form"):
            col_a, col_b = st.columns(2)
            with col_a:
                new_genre = st.text_input("ジャンル (例: 文房具)")
                new_name = st.text_input("商品名 (例: ボールペン)")
                new_interval = st.number_input("発注間隔(日)", value=30, step=1)
            
            with col_b:
                new_current = st.number_input("現在の在庫数", min_value=0, value=10)
                new_last_date = st.date_input("最終発注日", datetime.now())
                
                # --- ★ここを変更しました★ ---
                st.markdown("---")
                st.caption("📦 必要在庫数の自動計算")
                daily_usage = st.number_input("1日の使用量", min_value=0.0, value=1.0, step=0.1, format="%.1f")
                lead_time = st.number_input("発注〜入荷までの日数", min_value=0, value=3, step=1)
                
                # ここで計算してしまう
                # ceilを使って切り上げたい場合は import math が必要ですが、今回は単純な掛け算にします
                # 計算結果を整数(int)にしておく
                new_required = int(daily_usage * lead_time)
                
                st.info(f"計算結果: 必要在庫数は **{new_required}個** として登録されます。")
                # -----------------------------
            
            submitted = st.form_submit_button("商品を登録する")
            
            if submitted:
                if new_name and new_genre:
                    # 計算済みの new_required を渡して登録
                    if add_new_item(sheet, new_genre, new_name, new_current, new_required, new_last_date, new_interval):
                        st.rerun()
                else:
                    st.warning("ジャンルと商品名は必須です")

        st.markdown("---")
        # ...（以下、一覧表示のコードはそのまま）
        
        # --- ここに追加しました: ジャンル絞り込み機能 ---
        if not df.empty and "ジャンル" in df.columns:
            # 管理者用のジャンルリスト作成
            admin_genres = ["すべて"] + list(df["ジャンル"].unique())
            # keyを指定して、メンバー側のボックスと区別します
            admin_selected_genre = st.selectbox("表示するジャンルを選択", admin_genres, key="admin_genre_filter")
            
            # フィルタリング実行
            if admin_selected_genre == "すべて":
                admin_view_df = df
            else:
                admin_view_df = df[df["ジャンル"] == admin_selected_genre]
            
            # 絞り込んだ結果を表示
            st.dataframe(admin_view_df)
        else:
            # データがない、またはジャンル列がない場合はそのまま表示
            st.dataframe(df)

        if st.button("ログアウト"):
            st.session_state['logged_in'] = False
            st.rerun()
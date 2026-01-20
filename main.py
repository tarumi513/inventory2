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
        # 1. Secretsから認証情報を辞書として取り出す
        key_dict = dict(st.secrets["gcp_service_account"])

        # 2. 鍵の改行コード（\n）を正しく変換する
        if "private_key" in key_dict:
            key_dict["private_key"] = key_dict["private_key"].replace("\\n", "\n")

        # 3. 認証の範囲を設定
        scopes = [
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive"
        ]

        # 4. 認証を行ってクライアントを返す
        creds = service_account.Credentials.from_service_account_info(key_dict, scopes=scopes)
        return gspread.authorize(creds)

    except Exception as e:
        st.error(f"認証エラー: 設定の読み込みに失敗しました。\n{e}")
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
        
     # --- アプリの表示部分 ---
st.title("在庫管理アプリ")

# データの読み込み
df, sheet = load_data()

# --- サイドバー：管理者ログイン ---
st.sidebar.title("メニュー")
is_admin = False # 最初は管理者じゃない状態

# 管理者モードのチェックボックス
if st.sidebar.checkbox("管理者モード（編集する）"):
    password = st.sidebar.text_input("管理者パスワード", type="password")
    if password == st.secrets["admin_password"]:
        st.sidebar.success("ログイン成功！編集できます")
        is_admin = True # パスワードが合っていたら管理者フラグON
    elif password:
        st.sidebar.error("パスワードが違います")

# --- メイン画面：在庫一覧（全員が見れる） ---
st.subheader("現在の在庫一覧")
st.dataframe(df)

# --- 管理者専用エリア（is_adminがTrueのときだけ表示） ---
if is_admin:
    st.markdown("---")
    st.subheader("🔧 在庫の編集（管理者のみ）")

    # 1. 新規追加フォーム
    with st.form(key='add_form'):
        name = st.text_input("商品名")
        quantity = st.number_input("個数", min_value=0, step=1)
        submit_btn = st.form_submit_button("追加")
        
        if submit_btn:
            if name:
                new_row = [name, quantity]
                sheet.append_row(new_row)
                st.success(f"「{name}」を追加しました！")
                time.sleep(1)
                st.rerun()
            else:
                st.warning("商品名を入力してください")

    # 2. 削除フォーム
    st.markdown("---")
    delete_target = st.selectbox("削除する商品を選択", df["商品名"].unique())
    if st.button("削除"):
        try:
            cell = sheet.find(delete_target)
            sheet.delete_rows(cell.row)
            st.success(f"「{delete_target}」を削除しました")
            time.sleep(1)
            st.rerun()
        except Exception as e:
            st.error(f"エラーが発生しました: {e}")

else:
    # 管理者じゃない人に表示するメッセージ
    st.info("※ 在庫の追加・削除を行う場合は、左のサイドバーから「管理者モード」にチェックを入れてください。")
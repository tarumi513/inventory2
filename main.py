import streamlit as st
import pandas as pd
import gspread
from google.oauth2 import service_account
import time

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
        return pd.DataFrame(), None
    try:
        sheet = client.open("inventory_data").sheet1 
        data = sheet.get_all_records()
        df = pd.DataFrame(data)
        
        # 列が存在しない場合の保険
        if "ジャンル" not in df.columns:
            df["ジャンル"] = "未分類"
        if "必要在庫数" not in df.columns:
            df["必要在庫数"] = 0

        # 数値変換（計算できるようにする）
        df["個数"] = pd.to_numeric(df["個数"], errors='coerce').fillna(0)
        df["必要在庫数"] = pd.to_numeric(df["必要在庫数"], errors='coerce').fillna(0)
        
        return df, sheet
    except Exception as e:
        st.error(f"シートの読み込みエラー: {e}")
        return pd.DataFrame(), None

# --- ★ここが重要：色分けのルール関数 ---
def highlight_stock_status(row):
    # 1. 不足している場合（赤色）
    if row["個数"] < row["必要在庫数"]:
        return ['color: red; font-weight: bold'] * len(row)
    
    # 2. 過剰在庫の場合（青色）：必要数の2倍以上
    # ※ただし、個数が0の場合は青くしないようにする（0個なのに過剰はおかしいため）
    elif row["個数"] > 0 and row["個数"] >= (row["必要在庫数"] * 2):
        # 見やすい青色（DodgerBlue）を指定
        return ['color: #1E90FF; font-weight: bold'] * len(row)
    
    # 3. それ以外（普通）
    else:
        return [''] * len(row)

# --- アプリのメイン処理 ---
st.title("📦 在庫管理アプリ")

# データを読み込む
df, sheet = load_data()

# ---------------------------------------------------------
# サイドバー設定
# ---------------------------------------------------------
st.sidebar.title("メニュー")

st.sidebar.subheader("🔍 表示切り替え")
all_genres = ["すべて"] + list(df["ジャンル"].unique())
selected_genre = st.sidebar.selectbox("ジャンルを選択", all_genres)

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
# ジャンルで絞り込み
if selected_

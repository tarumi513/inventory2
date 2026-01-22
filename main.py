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
        # 空欄（NaN）があるとエラーになることがあるので、空文字で埋める
        df = df.fillna("")
        # もし「ジャンル」列がまだない場合のために、強制的に作る
        if "ジャンル" not in df.columns:
            df["ジャンル"] = "未分類"
        return df, sheet
    except Exception as e:
        st.error(f"シートの読み込みエラー: {e}")
        return pd.DataFrame(), None

# --- アプリのメイン処理 ---
st.title("📦 在庫管理アプリ")

# データを読み込む
df, sheet = load_data()

# ---------------------------------------------------------
# サイドバー設定（ジャンル絞り込み ＆ ログイン）
# ---------------------------------------------------------
st.sidebar.title("メニュー")

# 1. ジャンルで絞り込み機能
st.sidebar.subheader("🔍 表示切り替え")
# データからジャンルの一覧（重複なし）を取得
all_genres = ["すべて"] + list(df["ジャンル"].unique())
selected_genre = st.sidebar.selectbox("ジャンルを選択", all_genres)

# 2. 管理者ログイン機能
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
# ジャンルでデータをフィルタリングする
if selected_genre == "すべて":
    df_display = df
else:
    df_display = df[df["ジャンル"] == selected_genre]

st.info("在庫数の変更は下のフォームから誰でも行えます。")

# フィルタリングされた表を表示
st.dataframe(df_display)

# ---------------------------------------------------------
# 入出庫エリア（誰でも操作OK）
# ---------------------------------------------------------
st.markdown("---")
st.subheader("📝 在庫数の更新")

if not df.empty:
    with st.form(key='update_stock_form'):
        col1, col2 = st.columns(2)
        with col1:
            # 絞り込まれたリストの中から商品を選ぶ
            target_name = st.selectbox("商品を選択", df_display["商品名"].unique())
        with col2:
            new_quantity = st.number_input("現在の在庫数", min_value=0, step=1)

        update_btn = st.form_submit_button("在庫数を更新")

        if update_btn:
            try:
                cell = sheet.find(target_name)
                # 2列目（個数）を更新
                sheet.update_cell(cell.row, 2, new_quantity)
                st.success(f"「{target_name}」を更新しました！")
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
    
    tab1, tab2 = st.tabs(["商品の追加", "商品の削除"])

    # 【追加機能】ジャンルも入力できるように変更
    with tab1:
        with st.form(key='add_form'):
            col_a, col_b = st.columns(2)
            with col_a:
                name = st.text_input("商品名")
            with col_b:
                # 既存のジャンルから選ぶか、手入力するか
                genre = st.text_input("ジャンル（例: レジン）")
            
            quantity = st.number_input("初期在庫数", min_value=0, step=1)
            submit_btn = st.form_submit_button("追加する")
            
            if submit_btn:
                if name and genre:
                    # シートの末尾に [商品名, 個数, ジャンル] を追加
                    sheet.append_row([name, quantity, genre])
                    st.success(f"「{name}」を追加しました！")
                    time.sleep(1)
                    st.rerun()
                else:
                    st.warning("商品名とジャンルを入力してください")

    # 【削除機能】
    with tab2:
        delete_target = st.selectbox("削除する商品を選択", df["商品名"].unique(), key='del_select')
        if st.button("削除実行"):
            try:
                cell = sheet.find(delete_target)
                sheet.delete_rows(cell.row)
                st.success(f"「{delete_target}」を削除しました")
                time.sleep(1)
                st.rerun()
            except Exception as e:
                st.error(f"削除エラー: {e}")
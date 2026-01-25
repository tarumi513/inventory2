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
        sheet = client.open("inventory_data").sheet1 
        data = sheet.get_all_records()
        df = pd.DataFrame(data)
        
        try:
            log_sheet = client.open("inventory_data").worksheet("log")
        except:
            return pd.DataFrame(), None, None

        if "ジャンル" not in df.columns: df["ジャンル"] = "未分類"
        if "必要在庫数" not in df.columns: df["必要在庫数"] = 0
        if "月間使用量" not in df.columns: df["月間使用量"] = 0

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
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_sheet.append_row([now, item_name, change_amount, action_type])

# --- アプリのメイン処理 ---
st.title("📦 在庫管理アプリ")

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

if not df.empty:
    display_cols = ["商品名", "個数", "ジャンル", "必要在庫数", "月間使用量"]
    valid_cols = [c for c in display_cols if c in df_display.columns]
    
    # データフレームを表示（高さ固定をやめて全表示）
    st.dataframe(df_display[valid_cols].style.apply(highlight_stock_status, axis=1))

# ---------------------------------------------------------
# 入出庫エリア（★ここを大幅に変更しました）
# ---------------------------------------------------------
st.markdown("---")
st.subheader("📝 在庫の入出庫")

if not df.empty:
    with st.form(key='update_stock_form'):
        # 1行目：商品選択
        target_name = st.selectbox("商品を選択", df_display["商品名"].unique())
        
        # 現在の在庫数を取得して表示（確認用）
        current_stock = df[df["商品名"] == target_name]["個数"].values[0]
        st.caption(f"現在の在庫: {current_stock} 個")

        # 2行目：操作選択と数量入力
        col1, col2 = st.columns(2)
        with col1:
            action = st.selectbox("操作", ["出庫 (使う)", "入庫 (補充)", "棚卸し (修正)"])
        with col2:
            amount = st.number_input("数量", min_value=0, step=1, value=1)

        update_btn = st.form_submit_button("実行")

        if update_btn:
            try:
                # 新しい在庫数を計算
                new_quantity = current_stock
                log_amount = 0
                log_action = ""

                if action == "出庫 (使う)":
                    new_quantity = current_stock - amount
                    log_amount = -amount
                    log_action = "出庫"
                    if new_quantity < 0:
                        st.warning("⚠️ 在庫がマイナスになりますが、そのまま記録します。")
                
                elif action == "入庫 (補充)":
                    new_quantity = current_stock + amount
                    log_amount = amount
                    log_action = "入庫"

                elif action == "棚卸し (修正)":
                    # 入力された数値をそのまま「正」とする
                    new_quantity = amount
                    log_amount = new_quantity - current_stock # 差分を記録
                    log_action = "棚卸修正"

                # 更新処理
                if log_amount != 0 or action == "棚卸し (修正)":
                    cell = sheet.find(target_name)
                    sheet.update_cell(cell.row, 2, new_quantity)
                    
                    # ログ記録
                    add_log(log_sheet, target_name, log_amount, log_action)

                    st.success(f"「{target_name}」を {new_quantity} 個に更新しました！（{log_action}）")
                    time.sleep(1)
                    st.rerun()
                else:
                    st.warning("数量が0です。")

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
                    sheet.append_row([name, quantity, genre, required, 0])
                    st.success(f"追加しました")
                    time.sleep(1)
                    st.rerun()

    with tab2:
        delete_target = st.selectbox("削除選択", df["商品名"].unique(), key='del')
        if st.button("削除実行"):
            cell = sheet.find(delete_target)
            sheet.delete_rows(cell.row)
            st.success("削除しました")
            time.sleep(1)
            st.rerun()

    with tab3:
        st.write("履歴（log）シートから、直近30日間の使用量（減った数）を計算して、メインシートに記録します。")
        if st.button("集計を実行して記録する"):
            with st.spinner("集計中..."):
                try:
                    logs = log_sheet.get_all_records()
                    log_df = pd.DataFrame(logs)
                    log_df["日時"] = pd.to_datetime(log_df["日時"])
                    cutoff_date = datetime.now() - timedelta(days=30)
                    recent_logs = log_df[log_df["日時"] >= cutoff_date]
                    
                    usage_df = recent_logs[recent_logs["変動数"] < 0].copy()
                    usage_df["使用数"] = usage_df["変動数"].abs()
                    summary = usage_df.groupby("商品名")["使用数"].sum()
                    
                    items = sheet.col_values(1)[1:]
                    for i, item_name in enumerate(items):
                        row_num = i + 2
                        usage_amount = int(summary[item_name]) if item_name in summary else 0
                        sheet.update_cell(row_num, 5, usage_amount)
                    
                    st.success("集計完了！")
                    time.sleep(2)
                    st.rerun()
                except Exception as e:
                    st.error(f"集計エラー: {e}")
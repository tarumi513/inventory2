import streamlit as st
import pandas as pd
import gspread
from google.oauth2 import service_account
import time

# --- 認証の設定関数（ここは変更なし） ---
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
    
    # スプレッドシートを開く（名前は実際のシート名に合わせてください）
    # ※もしエラーが出る場合は、スプレッドシートのURLからキーで開く方法もあります
    try:
        sheet = client.open("inventory_data").sheet1 
        data = sheet.get_all_records()
        df = pd.DataFrame(data)
        return df, sheet
    except Exception as e:
        st.error(f"シートの読み込みエラー: {e}")
        return pd.DataFrame(), None

# --- アプリのメイン処理 ---
st.title("📦 在庫管理アプリ")

# データを読み込む
df, sheet = load_data()

# ---------------------------------------------------------
# 1. サイドバー（管理者ログイン設定）
# ---------------------------------------------------------
st.sidebar.title("メニュー")
is_admin = False # 最初は管理者ではない

# チェックボックスでログイン画面を出す
if st.sidebar.checkbox("管理者モード（商品追加・削除）"):
    password = st.sidebar.text_input("管理者パスワード", type="password")
    
    # Secretsに保存したパスワードと照合
    if password == st.secrets["admin_password"]:
        st.sidebar.success("✅ ログイン成功")
        is_admin = True
    elif password:
        st.sidebar.error("❌ パスワードが違います")

# ---------------------------------------------------------
# 2. メイン画面：在庫一覧（誰でも見れる）
# ---------------------------------------------------------
st.info("在庫数の変更は下のフォームから誰でも行えます。")
st.dataframe(df)

# ---------------------------------------------------------
# 3. 入出庫エリア（誰でも操作OK！）
# ---------------------------------------------------------
st.markdown("---")
st.subheader("📝 在庫数の更新（入庫・出庫）")

if not df.empty:
    with st.form(key='update_stock_form'):
        col1, col2 = st.columns(2)
        with col1:
            # 更新する商品を選ぶ
            target_name = st.selectbox("商品を選択", df["商品名"].unique())
        with col2:
            # 新しい個数を入力する
            new_quantity = st.number_input("現在の在庫数", min_value=0, step=1)

        update_btn = st.form_submit_button("在庫数を更新")

        if update_btn:
            try:
                # 商品名のセルを探す
                cell = sheet.find(target_name)
                # その行の2列目（個数）を書き換える
                sheet.update_cell(cell.row, 2, new_quantity)
                
                st.success(f"「{target_name}」の在庫を {new_quantity} 個に更新しました！")
                time.sleep(1)
                st.rerun() # 画面更新
            except Exception as e:
                st.error(f"更新エラー: {e}")
else:
    st.warning("データがありません。管理者が商品を追加してください。")


# ---------------------------------------------------------
# 4. 管理者専用エリア（パスワードが合った時だけ表示）
# ---------------------------------------------------------
if is_admin:
    st.markdown("---")
    st.markdown("### 🔧 管理者メニュー")
    
    # --- タブで機能を分ける ---
    tab1, tab2 = st.tabs(["商品の追加", "商品の削除"])

    # 【追加機能】
    with tab1:
        st.write("新しい商品をリストに追加します")
        with st.form(key='add_form'):
            name = st.text_input("新しい商品名")
            quantity = st.number_input("初期在庫数", min_value=0, step=1)
            submit_btn = st.form_submit_button("追加する")
            
            if submit_btn:
                if name and name not in df["商品名"].values:
                    sheet.append_row([name, quantity])
                    st.success(f"「{name}」を追加しました！")
                    time.sleep(1)
                    st.rerun()
                elif name in df["商品名"].values:
                    st.warning("その商品は既に存在します。")
                else:
                    st.warning("商品名を入力してください")

    # 【削除機能】
    with tab2:
        st.write("商品をリストから完全に削除します")
        delete_target = st.selectbox("削除する商品を選択", df["商品名"].unique(), key='del_select')
        
        if st.button("この商品を削除する"):
            try:
                cell = sheet.find(delete_target)
                sheet.delete_rows(cell.row)
                st.success(f"「{delete_target}」を削除しました")
                time.sleep(1)
                st.rerun()
            except Exception as e:
                st.error(f"削除エラー: {e}")
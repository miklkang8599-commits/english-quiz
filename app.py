# ==============================================================================
# 🧩 英文重組練習旗艦版 (English Sentence Scramble App)
# ==============================================================================
# 📌 版本編號 (VERSION): 1.7.9
# 📅 更新日期: 2026-03-08
#
# 📜 【GitHub 開發日誌 & 版本功能說明】
# ------------------------------------------------------------------------------
# V1.7.9 [2026-03-08]: 
#   - 修復選單空白問題：重寫下拉選單過濾邏輯，支援各種資料型態(文字/數值/小數)。
#   - 修正級聯選單連動：確保 年度->冊別->單元->課次 能夠正確遞進過濾。
# V1.7.8 [2026-03-08]: 
#   - 引入載入測驗確認機制，解決按鈕點擊導致範圍重置的 Bug。
# ==============================================================================

import streamlit as st
import pandas as pd
import random
import re
from datetime import datetime, timedelta
from streamlit_gsheets import GSheetsConnection

VERSION = "1.7.9"

st.set_page_config(page_title=f"英文重組 V{VERSION}", layout="centered")

# --- 1. 連線與資料讀取 ---
conn = st.connection("gsheets", type=GSheetsConnection)

@st.cache_data(ttl=300)
def load_all_data():
    try:
        df_q = conn.read(worksheet="questions")
        df_s = conn.read(worksheet="students")
        # 預處理：將關鍵欄位轉為數值，非數字轉為 NaN
        cols_to_fix = ['年度', '冊編號', '單元', '課編號', '句編號']
        for col in cols_to_fix:
            df_q[col] = pd.to_numeric(df_q[col], errors='coerce')
        # 移除關鍵欄位有空值的列
        df_q = df_q.dropna(subset=['年度', '冊編號', '單元', '課編號', '句編號', '英文'])
        return df_q, df_s
    except: return None, None

@st.cache_data(ttl=30)
def load_logs_data():
    try:
        df = conn.read(worksheet="logs")
        df['時間'] = pd.to_datetime(df['時間'])
        return df
    except: return None

# --- 2. 輔助函數 ---
def get_clean_list(df, col):
    """取得該欄位所有不重複且為整數的清單"""
    if df is None or df.empty: return []
    vals = df[col].dropna().unique()
    return sorted([int(x) for x in vals])

def log_event(action_type, detail="", result="-", duration=0):
    if not st.session_state.get('logged_in'): return
    try:
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        new_row = pd.DataFrame([{
            "時間": now, "帳號": st.session_state.user_id, "姓名": st.session_state.user_name,
            "分組": st.session_state.group_id, "題目ID": st.session_state.get('current_qid','-'), 
            "動作": action_type, "內容": detail, "結果": result, "費時": duration
        }])
        if action_type in ["作答", "登入", "登出"]:
            old_logs = conn.read(worksheet="logs", ttl=0)
            updated_logs = pd.concat([old_logs, new_row], ignore_index=True)
            conn.update(worksheet="logs", data=updated_logs)
            st.cache_data.clear()
    except: pass

def reset_quiz():
    st.session_state.q_idx = 0
    st.session_state.ans, st.session_state.used_history, st.session_state.shuf = [], [], []
    st.session_state.start_time = datetime.now()
    st.session_state.finished = False

# --- 3. 登入系統 ---
if 'logged_in' not in st.session_state: st.session_state.logged_in = False

if not st.session_state.logged_in:
    st.title("🧩 英文句子重組練習系統")
    st.write("---")
    col1, col2 = st.columns([1, 4])
    col1.markdown("### EA")
    input_id = col2.text_input("帳號 (4位數字)", max_chars=4)
    input_pw = st.text_input("密碼 (4位數字)", type="password", max_chars=4)
    if st.button("🚀 確認登入", type="primary", use_container_width=True):
        _, df_s = load_all_data()
        if df_s is not None:
            df_s['帳號_c'] = df_s['帳號'].astype(str).str.split('.').str[0].str.strip().str.zfill(4)
            df_s['密碼_c'] = df_s['密碼'].astype(str).str.split('.').str[0].str.strip().str.zfill(4)
            user = df_s[df_s['帳號_c'] == str(input_id).strip().zfill(4)]
            if not user.empty and str(user.iloc[0]['密碼_c']) == str(input_pw).strip().zfill(4):
                st.session_state.logged_in = True
                st.session_state.user_id = f"EA{input_id.zfill(4)}"
                st.session_state.user_name = user.iloc[0]['姓名']
                st.session_state.group_id = user.iloc[0]['分組']
                log_event("登入")
                st.rerun()
            else: st.error("❌ 帳密錯誤")
    st.stop()

# --- 4. 主畫面 ---
st.title("🧩 英文句子重組練習")

# CSS
st.markdown("""
    <style>
    @keyframes marquee { 0% { transform: translateX(100%); } 100% { transform: translateX(-100%); } }
    .marquee-container { background: #333; color: #00ff00; padding: 5px 0; overflow: hidden; white-space: nowrap; margin-bottom:10px; border-radius:5px; }
    .marquee-text { display: inline-block; animation: marquee 25s linear infinite; font-size: 16px; }
    .hint-box { background-color: #f8f9fa; padding: 15px 20px; border-radius: 10px; border-left: 6px solid #1e88e5; font-size: 18px; margin-bottom: 10px; }
    .q-meta { color: #1e88e5; font-size: 15px; font-weight: bold; }
    .answer-display { background-color: #ffffff; padding: 15px; border-radius: 10px; border: 1px solid #dee2e6; min-height: 70px; display: flex; flex-wrap: wrap; gap: 8px; align-items: center; justify-content: center; font-size: 20px; margin-bottom: 10px; }
    </style>
""", unsafe_allow_html=True)

# 跑馬燈
logs_df = load_logs_data()
if logs_df is not None:
    recent = logs_df[logs_df['結果'] == '✅'].tail(3)
    m_text = " | ".join([f"🔥 {r['姓名']}({r['分組']}) 答對了!" for _, r in recent.iterrows()])
    if m_text: st.markdown(f'<div class="marquee-container"><div class="marquee-text">{m_text}</div></div>', unsafe_allow_html=True)

df_q, _ = load_all_data()

# 側邊欄
with st.sidebar:
    st.title(f"👋 {st.session_state.user_name}")
    if st.button("🚪 登出"): log_event("登出"); st.session_state.logged_in = False; st.rerun()
    st.divider()
    if logs_df is not None:
        st.subheader("📊 同組即時動態")
        ten_mins_ago = datetime.now() - timedelta(minutes=10)
        group_data = logs_df[logs_df['分組'] == st.session_state.group_id]
        online_users = group_data[group_data['時間'] > ten_mins_ago]['姓名'].unique()
        st.write("🟢 在線：" + (", ".join(online_users) if len(online_users) > 0 else "僅您"))
        recent_2 = group_data[group_data['動作'] == '作答'].sort_values('時間', ascending=False).head(2)
        for _, row in recent_2.iterrows():
            st.info(f"👤 {row['姓名']} | 題: {row['題目ID']}")

# --- 5. 範圍與連動選單 ---
if df_q is not None:
    # 如果還沒載入測驗，或展開設定區
    with st.expander("⚙️ 範圍與題數設定", expanded=not st.session_state.get('quiz_loaded', False)):
        c1, c2, c3, c4 = st.columns(4)
        
        # 1. 年度
        y_list = get_clean_list(df_q, '年度')
        sel_y = c1.selectbox("年度", y_list)
        df_f1 = df_q[df_q['年度'] == sel_y]
        
        # 2. 冊別 (連動年度)
        b_list = get_clean_list(df_f1, '冊編號')
        sel_b = c2.selectbox("冊別", b_list)
        df_f2 = df_f1[df_f1['冊編號'] == sel_b]
        
        # 3. 單元 (連動冊別)
        u_list = get_clean_list(df_f2, '單元')
        sel_u = c3.selectbox("單元", u_list)
        df_f3 = df_f2[df_f2['單元'] == sel_u]
        
        # 4. 課次 (連動單元)
        l_list = get_clean_list(df_f3, '課編號')
        sel_l = c4.selectbox("課次", l_list)
        
        # 最終過濾出的題目底稿
        base_df = df_f3[df_f3['課編號'] == sel_l].sort_values('句編號')
        
        if not base_df.empty:
            s1, s2 = st.columns([1, 1])
            start_id = s1.number_input("起始句編號", int(base_df['句編號'].min()), int(base_df['句編號'].max()), step=1)
            
            # 題數控制 (用臨時 session 儲存)
            if 'num_q_tmp' not in st.session_state: st.session_state.num_q_tmp = 10
            sc1, sc2, sc3 = s2.columns([1, 2, 1])
            if sc1.button("➖"): st.session_state.num_q_tmp = max(1, st.session_state.num_q_tmp - 1)
            sc2.markdown(f"<h5 style='text-align: center;'>題數: {st.session_state.num_q_tmp}</h5>", unsafe_allow_html=True)
            if sc3.button("➕"): st.session_state.num_q_tmp += 1
            
            if st.button("🚀 載入測驗", type="primary", use_container_width=True):
                st.session_state.quiz_list = base_df[base_df['句編號'] >= start_id].head(st.session_state.num_q_tmp).to_dict('records')
                st.session_state.quiz_loaded = True
                reset_quiz()
                st.rerun()

    # 題目主畫面
    if st.session_state.get('quiz_loaded') and not st.session_state.get('finished'):
        quiz_list = st.session_state.quiz_list
        if st.session_state.q_idx < len(quiz_list):
            q = quiz_list[st.session_state.q_idx]
            st.session_state.current_qid = f"{int(q['年度'])}_{int(q['冊編號'])}_{int(q['課編號'])}_{int(q['句編號'])}"
            
            st.markdown(f'<div class="hint-box"><span class="q-meta">題號 {st.session_state.q_idx + 1} (句編號 {int(q["句編號"])})</span><br>{q["中文"]}</div>', unsafe_allow_html=True)
            st.markdown(f'<div class="answer-display">{" ".join(st.session_state.ans) if st.session_state.ans else "......"}</div>', unsafe_allow_html=True)

            nav = st.columns(4)
            if nav[0].button("退回"):
                if st.session_state.ans: st.session_state.ans.pop(); st.session_state.used_history.pop(); st.rerun()
            if nav[1].button("重填"): st.session_state.ans, st.session_state.used_history = [], []; st.rerun()
            if nav[2].button("上一題", disabled=(st.session_state.q_idx == 0)):
                st.session_state.q_idx -= 1; st.session_state.ans, st.session_state.used_history, st.session_state.shuf = [], [], []; st.rerun()
            if nav[3].button("下一題"):
                if st.session_state.q_idx + 1 < len(quiz_list):
                    st.session_state.q_idx += 1; st.session_state.ans, st.session_state.used_history, st.session_state.shuf = [], [], []; st.rerun()
                else: st.session_state.finished = True; st.rerun()

            tokens = re.findall(r"[\w']+|[^\w\s]", str(q['英文']).strip())
            if not st.session_state.shuf: st.session_state.shuf = tokens.copy(); random.shuffle(st.session_state.shuf)

            st.write("---")
            btn_cols = st.columns(2)
            for idx, token in enumerate(st.session_state.shuf):
                if idx not in st.session_state.used_history:
                    with btn_cols[idx % 2]:
                        if st.button(token, key=f"t_{idx}", use_container_width=True):
                            st.session_state.ans.append(token); st.session_state.used_history.append(idx); st.rerun()

            if len(st.session_state.ans) == len(tokens):
                if st.button("✅ 檢查答案", type="primary", use_container_width=True):
                    dur = (datetime.now() - st.session_state.start_time).seconds
                    is_ok = "".join(st.session_state.ans).lower() == str(q['英文']).strip().replace(" ", "").lower()
                    log_event("作答", detail=" ".join(st.session_state.ans), result="✅" if is_ok else "❌", duration=dur)
                    if is_ok: st.success("Correct!"); st.balloons()
                    else: st.error(f"錯誤！答案是: {q['英文']}")
                    st.session_state.start_time = datetime.now()

    elif st.session_state.get('finished'):
        st.success("🎊 您已完成本次所有練習。")
        if st.button("🔄 重新載入設定"):
            st.session_state.quiz_loaded = False
            st.session_state.finished = False
            st.rerun()

st.caption(f"Final Fix Ver {VERSION}")

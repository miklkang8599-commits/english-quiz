# ==============================================================================
# 🧩 英文全能練習系統 (V2.7.6 同組看板強化版)
# ==============================================================================
# 📌 版本編號 (VERSION): 2.7.6
# 📅 更新日期: 2026-03-08
#
# 📜 【GitHub 開發日誌】
# ------------------------------------------------------------------------------
# V2.7.6 [2026-03-08]: 
#   - 側邊欄新增「同組進度看板」：統計組員今日累計答對題數。
#   - 增加活動捲動框：顯示組員最新的 5 筆作答細節。
#   - 優化 ADMIN 模式下的側邊欄顯示，確保資訊隔離。
# ==============================================================================

import streamlit as st
import pandas as pd
import random
import re
import time
from datetime import datetime
from streamlit_gsheets import GSheetsConnection

VERSION = "2.7.6"
IDLE_TIMEOUT = 300 

st.set_page_config(page_title=f"英文練習系統 V{VERSION}", layout="wide")

# --- 1. 資料處理核心 ---
conn = st.connection("gsheets", type=GSheetsConnection)

@st.cache_data(ttl=60)
def load_static_data():
    try:
        df_q = conn.read(worksheet="questions")
        df_s = conn.read(worksheet="students")
        if df_q is not None:
            df_q = df_q.fillna("").astype(str).replace(r'\.0$', '', regex=True)
        return df_q, df_s
    except: return None, None

def load_dynamic_data():
    try:
        df_a = conn.read(worksheet="assignments", ttl=5)
        df_l = conn.read(worksheet="logs", ttl=5)
        if df_l is not None and not df_l.empty:
            df_l['時間'] = pd.to_datetime(df_l['時間'], errors='coerce')
        return df_a, df_l
    except: return None, None

def log_event_fast(action_type, detail="", result="-"):
    now_ts = time.time()
    start_ts = st.session_state.get('start_time_ts', now_ts)
    duration = max(0.1, round(now_ts - start_ts, 1))
    st.session_state.pending_log = {
        "時間": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "帳號": st.session_state.user_id, "姓名": st.session_state.user_name,
        "分組": st.session_state.group_id, "題目ID": st.session_state.get('current_qid','-'), 
        "動作": action_type, "內容": detail, "結果": result, "費時": duration
    }

def flush_pending_log():
    if st.session_state.get('pending_log'):
        try:
            old_logs = conn.read(worksheet="logs", ttl=0)
            new_row = pd.DataFrame([st.session_state.pending_log])
            updated_logs = pd.concat([old_logs, new_row], ignore_index=True)
            conn.update(worksheet="logs", data=updated_logs)
            st.session_state.pending_log = None
            st.cache_data.clear() 
        except: pass

# --- 2. 登入邏輯 (略) ---
if 'logged_in' not in st.session_state: st.session_state.logged_in = False
if 'view_mode' not in st.session_state: st.session_state.view_mode = "管理後台"

if not st.session_state.logged_in:
    df_q, df_s = load_static_data()
    _, c_login, _ = st.columns([1, 1.2, 1])
    with c_login:
        st.title("🧩 系統登入")
        input_id = st.text_input("帳號 (後四碼)")
        input_pw = st.text_input("密碼", type="password")
        if st.button("🚀 登入", use_container_width=True):
            if df_s is not None:
                df_s['帳號_c'] = df_s['帳號'].astype(str).str.split('.').str[0].str.zfill(4)
                user = df_s[df_s['帳號_c'] == input_id.strip().zfill(4)]
                if not user.empty and str(user.iloc[0]['密碼']).split('.')[0] == input_pw.strip():
                    st.session_state.update({
                        "logged_in": True, "user_id": f"EA{input_id.zfill(4)}",
                        "user_name": user.iloc[0]['姓名'], "group_id": user.iloc[0]['分組'],
                        "last_activity": time.time()
                    })
                    st.rerun()
    st.stop()

# --- 3. 樣式載入 ---
df_q, df_s = load_static_data()
df_a, df_l = load_dynamic_data()

st.markdown("""<style>
    .sidebar-scroll { max-height: 300px; overflow-y: auto; background: #fdfdfd; border: 1px solid #eee; padding: 10px; border-radius: 8px; margin-bottom: 15px; }
    .leaderboard-item { display: flex; justify-content: space-between; padding: 5px 0; border-bottom: 1px solid #f0f0f0; font-size: 14px; }
    .status-on { color: #28a745; font-size: 12px; }
    .status-off { color: #ccc; font-size: 12px; }
</style>""", unsafe_allow_html=True)

# --- 4. 側邊欄：同組即時看板 ---
with st.sidebar:
    st.title(f"👋 {st.session_state.user_name}")
    if st.session_state.group_id == "ADMIN":
        st.session_state.view_mode = st.radio("模式：", ["管理後台", "練習模式"])
    if st.button("🚪 登出", use_container_width=True):
        st.session_state.logged_in = False; st.rerun()
    
    st.divider()
    
    if df_l is not None and not df_l.empty:
        st.subheader("🏆 同組今日看板")
        # 篩選同組組員 (不含 ADMIN)
        my_group = st.session_state.group_id
        gl = df_l[df_l['分組'] == my_group].copy()
        
        # 今日時間過濾
        today_str = datetime.now().strftime("%Y-%m-%d")
        gl_today = gl[gl['時間'].dt.strftime("%Y-%m-%d") == today_str]
        
        # 1. 組員排行榜 (捲動框)
        st.markdown('<div class="sidebar-scroll">', unsafe_allow_html=True)
        group_members = df_s[df_s['分組'] == my_group]['姓名'].tolist()
        
        for member in sorted(group_members):
            m_logs = gl_today[gl_today['姓名'] == member]
            correct_count = len(m_logs[m_logs['結果'] == '✅'])
            
            # 判斷是否在線 (10分鐘內)
            is_online = not gl[gl['姓名'] == member].empty and (gl[gl['姓名'] == member].iloc[-1]['時間'] > (datetime.now() - pd.Timedelta(minutes=10)))
            status_icon = "🟢" if is_online else "⚪"
            
            st.markdown(f'''<div class="leaderboard-item">
                <span>{status_icon} {member}</span>
                <span style="font-weight:bold; color:#007bff;">{correct_count} 題</span>
            </div>''', unsafe_allow_html=True)
        st.markdown('</div>', unsafe_allow_html=True)
        
        # 2. 最近動態 (捲動框)
        st.subheader("🕒 組員最新活動")
        st.markdown('<div class="sidebar-scroll" style="max-height:150px;">', unsafe_allow_html=True)
        recent_group_act = gl[gl['動作'].str.contains('單選|重組', na=False)].head(10)
        for _, r in recent_group_act.iterrows():
            icon = "✅" if r['結果'] == "✅" else "❌"
            qid_part = str(r['題目ID']).split('_')[-1]
            st.markdown(f'<div style="font-size:12px; margin-bottom:4px;">👤 {r["姓名"]}: {icon} (句:{qid_part})</div>', unsafe_allow_html=True)
        st.markdown('</div>', unsafe_allow_html=True)

# --- 5. 導師管理中心 (略，同 V2.7.5) ---
if st.session_state.group_id == "ADMIN" and st.session_state.view_mode == "管理後台":
    st.title("👨‍🏫 導師管理中心")
    # ... (此處保留老師後台完整代碼)
    st.stop()

# --- 6. 學生練習介面 ---
st.title("🚀 英文全能練習")

# [任務偵測、手動設定、練習邏輯、個人紀錄 同 V2.7.5]
# (此處為節省空間簡寫，實際上程式碼會包含所有練習邏輯與 flush_pending_log)

# 重申關鍵：flush_pending_log() 必須在「下一題」按鈕內呼叫
# 學生手動設定與練習區 (維持 V2.7.5 穩定代碼)...
# [由於長度限制，此處僅標註邏輯出口，實際覆蓋請務必包含 V2.7.5 的完整內容]

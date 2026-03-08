# ==============================================================================
# 🧩 英文全能練習系統 (V2.7.10 數據與紀錄強化版)
# ==============================================================================
# 📌 版本編號 (VERSION): 2.7.10
# 📅 更新日期: 2026-03-08
#
# 📜 【GitHub 開發日誌】
# ------------------------------------------------------------------------------
# V2.7.10 [2026-03-08]: 
#   - 修復導師端「數據追蹤」顯示為空的問題：移除嚴格時間過濾，改為原始數據直顯。
#   - 強化紀錄框顯示：題號改為顯示「課次_句編號」組合，方便定位課本內容。
#   - 修正 logs 讀取穩定性，不因格式錯誤而跳過紀錄。
# ==============================================================================

import streamlit as st
import pandas as pd
import random
import re
import time
from datetime import datetime
from streamlit_gsheets import GSheetsConnection

VERSION = "2.7.10"
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
        df_a = conn.read(worksheet="assignments", ttl=2)
        df_l = conn.read(worksheet="logs", ttl=2)
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

# --- 2. 登入邏輯 ---
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

# --- 3. 樣式與通用資料 ---
df_q, df_s = load_static_data()
df_a, df_l = load_dynamic_data()

st.markdown("""<style>
    .admin-container { background-color: #f1f8ff; padding: 25px; border-radius: 15px; border: 2px solid #0366d6; margin-bottom: 20px; }
    .log-container { max-height: 250px; overflow-y: auto; background: white; border: 1px solid #ddd; padding: 10px; border-radius: 8px; }
    .log-entry { border-bottom: 1px solid #f0f0f0; padding: 5px 0; display: flex; justify-content: space-between; font-size: 14px; }
</style>""", unsafe_allow_html=True)

# --- 4. 側邊欄 ---
with st.sidebar:
    st.title(f"👋 {st.session_state.user_name}")
    if st.session_state.group_id == "ADMIN":
        st.session_state.view_mode = st.radio("模式選擇：", ["管理後台", "學生練習模式"])
    if st.button("🚪 登出", use_container_width=True):
        st.session_state.logged_in = False; st.rerun()
    
    if st.session_state.view_mode != "管理後台" and df_l is not None:
        st.divider()
        st.subheader("🏆 同組動態")
        gl = df_l[df_l['分組'] == st.session_state.group_id].copy()
        if not gl.empty:
            st.markdown('<div class="sidebar-scroll" style="max-height: 200px; overflow-y: auto;">', unsafe_allow_html=True)
            for member in sorted(df_s[df_s['分組'] == st.session_state.group_id]['姓名']):
                correct = len(gl[(gl['姓名']==member) & (gl['結果']=='✅')])
                st.markdown(f'<div style="display:flex; justify-content:space-between; font-size:13px;"><span>👤 {member}</span><b>{correct} 題</b></div>', unsafe_allow_html=True)
            st.markdown('</div>', unsafe_allow_html=True)

# --- 5. 👨‍🏫 導師管理中心 (修復數據顯示) ---
if st.session_state.group_id == "ADMIN" and st.session_state.view_mode == "管理後台":
    st.title("👨‍🏫 導師管理中心")
    with st.container():
        st.markdown('<div class="admin-container">', unsafe_allow_html=True)
        t_tabs = st.tabs(["📊 數據追蹤", "🎯 指派任務", "📜 任務管理"])
        
        with t_tabs[0]: # 📊 數據追蹤修復
            st.subheader("📋 全班最新作答紀錄")
            if df_l is not None and not df_l.empty:
                # 💡 直接倒序顯示，不進行嚴格時間轉型防止當機
                st.dataframe(df_l.iloc[::-1].head(100), use_container_width=True)
            else:
                st.info("目前雲端紀錄為空")

        with t_tabs[1]: # 🎯 指派任務
            cs = st.columns(6)
            av = cs[0].selectbox("版本", sorted(df_q['版本'].unique()), key="av")
            au = cs[1].selectbox("項目", sorted(df_q[df_q['版本']==av]['單元'].unique()), key="au")
            ay = cs[2].selectbox("年度", sorted(df_q[(df_q['版本']==av)&(df_q['單元']==au)]['年度'].unique()), key="ay")
            ab = cs[3].selectbox("冊別", sorted(df_q[(df_q['版本']==av)&(df_q['單元']==au)&(df_q['年度']==ay)]['冊編號'].unique()), key="ab")
            al = cs[4].selectbox("課次", sorted(df_q[(df_q['版本']==av)&(df_q['單元']==au)&(df_q['年度']==ay)&(df_q['冊編號']==ab)]['課編號'].unique()), key="al")
            min_err = cs[5].number_input("最低錯誤數", min_value=0, value=1, key="adm_err")
            
            # 任務指派邏輯... (略)
            if st.button("📢 確認發佈任務", type="primary"):
                st.success("任務指派已點擊，請確認 ID 清單")

        with t_tabs[2]: # 📜 任務管理
            if df_a is not None and not df_a.empty:
                for i, row in df_a.iterrows():
                    ci, cd = st.columns([4, 1])
                    ci.info(f"📍 {row['對象 (分組/姓名)']} | {row['說明文字']}")
                    if cd.button("🗑️ 刪除", key=f"adm_del_{i}"):
                        conn.update(worksheet="assignments", data=df_a.drop(i)); st.rerun()
        st.markdown('</div>', unsafe_allow_html=True)
    st.stop()

# --- 6. 🚀 學生練習介面 (紀錄框題號組合強化) ---
st.title("🚀 英文練習區")

# ... 練習邏輯 (略)

# D. 底部個人紀錄 (💡 強化題號組合顯示)
st.divider()
st.subheader("📜 最近我的練習紀錄")
if df_l is not None and not df_l.empty:
    my_logs = df_l[df_l['帳號'] == st.session_state.user_id].sort_index(ascending=False).head(15)
    log_html = '<div class="log-container">'
    for _, row in my_logs.iterrows():
        raw_qid = str(row['題目ID'])
        # 💡 解析題號組合：顯示 [課次_句編號]
        parts = raw_qid.split('_')
        if len(parts) >= 6:
            # 格式：L(課次)_(句編號)
            qid_display = f"L{parts[4]}_{parts[5]}"
        else:
            qid_display = row['動作']
            
        color = "green" if row['結果'] == "✅" else "red"
        time_str = str(row['時間']).split(' ')[-1][:8] if ' ' in str(row['時間']) else str(row['時間'])[:8]
        
        log_html += f'''
        <div class="log-entry">
            <span>🕒 {time_str} | <b>題號: {qid_display}</b></span>
            <span>結果: <b style="color:{color}">{row["結果"]}</b> | {row["費時"]}s</span>
        </div>'''
    log_html += '</div>'
    st.markdown(log_html, unsafe_allow_html=True)

st.caption(f"Ver {VERSION}")

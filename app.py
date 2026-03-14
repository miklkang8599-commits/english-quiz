# ==============================================================================
# 🧩 英文全能練習系統 (V2.8.80 - 雙端版號全域同步版)
# ==============================================================================
# 📌 版本編號 (VERSION): 2.8.80
# 📅 更新日期: 2026-03-14
# 🛠️ 修復重點：確保老師端、學生端、登入端均能常駐看見版本編號與台灣時間標註。
# ==============================================================================

import streamlit as st
import pandas as pd
import random
import re
import time
from datetime import datetime, timedelta
from streamlit_gsheets import GSheetsConnection

VERSION = "2.8.80"

# ------------------------------------------------------------------------------
# 📦 【盒子 A：系統核心 (時區與基礎邏輯)】
# ------------------------------------------------------------------------------
def get_now():
    return datetime.utcnow() + timedelta(hours=8)

def standardize(v):
    val = str(v).split('.')[0].strip()
    return val.zfill(4) if val.isdigit() else val

def clean_string_for_compare(s):
    s = s.lower().replace(" ", "").replace("’", "'").replace("‘", "'")
    s = re.sub(r'[.,?!:;()]', '', s) 
    return s.strip()

# 全域版號顯示函式
def show_version_caption():
    st.caption(f"🚀 系統版本：Ver {VERSION} | 🌍 台灣時間鎖定 (GMT+8)")

st.session_state.setdefault('range_confirmed', False)
st.session_state.setdefault('quiz_loaded', False)
st.session_state.setdefault('ans', [])
st.session_state.setdefault('used_history', [])
st.session_state.setdefault('show_analysis', False)

conn = st.connection("gsheets", type=GSheetsConnection)

@st.cache_data(ttl=60)
def load_static_data():
    try:
        df_q = conn.read(worksheet="questions").fillna("").astype(str).replace(r'\.0$', '', regex=True)
        df_s = conn.read(worksheet="students").fillna("").astype(str).replace(r'\.0$', '', regex=True)
        return df_q, df_s
    except: return None, None

def load_dynamic_data():
    try:
        df_a = conn.read(worksheet="assignments", ttl=10)
        df_l = conn.read(worksheet="logs", ttl=10)
        return df_a, df_l
    except: return pd.DataFrame(), pd.DataFrame()

# ------------------------------------------------------------------------------
# 🔐 【權限控管：登入端版號顯示】
# ------------------------------------------------------------------------------
st.set_page_config(page_title=f"英文練習系統 V{VERSION}", layout="wide")

if not st.session_state.get('logged_in', False):
    df_q, df_s = load_static_data()
    _, c, _ = st.columns([1, 1.2, 1])
    with c:
        st.markdown("### 🔵 系統登入")
        i_id = st.text_input("帳號", key="l_id")
        i_pw = st.text_input("密碼", type="password", key="l_pw")
        if st.button("🚀 登入", use_container_width=True):
            if df_s is not None:
                std_id, std_pw = standardize(i_id), standardize(i_pw)
                df_s['c_id'], df_s['c_pw'] = df_s['帳號'].apply(standardize), df_s['密碼'].apply(standardize)
                user = df_s[df_s['c_id'] == std_id]
                if not user.empty and user.iloc[0]['c_pw'] == std_pw:
                    st.session_state.clear()
                    st.session_state.update({
                        "logged_in": True, "user_id": f"EA{std_id}", "user_name": user.iloc[0]['姓名'], 
                        "group_id": user.iloc[0]['分組'], "view_mode": "管理後台" if user.iloc[0]['分組']=="ADMIN" else "練習模式"
                    })
                    st.rerun()
        show_version_caption() # 💡 登入畫面也顯示
    st.stop()

df_q, df_s = load_static_data()
df_a, df_l = load_dynamic_data()

# ------------------------------------------------------------------------------
# 📦 【盒子 E：側邊排行 (側邊欄版號顯示)】
# ------------------------------------------------------------------------------
with st.sidebar:
    st.write(f"👤 {st.session_state.user_name} ({st.session_state.group_id})")
    if st.session_state.group_id == "ADMIN":
        st.session_state.view_mode = st.radio("功能切換：", ["管理後台", "進入練習"])
    if st.button("🚪 登出系統"):
        st.session_state.clear(); st.rerun()
    
    st.divider()
    st.markdown("🏆 **今日成就排行**")
    if not df_l.empty:
        today_str = get_now().strftime("%Y-%m-%d")
        gl = df_l[(df_l['分組'] == st.session_state.group_id) & (df_l['時間'].str.startswith(today_str))].copy()
        for m in sorted(df_s[df_s['分組'] == st.session_state.group_id]['姓名'].tolist()):
            c_cnt = len(gl[(gl['姓名']==m) & (gl['結果']=='✅')])
            st.markdown(f'<div style="font-size:12px;">👤 {m}: {c_cnt} 題</div>', unsafe_allow_html=True)
    
    st.write("")
    st.caption(f"Ver {VERSION}") # 💡 側邊欄底部小版號

# ------------------------------------------------------------------------------
# 📦 【盒子 B：導師中心 (後台端版號顯示)】
# ------------------------------------------------------------------------------
if st.session_state.group_id == "ADMIN" and st.session_state.view_mode == "管理後台":
    st.markdown("## 🟢 導師中心 (盒子 B)")
    t1, t2 = st.tabs(["📋 指派任務", "📈 數據監控"])
    # ... (管理功能邏輯)
    with t2:
        if not df_l.empty: st.dataframe(df_l.sort_values("時間", ascending=False), use_container_width=True)
    
    show_version_caption() # 💡 導師後台底部顯示
    st.stop()

# ------------------------------------------------------------------------------
# 📦 【盒子 C：練習範圍設定】 (設定端版號顯示)
# ------------------------------------------------------------------------------
if not st.session_state.quiz_loaded:
    st.markdown("## 🟡 練習範圍設定 (盒子 C)")
    with st.expander("⚙️ 篩選題目範圍", expanded=not st.session_state.range_confirmed):
        # ... (篩選代碼)
        c_s = st.columns(5)
        sv = c_s[0].selectbox("版本", sorted(df_q['版本'].unique()), key="s_v")
        su = c_s[1].selectbox("單元", sorted(df_q[df_q['版本']==sv]['單元'].unique()), key="s_u")
        sy = c_s[2].selectbox("年度", sorted(df_q[(df_q['版本']==sv)&(df_q['單元']==su)]['年度'].unique()), key="s_y")
        sb = c_s[3].selectbox("冊別", sorted(df_q[(df_q['版本']==sv)&(df_q['單元']==su)&(df_q['年度']==sy)]['冊編號'].unique()), key="s_b")
        sl = c_s[4].selectbox("課次", sorted(df_q[(df_q['版本']==sv)&(df_q['單元']==su)&(df_q['年度']==sy)&(df_q['冊編號']==sb)]['課編號'].unique()), key="s_l")
        if st.button("🔍 確認篩選", use_container_width=True): st.session_state.range_confirmed = True; st.rerun()
    
    if st.session_state.range_confirmed:
        # ... (模式選擇代碼)
        st.success("📊 準備就緒")
        if st.button("🚀 開始練習", type="primary", use_container_width=True):
            # ... (啟動邏輯)
            st.session_state.update({"quiz_loaded": True, "q_idx": 0, "ans": [], "used_history": []}) # 簡化演示
            st.rerun()
    
    show_version_caption() # 💡 學生設定畫面底部顯示

# ------------------------------------------------------------------------------
# 📦 【盒子 D：練習引擎 (引擎端版號顯示)】
# ------------------------------------------------------------------------------
if st.session_state.quiz_loaded:
    st.markdown(f"### 🔴 練習中 (第 {st.session_state.q_idx + 1} 題)")
    # ... (練習核心代碼)
    
    st.divider()
    if st.button("🏁 🔴 結束作答", use_container_width=True):
        st.session_state.update({"quiz_loaded": False, "range_confirmed": False}); st.rerun()
    
    show_version_caption() # 💡 學生練習畫面底部顯示

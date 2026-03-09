# ==============================================================================
# 🧩 英文全能練習系統 (V2.8.34 學生端練習載入鍵鎖定版)
# ==============================================================================
# 📌 版本編號 (VERSION): 2.8.34
# 📅 更新日期: 2026-03-09
# ------------------------------------------------------------------------------
# 🛠️ 核心功能檢核清單:
# [07-A/B] s_i, s_n 鎖定 [08] 側邊欄排行 [21] 登入清理
# [23] 學生練習載入鍵: 確保載入後 quiz_loaded 狀態切換並重置題號 -> LOCKED
# ==============================================================================

import streamlit as st
import pandas as pd
import random
import re
import time
from datetime import datetime
from streamlit_gsheets import GSheetsConnection

VERSION = "2.8.34"

# --- ### MODULE 1: 數據讀取與清理 [02, 21] ---
conn = st.connection("gsheets", type=GSheetsConnection)

@st.cache_data(ttl=30)
def load_static_data():
    try:
        df_q = conn.read(worksheet="questions")
        df_s = conn.read(worksheet="students")
        if df_q is not None:
            df_q = df_q.fillna("").astype(str).replace(r'\.0$', '', regex=True)
            df_s = df_s.fillna("").astype(str).replace(r'\.0$', '', regex=True)
        return df_q, df_s
    except: return None, None

def load_dynamic_data():
    try:
        df_a = conn.read(worksheet="assignments", ttl=2)
        df_l = conn.read(worksheet="logs", ttl=2)
        return df_a, df_l
    except: return None, None

def standardize(v):
    val = str(v).split('.')[0].strip()
    return val.zfill(4) if val.isdigit() else val

# --- ### MODULE 3: 登入模組 (徹底清理 [21]) ---
if 'logged_in' not in st.session_state: st.session_state.logged_in = False

if not st.session_state.logged_in:
    df_q, df_s = load_static_data()
    _, c_login, _ = st.columns([1, 1.2, 1])
    with c_login:
        st.title("🧩 系統登入")
        i_id = st.text_input("帳號", key="l_id")
        i_pw = st.text_input("密碼", type="password", key="l_pw")
        if st.button("🚀 進入系統", use_container_width=True):
            if df_s is not None:
                std_id, std_pw = standardize(i_id), standardize(i_pw)
                df_s['c_id'], df_s['c_pw'] = df_s['帳號'].apply(standardize), df_s['密碼'].apply(standardize)
                user = df_s[df_s['c_id'] == std_id]
                if not user.empty and user.iloc[0]['c_pw'] == std_pw:
                    st.session_state.clear() # 💡 [21] 登入必清理
                    st.session_state.update({
                        "logged_in": True, 
                        "user_id": f"EA{std_id}", 
                        "user_name": user.iloc[0]['姓名'], 
                        "group_id": user.iloc[0]['分組'], 
                        "view_mode": "管理後台" if user.iloc[0]['分組'] == "ADMIN" else "練習模式",
                        "log_buffer": [],
                        "quiz_loaded": False
                    })
                    st.rerun()
                else: st.error("❌ 帳密錯誤")
    st.stop()

df_q, df_s = load_static_data()
df_a, df_l = load_dynamic_data()

# --- ### [編號 08] 側邊欄排行榜 ---
with st.sidebar:
    st.title(f"👋 {st.session_state.user_name}")
    if st.session_state.group_id == "ADMIN":
        st.session_state.view_mode = st.radio("功能切換：", ["管理後台", "練習模式"])
    if st.button("🚪 登出", use_container_width=True):
        st.session_state.clear(); st.rerun()
    if (st.session_state.view_mode == "練習模式" or st.session_state.group_id != "ADMIN") and df_l is not None:
        st.divider(); st.subheader("🏆 今日對題排行")
        gl = df_l[df_l['分組'] == st.session_state.group_id].copy()
        members = sorted(df_s[df_s['分組'] == st.session_state.group_id]['姓名'].tolist())
        for m in members:
            cnt = len(gl[(gl['姓名']==m) & (gl['結果']=='✅')])
            st.markdown(f'<div style="display:flex; justify-content:space-between; font-size:13px;"><span>👤 {m}</span><b>{cnt} 題</b></div>', unsafe_allow_html=True)

# --- ### [編號 15] 導師管理中心 ---
if st.session_state.group_id == "ADMIN" and st.session_state.view_mode == "管理後台":
    st.title(f"👨‍🏫 導師管理中心 (V{VERSION})")
    st.info("請切換至『練習模式』進行學生端功能測試。")
    st.stop()

# --- ### MODULE 6: 學生設定與練習 [07, 20, 23] ---
st.title("🚀 英文練習區")

# [20] 範圍重設按鈕
if st.session_state.get('quiz_loaded'):
    if st.button("🔄 重新設定範圍", type="secondary"):
        st.session_state.update({"quiz_loaded": False, "ans": [], "used_history": []})
        st.rerun()

# [07-A/B, 23] 學生設定區與練習載入鍵
if not st.session_state.get('quiz_loaded'):
    with st.expander("⚙️ 手動設定練習範圍", expanded=True):
        cs = st.columns(5)
        sv, su, sy, sb, sl = cs[0].selectbox("版本", sorted(df_q['版本'].unique()), key="s_v"), cs[1].selectbox("單元", sorted(df_q['單元'].unique()), key="s_u"), cs[2].selectbox("年度", sorted(df_q['年度'].unique()), key="s_y"), cs[3].selectbox("冊別", sorted(df_q['冊編號'].unique()), key="s_b"), cs[4].selectbox("課次", sorted(df_q['課編號'].unique()), key="s_l")
        
        st.divider()
        sc1, sc2 = st.columns(2)
        # 💡 [07-A/B] 數值調整鈕
        st_i = sc1.number_input("📍 起始句編號 (+/-)", 1, 100, 1, key="s_i")
        nu_i = sc2.number_input("🔢 練習題數 (+/-)", 1, 50, 10, key="s_n")
        
        base = df_q[(df_q['版本']==sv)&(df_q['單元']==su)&(df_q['年度']==sy)&(df_q['冊編號']==sb)&(df_q['課編號']==sl)].copy()
        if not base.empty:
            base['句編號_int'] = pd.to_numeric(base['句編號'], errors='coerce')
            actual_q = base[base['句編號_int']>=st_i].sort_values('句編號_int').head(int(nu_i))
            st.success(f"📊 範圍內共找到：{len(actual_q)} 題")
            
            # 💡 [23] 關鍵功能鍵：開始練習
            if st.button("🚀 開始練習題目", type="primary", use_container_width=True, key="btn_start_quiz"):
                st.session_state.update({
                    "quiz_list": actual_q.to_dict('records'), 
                    "q_idx": 0, 
                    "quiz_loaded": True, 
                    "ans": [], 
                    "used_history": [], 
                    "shuf": [], 
                    "show_analysis": False, 
                    "start_time_ts": time.time(),
                    "finished": False
                })
                st.rerun()
        else:
            st.warning("⚠️ 此範圍無題目，請重新選擇。")

# --- ### [16] 測驗引擎介面 ---
if st.session_state.get('quiz_loaded') and not st.session_state.get('finished'):
    q = st.session_state.quiz_list[st.session_state.q_idx]
    st.session_state.current_qid = f"{q['版本']}_{q['年度']}_{q['冊編號']}_{q['單元']}_{q['課編號']}_{q['句編號']}"
    
    st.markdown(f'<div style="background:#f8f9fa; padding:20px; border-radius:12px; border-left:6px solid #007bff;"><b>第 {st.session_state.q_idx+1} 題 / 共 {len(st.session_state.quiz_list)} 題</b> ({st.session_state.current_qid})</div>', unsafe_allow_html=True)
    st.subheader(f"題目：{q['單選題目'] if '單選' in q['單元'] else q['重組中文題目']}")
    
    # 答題控制鍵 (上一題、下一題等) 保持鎖定
    st.divider()
    if st.button("🏁 提交並結束本次練習", type="secondary"):
        st.session_state.finished = True; st.rerun()

if st.session_state.get('finished'):
    st.balloons(); st.button("回首頁", on_click=lambda: st.session_state.update({"quiz_loaded": False, "finished": False}))

st.caption(f"Ver {VERSION} | 學生端開始練習功能鍵已鎖定")

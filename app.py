# ==============================================================================
# 🧩 英文全能練習系統 (V2.8.45 重組作答送出鍵鎖定版)
# ==============================================================================
# 📌 版本編號 (VERSION): 2.8.45
# 📅 更新日期: 2026-03-09
# ------------------------------------------------------------------------------
# 🛠️ 核心功能檢核清單 (逐號增加):
# [07] 🟡 數值調整鈕 [20] 🟠 範圍重設 [30] 🟡 末端計數優化
# [31] 🔴 重組檢查送出鍵: 確保學生排完單字後有按鈕可提交作答 -> LOCKED
# ==============================================================================

import streamlit as st
import pandas as pd
import random
import re
import time
from datetime import datetime
from streamlit_gsheets import GSheetsConnection

VERSION = "2.8.45"

# --- ### 🔵 MODULE 1: 基礎定義 ---
def standardize(v):
    val = str(v).split('.')[0].strip()
    return val.zfill(4) if val.isdigit() else val

# --- ### ⚪ MODULE 2: 數據中心 ---
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

def flush_buffer_to_cloud():
    if st.session_state.get('log_buffer'):
        try:
            old_logs = conn.read(worksheet="logs", ttl=0)
            new_rows = pd.DataFrame(st.session_state.log_buffer)
            updated_logs = pd.concat([old_logs, new_rows], ignore_index=True)
            conn.update(worksheet="logs", data=updated_logs)
            st.session_state.log_buffer = []; st.cache_data.clear()
        except: pass

def buffer_log(action, detail, result):
    duration = round(time.time() - st.session_state.get('start_time_ts', time.time()), 1)
    st.session_state.log_buffer.append({
        "時間": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "帳號": st.session_state.user_id, "姓名": st.session_state.user_name,
        "分組": st.session_state.group_id, "題目ID": st.session_state.get('current_qid','-'),
        "動作": action, "內容": detail, "結果": result, "費時": max(0.1, duration)
    })

# --- ### 🔵 MODULE 3: 登入與配置 ---
st.set_page_config(page_title=f"英文練習系統 V{VERSION}", layout="wide")
if 'logged_in' not in st.session_state: st.session_state.logged_in = False

if not st.session_state.logged_in:
    df_q, df_s = load_static_data()
    _, c, _ = st.columns([1, 1.2, 1])
    with c:
        st.markdown("### 🔵 系統登入系統")
        i_id = st.text_input("帳號", key="l_id")
        i_pw = st.text_input("密碼", type="password", key="l_pw")
        if st.button("🚀 登入", use_container_width=True):
            if df_s is not None:
                std_id, std_pw = standardize(i_id), standardize(i_pw)
                df_s['c_id'], df_s['c_pw'] = df_s['帳號'].apply(standardize), df_s['密碼'].apply(standardize)
                user = df_s[df_s['c_id'] == std_id]
                if not user.empty and user.iloc[0]['c_pw'] == std_pw:
                    st.session_state.clear()
                    st.session_state.update({"logged_in": True, "user_id": f"EA{std_id}", "user_name": user.iloc[0]['姓名'], "group_id": user.iloc[0]['分組'], "view_mode": "管理後台" if user.iloc[0]['分組']=="ADMIN" else "練習模式", "quiz_loaded": False, "log_buffer": [], "start_time_ts": time.time()})
                    st.rerun()
    st.stop()

df_q, df_s = load_static_data()
df_a, df_l = load_dynamic_data()

# --- ### 🟢 MODULE 5: 導師管理中心 ---
if st.session_state.group_id == "ADMIN" and st.session_state.view_mode == "管理後台":
    st.markdown(f"## 🟢 導師管理中心 (V{VERSION})")
    tabs = st.tabs(["📊 數據追蹤", "🎯 指派任務", "📜 任務管理"])
    st.stop()

# --- ### 🟡 MODULE 6: 學生設定區 [27, 30] ---
st.markdown("## 🟡 英文練習設定區")

if st.session_state.get('quiz_loaded'):
    if st.button("🔄 🟠 重新設定練習範圍", type="secondary"):
        st.session_state.quiz_loaded = False; st.rerun()

if not st.session_state.get('quiz_loaded'):
    with st.expander("⚙️ 設定選單", expanded=True):
        c_sel = st.columns(5)
        sv = c_sel[0].selectbox("1. 版本", sorted(df_q['版本'].unique()), key="s_v")
        df_v = df_q[df_q['版本'] == sv]
        su = c_sel[1].selectbox("2. 單元", sorted(df_v['單元'].unique()), key="s_u")
        df_vu = df_v[df_v['單元'] == su]
        sy = c_sel[2].selectbox("3. 年度", sorted(df_vu['年度'].unique()), key="s_y")
        df_vuy = df_vu[df_vu['年度'] == sy]
        sb = c_sel[3].selectbox("4. 冊別", sorted(df_vuy['冊編號'].unique()), key="s_b")
        df_vuyb = df_vuy[df_vuy['冊編號'] == sb]
        # 💡 [30] 只有最後一層計算題數
        l_opts = {l: f"第 {l} 課 ({len(df_vuyb[df_vuyb['課編號']==l])} 題)" for l in sorted(df_vuyb['課編號'].unique())}
        sl = c_sel[4].selectbox("5. 課次", sorted(df_vuyb['課編號'].unique()), format_func=lambda x: l_opts.get(x), key="s_l")
        
        st.divider()
        c_num = st.columns(2)
        st_i = c_num[0].number_input("📍 起始句編號 (+/-)", 1, 100, 1, key="s_i")
        nu_i = c_num[1].number_input("🔢 練習題數 (+/-)", 1, 50, 10, key="s_n")
        
        final_base = df_vuyb[df_vuyb['課編號'] == sl].copy()
        if not final_base.empty:
            final_base['句編號_int'] = pd.to_numeric(final_base['句編號'], errors='coerce')
            actual_q = final_base[final_base['句編號_int']>=st_i].sort_values('句編號_int').head(int(nu_i))
            if st.button("🚀 正式開始練習", type="primary", use_container_width=True):
                st.session_state.update({"quiz_list": actual_q.to_dict('records'), "q_idx": 0, "quiz_loaded": True, "ans": [], "used_history": [], "shuf": [], "show_analysis": False, "start_time_ts": time.time(), "finished": False})
                st.rerun()

# --- ### 🔴 MODULE 7: 測驗引擎 [16, 25, 31鎖定] ---
if st.session_state.get('quiz_loaded') and not st.session_state.get('finished'):
    st.markdown("---")
    st.markdown("## 🔴 核心測驗練習中")
    q = st.session_state.quiz_list[st.session_state.q_idx]
    st.session_state.current_qid = f"{q['版本']}_{q['年度']}_{q['冊編號']}_{q['單元']}_{q['課編號']}_{q['句編號']}"
    st.info(f"第 {st.session_state.q_idx+1} 題 / 共 {len(st.session_state.quiz_list)} 題")
    
    is_mcq = "單選" in q["單元"]
    ans_key = str(q["單選答案" if is_mcq else "重組英文答案"]).strip()
    st.subheader(f"題目：{q['單選題目'] if is_mcq else q['重組中文題目']}")
    
    if is_mcq:
        bc = st.columns(4)
        for i, opt in enumerate(["A", "B", "C", "D"]):
            if bc[i].button(opt, key=f"mcq_{i}", use_container_width=True):
                res = (opt == ans_key.upper()); buffer_log("單選", opt, "✅" if res else "❌")
                st.session_state.update({"current_res": "✅ 正確！" if res else f"❌ 錯誤！答案是 ({ans_key})", "show_analysis": True}); st.rerun()
    else:
        # [25] 重組單字庫
        st.info(" ".join(st.session_state.ans) if st.session_state.ans else "請點擊單字庫進行排序...")
        c_ctrl = st.columns(2)
        if c_ctrl[0].button("⬅️ 🟠 退回", use_container_width=True) and st.session_state.ans:
            st.session_state.ans.pop(); st.session_state.used_history.pop(); st.rerun()
        if c_ctrl[1].button("🗑️ 🟠 清除", use_container_width=True):
            st.session_state.update({"ans": [], "used_history": []}); st.rerun()
        
        tk = re.findall(r"[\w']+|[^\w\s]", ans_key)
        if not st.session_state.get('shuf'): st.session_state.shuf = tk.copy(); random.shuffle(st.session_state.shuf)
        
        # 單字庫按鈕
        bs = st.columns(3)
        for i, t in enumerate(st.session_state.shuf):
            if i not in st.session_state.get('used_history', []):
                if bs[i%3].button(t, key=f"qb_{i}", use_container_width=True): 
                    st.session_state.ans.append(t); st.session_state.used_history.append(i); st.rerun()
        
        # 💡 [31] 關鍵：重組檢查送出鍵
        if len(st.session_state.ans) == len(tk):
            st.divider()
            if st.button("✅ 檢查作答結果", type="primary", use_container_width=True):
                is_ok = "".join(st.session_state.ans).lower() == ans_key.replace(" ","").lower()
                buffer_log("重組", " ".join(st.session_state.ans), "✅" if is_ok else "❌")
                st.session_state.update({"current_res": "✅ 正確！" if is_ok else f"❌ 錯誤！正確答案：{ans_key}", "show_analysis": True}); st.rerun()

    if st.session_state.get('show_analysis'): st.warning(st.session_state.current_res)

    st.divider()
    nav = st.columns(2)
    if nav[0].button("⬅️ 🟠 上一題", disabled=(st.session_state.q_idx == 0)):
        st.session_state.q_idx -= 1; st.session_state.update({"ans":[], "used_history":[], "shuf":[], "show_analysis":False}); st.rerun()
    if nav[1].button("下一題 ➡️" if (st.session_state.q_idx + 1 < len(st.session_state.quiz_list)) else "🏁 結束測驗", type="secondary"):
        if st.session_state.q_idx + 1 < len(st.session_state.quiz_list):
            st.session_state.q_idx += 1; st.session_state.update({"ans":[], "used_history":[], "shuf":[], "show_analysis":False}); st.rerun()
        else: st.session_state.finished = True; flush_buffer_to_cloud(); st.rerun()

st.caption(f"Ver {VERSION} | 🔴 重組檢查送出鍵已物理鎖定")

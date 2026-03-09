# ==============================================================================
# 🧩 英文全能練習系統 (V2.8.26 視覺強制回歸鎖定版)
# ==============================================================================
# 📌 版本編號 (VERSION): 2.8.26
# 📅 更新日期: 2026-03-09
# ------------------------------------------------------------------------------
# 🛠️ 核心功能實體檢核清單 (逐號增加):
# [01-06] 基礎權限/登入補零/任務系統 (同前版)
# [07-A] 起始句編號 (s_i number_input) -> **視覺強制鎖定**
# [07-B] 練習題數 (s_n number_input) -> **視覺強制鎖定**
# [08] 排行看板 (Sidebar) -> **視覺強制鎖定**
# [09-13] 題號組合/效能緩衝/導師函數 (同前版)
# [14] 視覺強制回歸: 移除條件判斷，確保按鈕在選單下方必現
# [15] 導師端 IU 版本同步: 顯示 V2.8.26
# ==============================================================================

import streamlit as st
import pandas as pd
import random
import re
import time
from datetime import datetime
from streamlit_gsheets import GSheetsConnection

VERSION = "2.8.26"

st.set_page_config(page_title=f"英文練習系統 V{VERSION}", layout="wide")

# --- ### MODULE 1: 數據讀取 [02] ---
conn = st.connection("gsheets", type=GSheetsConnection)

@st.cache_data(ttl=30)
def load_static_data():
    try:
        df_q = conn.read(worksheet="questions")
        df_s = conn.read(worksheet="students")
        if df_q is not None: df_q = df_q.fillna("").astype(str).replace(r'\.0$', '', regex=True)
        if df_s is not None: df_s = df_s.fillna("").astype(str).replace(r'\.0$', '', regex=True)
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

# --- ### MODULE 2: 效能緩衝與存檔 [10, 11] ---
def buffer_log(action_type, detail="", result="-"):
    now_ts = time.time()
    start_ts = st.session_state.get('start_time_ts', now_ts)
    duration = max(0.1, round(now_ts - start_ts, 1))
    new_entry = {
        "時間": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "帳號": st.session_state.user_id, "姓名": st.session_state.user_name,
        "分組": st.session_state.group_id, "題目ID": st.session_state.get('current_qid','-'), 
        "動作": action_type, "內容": detail, "結果": result, "費時": duration
    }
    if 'log_buffer' not in st.session_state: st.session_state.log_buffer = []
    st.session_state.log_buffer.append(new_entry)

def flush_buffer_to_cloud():
    if st.session_state.get('log_buffer'):
        try:
            old_logs = conn.read(worksheet="logs", ttl=0)
            new_rows = pd.DataFrame(st.session_state.log_buffer)
            updated_logs = pd.concat([old_logs, new_rows], ignore_index=True)
            conn.update(worksheet="logs", data=updated_logs)
            st.session_state.log_buffer = []
            st.cache_data.clear() 
        except: pass

# --- ### MODULE 3: 登入模組 [01, 02] ---
if 'logged_in' not in st.session_state: st.session_state.logged_in = False
if 'view_mode' not in st.session_state: st.session_state.view_mode = "管理後台"

if not st.session_state.logged_in:
    df_q, df_s = load_static_data()
    _, c_login, _ = st.columns([1, 1.2, 1])
    with c_login:
        st.title("🧩 系統登入")
        i_id = st.text_input("帳號 (例如: 0097)", key="l_id")
        i_pw = st.text_input("密碼", type="password", key="l_pw")
        if st.button("🚀 登入系統", use_container_width=True):
            if df_s is not None:
                std_id, std_pw = standardize(i_id), standardize(i_pw)
                df_s['c_id'], df_s['c_pw'] = df_s['帳號'].apply(standardize), df_s['密碼'].apply(standardize)
                user = df_s[df_s['c_id'] == std_id]
                if not user.empty and user.iloc[0]['c_pw'] == std_pw:
                    st.session_state.update({"logged_in": True, "user_id": f"EA{std_id}", "user_name": user.iloc[0]['姓名'], "group_id": user.iloc[0]['分組'], "log_buffer": []})
                    st.rerun()
                else: st.error("❌ 帳號或密碼錯誤")
    st.stop()

df_q, df_s = load_static_data()
df_a, df_l = load_dynamic_data()

# --- ### MODULE 4: 側邊欄與排行 [08] ---
with st.sidebar:
    st.title(f"👋 {st.session_state.user_name}")
    if st.session_state.group_id == "ADMIN":
        st.session_state.view_mode = st.radio("模式切換：", ["管理後台", "練習模式"])
    if st.button("🚪 登出", use_container_width=True):
        flush_buffer_to_cloud(); st.session_state.logged_in = False; st.rerun()
    
    if (st.session_state.view_mode == "練習模式" or st.session_state.group_id != "ADMIN") and df_l is not None:
        st.divider()
        st.subheader("🏆 同組排行 (今日)")
        gl = df_l[df_l['分組'] == st.session_state.group_id].copy()
        st.markdown('<div style="max-height:250px; overflow-y:auto; background:#f9f9f9; padding:10px; border-radius:10px; border:1px solid #eee;">', unsafe_allow_html=True)
        members = sorted(df_s[df_s['分組'] == st.session_state.group_id]['姓名'].tolist())
        for m in members:
            cnt = len(gl[(gl['姓名']==m) & (gl['結果']=='✅')])
            st.markdown(f'<div style="display:flex; justify-content:space-between; font-size:13px; margin-bottom:4px;"><span>👤 {m}</span><b>{cnt} 題</b></div>', unsafe_allow_html=True)
        st.markdown('</div>', unsafe_allow_html=True)

# --- ### MODULE 5: 導師管理中心 [03, 04, 05, 12, 13, 15] ---
if st.session_state.group_id == "ADMIN" and st.session_state.view_mode == "管理後台":
    st.title(f"👨‍🏫 導師管理中心 (V{VERSION})") 
    t_tabs = st.tabs(["📊 數據追蹤", "🎯 指派任務", "📜 任務管理"])
    
    with t_tabs[1]:
        st.subheader("🎯 發佈新指派")
        cs = st.columns(5)
        av, au, ay, ab, al = cs[0].selectbox("版本", sorted(df_q['版本'].unique()), key="av_a"), cs[1].selectbox("單元", sorted(df_q['單元'].unique()), key="au_a"), cs[2].selectbox("年度", sorted(df_q['年度'].unique()), key="ay_a"), cs[3].selectbox("冊別", sorted(df_q['冊編號'].unique()), key="ab_a"), cs[4].selectbox("課次", sorted(df_q['課編號'].unique()), key="al_a")
        if st.button("📢 發佈任務", type="primary"):
            sq = df_q[(df_q['版本']==av)&(df_q['單元']==au)&(df_q['年度']==ay)&(df_q['冊編號']==ab)&(df_q['課編號']==al)]
            fids = [f"{r['版本']}_{r['年度']}_{r['冊編號']}_{r['單元']}_{r['課編號']}_{r['句編號']}" for _, r in sq.iterrows()]
            new_t = pd.DataFrame([{"對象 (分組/姓名)": "全體", "任務類型": "練習", "題目ID清單": ", ".join(fids), "說明文字": f"{au} 任務", "指派時間": datetime.now().strftime("%Y-%m-%d %H:%M:%S")}])
            conn.update(worksheet="assignments", data=pd.concat([df_a, new_t], ignore_index=True)); st.cache_data.clear(); st.rerun()

    with t_tabs[2]:
        for i, r in df_a.iloc[::-1].iterrows():
            c_i, c_d = st.columns([5, 1])
            c_i.warning(f"📌 {r['說明文字']}")
            if c_d.button("🗑️ 刪除", key=f"dt_{i}"):
                conn.update(worksheet="assignments", data=df_a.drop(i)); st.cache_data.clear(); st.rerun()
    st.stop()

# --- ### MODULE 6: 學生練習區 [07-A/B, 14] ---
st.title("🚀 英文練習區")

# [07-A/B, 14] 💡 強制視覺回歸：數值調整鈕必現
with st.expander("⚙️ 手動設定練習範圍", expanded=not st.session_state.get('quiz_loaded', False)):
    cs = st.columns(5)
    sv, su, sy, sb, sl = cs[0].selectbox("版本", sorted(df_q['版本'].unique()), key="s_v"), cs[1].selectbox("單元", sorted(df_q['單元'].unique()), key="s_u"), cs[2].selectbox("年度", sorted(df_q['年度'].unique()), key="s_y"), cs[3].selectbox("冊別", sorted(df_q['冊編號'].unique()), key="s_b"), cs[4].selectbox("課次", sorted(df_q['課編號'].unique()), key="s_l")
    
    # 💡 移除數據判斷限制，按鈕直接顯示
    st.divider()
    sc1, sc2 = st.columns(2)
    st_i = sc1.number_input("📍 起始句編號 (+/-)", 1, 100, 1, key="s_i")
    nu_i = sc2.number_input("🔢 練習題數 (+/-)", 1, 50, 10, key="s_n")
    
    if st.button(f"🚀 載入測驗", key="btn_load"):
        base = df_q[(df_q['版本']==sv)&(df_q['單元']==su)&(df_q['年度']==sy)&(df_q['冊編號']==sb)&(df_q['課編號']==sl)].copy()
        if not base.empty:
            base['句編號_int'] = pd.to_numeric(base['句編號'], errors='coerce')
            q_data = base[base['句編號_int']>=st_i].sort_values('句編號_int').head(int(nu_i))
            st.session_state.update({"quiz_list": q_data.to_dict('records'), "q_idx": 0, "quiz_loaded": True, "ans": [], "used_history": [], "shuf": [], "show_analysis": False, "start_time_ts": time.time()})
            st.rerun()
        else: st.warning("此範圍查無題目")

# --- ### [10] 測驗引擎 ---
if st.session_state.get('quiz_loaded') and not st.session_state.get('finished'):
    q = st.session_state.quiz_list[st.session_state.q_idx]
    st.session_state.current_qid = f"{q['版本']}_{q['年度']}_{q['冊編號']}_{q['單元']}_{q['課編號']}_{q['句編號']}"
    is_mcq = "單選" in q["單元"]
    disp = q["單選題目"] if is_mcq else q["重組中文題目"]
    ans_key = re.sub(r'[^A-Za-z]', '', str(q["單選答案" if is_mcq else "重組英文答案"])).upper() if is_mcq else str(q["重組英文答案"]).strip()
    
    st.markdown(f'<div style="background:#f8f9fa; padding:20px; border-radius:12px; border-left:6px solid #007bff;"><b>第 {st.session_state.q_idx+1} 題 / 共 {len(st.session_state.quiz_list)} 題</b><br><br><span style="font-size:22px;">{disp}</span></div>', unsafe_allow_html=True)
    if is_mcq:
        cols = st.columns(4)
        for i, opt in enumerate(["A", "B", "C", "D"]):
            if cols[i].button(opt, key=f"qo_{i}", use_container_width=True):
                is_ok = (opt == ans_key)
                buffer_log("單選", opt, "✅" if is_ok else "❌")
                st.session_state.update({"current_res": "✅ 正確！" if is_ok else f"❌ 錯誤！答案是 ({ans_key})", "show_analysis": True}); st.rerun()
        if st.session_state.get('show_analysis'):
            st.write(st.session_state.current_res)
            if st.button("下一題 ➡️"):
                if st.session_state.q_idx + 1 < len(st.session_state.quiz_list):
                    st.session_state.q_idx += 1; st.session_state.update({"ans": [], "used_history": [], "shuf": [], "show_analysis": False, "start_time_ts": time.time()}); st.rerun()
                else: st.session_state.finished = True; flush_buffer_to_cloud(); st.rerun()
    else:
        st.write(" ".join(st.session_state.ans) if st.session_state.ans else "......")
        tk = re.findall(r"[\w']+|[^\w\s]", ans_key)
        if not st.session_state.get('shuf'): st.session_state.shuf = tk.copy(); random.shuffle(st.session_state.shuf)
        bs = st.columns(2)
        for i, t in enumerate(st.session_state.shuf):
            if i not in st.session_state.get('used_history', []):
                if bs[i%2].button(t, key=f"qb_{i}", use_container_width=True): st.session_state.ans.append(t); st.session_state.used_history.append(i); st.rerun()
        if st.button("🔄 重填"): st.session_state.update({"ans": [], "used_history": []}); st.rerun()
        if len(st.session_state.ans) == len(tk):
            if st.button("✅ 檢查並下一題", type="primary"):
                is_ok = "".join(st.session_state.ans).lower() == ans_key.replace(" ","").lower()
                buffer_log("重組", " ".join(st.session_state.ans), "✅" if is_ok else "❌")
                if st.session_state.q_idx + 1 < len(st.session_state.quiz_list):
                    st.session_state.q_idx += 1; st.session_state.update({"ans": [], "used_history": [], "shuf": [], "show_analysis": False, "start_time_ts": time.time()}); st.rerun()
                else: st.session_state.finished = True; flush_buffer_to_cloud(); st.rerun()

st.divider()
if st.session_state.get('finished'):
    st.balloons(); st.button("回首頁", on_click=lambda: st.session_state.update({"quiz_loaded": False, "finished": False, "q_idx": 0, "log_buffer": []}))

st.caption(f"強制鎖定版 Ver {VERSION} | 起始句/題數按鈕已移除資料限制")

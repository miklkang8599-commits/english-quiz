# ==============================================================================
# 🧩 英文全能練習系統 (V2.6.4 效能與資訊優化版)
# ==============================================================================
# 📌 版本編號 (VERSION): 2.6.4
# 📅 更新日期: 2026-03-08
#
# 📜 【GitHub 開發日誌】
# ------------------------------------------------------------------------------
# V2.6.4 [2026-03-08]: 
#   - 優化單選題回饋速度：減少重繪次數，讓「正確/錯誤」圖樣即時顯示。
#   - 增強進度設定資訊：顯示範圍內總題數與原始句編號區間。
#   - 修正選單連動效能。
# ==============================================================================

import streamlit as st
import pandas as pd
import random
import re
import time
from datetime import datetime
from streamlit_gsheets import GSheetsConnection

VERSION = "2.6.4"
IDLE_TIMEOUT = 300 

st.set_page_config(page_title=f"英文練習系統 V{VERSION}", layout="wide")

# --- 1. 核心邏輯 ---
def enforce_auto_logout():
    if st.session_state.get('logged_in'):
        now = time.time()
        if now - st.session_state.get('last_activity', now) > IDLE_TIMEOUT:
            for key in list(st.session_state.keys()): del st.session_state[key]
            st.session_state.logged_in = False
            st.rerun()

conn = st.connection("gsheets", type=GSheetsConnection)

@st.cache_data(ttl=5)
def load_all_data():
    try:
        df_q = conn.read(worksheet="questions")
        df_s = conn.read(worksheet="students")
        df_a = conn.read(worksheet="assignments")
        df_l = conn.read(worksheet="logs")
        if df_q is not None:
            df_q = df_q.fillna("")
            for col in df_q.columns:
                df_q[col] = df_q[col].astype(str).str.replace(r'\.0$', '', regex=True).str.strip()
        if df_l is not None and not df_l.empty:
            df_l['時間'] = pd.to_datetime(df_l['時間'], errors='coerce')
        return df_q, df_s, df_a, df_l
    except: return None, None, None, None

def log_event(action_type, detail="", result="-", duration=0):
    if not st.session_state.get('logged_in'): return
    try:
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        new_row = pd.DataFrame([{
            "時間": now, "帳號": st.session_state.user_id, "姓名": st.session_state.user_name,
            "分組": st.session_state.group_id, "題目ID": st.session_state.get('current_qid','-'), 
            "動作": action_type, "內容": detail, "結果": result, "費時": duration
        }])
        old_logs = conn.read(worksheet="logs", ttl=0)
        updated_logs = pd.concat([old_logs, new_row], ignore_index=True)
        conn.update(worksheet="logs", data=updated_logs)
        st.cache_data.clear()
    except: pass

def reset_quiz():
    st.session_state.ans, st.session_state.used_history, st.session_state.shuf = [], [], []
    st.session_state.start_time = datetime.now()
    st.session_state.show_analysis = False
    st.session_state.current_res = None

# --- 2. 登入系統 (略) ---
if 'logged_in' not in st.session_state: st.session_state.logged_in = False
enforce_auto_logout()

if not st.session_state.logged_in:
    _, c_login, _ = st.columns([1, 1.2, 1])
    with c_login:
        st.title("🧩 系統登入")
        input_id = st.text_input("帳號 (後四碼)")
        input_pw = st.text_input("密碼", type="password")
        if st.button("🚀 登入", use_container_width=True):
            df_q, df_s, _, _ = load_all_data()
            df_s['帳號_c'] = df_s['帳號'].astype(str).split('.').str[0].str.zfill(4)
            user = df_s[df_s['帳號_c'] == input_id.strip()]
            if not user.empty and str(user.iloc[0]['密碼']).split('.')[0] == input_pw.strip():
                st.session_state.logged_in = True
                st.session_state.last_activity = time.time()
                st.session_state.user_id = f"EA{input_id.zfill(4)}"
                st.session_state.user_name = user.iloc[0]['姓名']
                st.session_state.group_id = user.iloc[0]['分組']
                log_event("登入")
                st.rerun()
    st.stop()

# --- 3. 資料與側邊欄 ---
st.session_state.last_activity = time.time()
df_q, df_s, df_a, df_l = load_all_data()

# --- 4. 學生主介面 ---
st.title(f"👋 {st.session_state.user_name}")

# A. 老師任務顯示 (略，維持邏輯)

# B. 手動設定區 (強化資訊顯示)
with st.expander("⚙️ 手動範圍與題數設定", expanded=not st.session_state.get('quiz_loaded', False)):
    if df_q is not None:
        c = st.columns(5)
        sv = c[0].selectbox("版本", sorted([v for v in df_q['版本'].unique() if v != ""]), key="sv")
        su = c[1].selectbox("項目", sorted([u for u in df_q[df_q['版本']==sv]['單元'].unique() if u != ""]), key="su")
        sy = c[2].selectbox("年度", sorted(list(df_q[(df_q['版本']==sv)&(df_q['單元']==su)]['年度'].unique())), key="sy")
        sb = c[3].selectbox("冊別", sorted(list(df_q[(df_q['版本']==sv)&(df_q['單元']==su)&(df_q['年度']==sy)]['冊編號'].unique())), key="sb")
        sl = c[4].selectbox("課次", sorted(list(df_q[(df_q['版本']==sv)&(df_q['單元']==su)&(df_q['年度']==sy)&(df_q['冊編號']==sb)]['課編號'].unique())), key="sl")
        
        base = df_q[(df_q['版本']==sv)&(df_q['單元']==su)&(df_q['年度']==sy)&(df_q['冊編號']==sb)&(df_q['課編號']==sl)]
        
        if not base.empty:
            nums = sorted([int(n) for n in base['句編號'].unique()])
            # 💡 顯示範圍資訊
            st.info(f"📊 該課目前共有 **{len(base)}** 題 | 句編號區間：**{min(nums)} ~ {max(nums)}**")
            
            sc1, sc2 = st.columns(2)
            start = sc1.number_input("起始句編號", min(nums), max(nums), min(nums))
            num = sc2.number_input("預計練習題數", 1, 50, 10)
            
            # 計算實際會載入的題數
            final_count = len(base[base['句編號'].astype(int) >= start].head(num))
            
            if st.button(f"🚀 載入測驗 (共 {final_count} 題)", use_container_width=True):
                st.session_state.quiz_list = base[base['句編號'].astype(int) >= start].sort_values('句編號').head(num).to_dict('records')
                st.session_state.q_idx = 0
                reset_quiz()
                st.session_state.quiz_loaded = True
                st.rerun()

# --- 5. 核心練習區 ---
if st.session_state.get('quiz_loaded') and not st.session_state.get('finished'):
    q = st.session_state.quiz_list[st.session_state.q_idx]
    st.session_state.current_qid = f"{q['版本']}_{q['年度']}_{q['冊編號']}_{q['單元']}_{q['課編號']}_{q['句編號']}"
    
    is_mcq = "單選" in q["單元"]
    disp = q["單選題目"] if is_mcq else q["重組中文題目"]
    raw_ans = q["單選答案"] if is_mcq else q["重組英文答案"]
    clean_ans = re.sub(r'[^A-Za-z]', '', raw_ans).upper() if is_mcq else raw_ans.strip()

    st.markdown(f'<div style="background:#f8f9fa; padding:20px; border-radius:10px; border-left:6px solid #1e88e5; margin-bottom:15px;">'
                f'<b>第 {st.session_state.q_idx+1} 題 / 共 {len(st.session_state.quiz_list)} 題 (原句編號: {q["句編號"]})</b><br><br>{disp}</div>', unsafe_allow_html=True)
    
    if is_mcq:
        # 單選題加速回饋邏輯
        cols = st.columns(4)
        for i, opt in enumerate(["A", "B", "C", "D"]):
            if cols[i].button(opt, key=f"opt_{i}", use_container_width=True, disabled=st.session_state.get('show_analysis', False)):
                is_ok = (opt == clean_ans)
                log_event("單選", detail=opt, result="✅" if is_ok else "❌")
                st.session_state.current_res = "✅ 正確！" if is_ok else f"❌ 錯誤！正確答案是 ({clean_ans})"
                st.session_state.show_analysis = True
                st.rerun()
        
        if st.session_state.get('show_analysis'):
            if "✅" in st.session_state.current_res: st.success(st.session_state.current_res)
            else: st.error(st.session_state.current_res)
            
            if q.get("單選解析"): st.warning(f"💡 解析：{q['單選解析']}")
            if st.button("下一題 ➡️", type="primary"):
                if st.session_state.q_idx + 1 < len(st.session_state.quiz_list):
                    st.session_state.q_idx += 1
                    reset_quiz()
                    st.rerun()
                else:
                    st.session_state.finished = True
                    st.rerun()
    else:
        # 重組題顯示原始句編號
        st.markdown(f'<div style="background:white; padding:15px; border-radius:10px; border:1px solid #ddd; min-height:70px; display:flex; flex-wrap:wrap; gap:8px; align-items:center; justify-content:center; font-size:20px;">'
                    f'{" ".join(st.session_state.ans) if st.session_state.ans else "......"}</div>', unsafe_allow_html=True)
        tk = re.findall(r"[\w']+|[^\w\s]", clean_ans)
        if not st.session_state.shuf: st.session_state.shuf = tk.copy(); random.shuffle(st.session_state.shuf)
        
        bs = st.columns(2)
        for i, t in enumerate(st.session_state.shuf):
            if i not in st.session_state.used_history:
                if bs[i%2].button(t, key=f"btn_{i}", use_container_width=True):
                    st.session_state.ans.append(t); st.session_state.used_history.append(i); st.rerun()
        
        if st.button("🔄 重填"): st.session_state.ans, st.session_state.used_history = [], []; st.rerun()
        
        if len(st.session_state.ans) == len(tk):
            if st.button("✅ 檢查答案", type="primary"):
                is_ok = "".join(st.session_state.ans).lower() == clean_ans.replace(" ","").lower()
                log_event("重組", detail=" ".join(st.session_state.ans), result="✅" if is_ok else "❌")
                if is_ok:
                    st.success("正確！")
                    time.sleep(0.5)
                    if st.session_state.q_idx + 1 < len(st.session_state.quiz_list):
                        st.session_state.q_idx += 1
                        reset_quiz()
                        st.rerun()
                    else:
                        st.session_state.finished = True
                        st.rerun()
                else: st.error(f"正確答案: {clean_ans}")

elif st.session_state.get('finished'):
    st.balloons(); st.success("測驗完成！")
    if st.button("回首頁"): 
        st.session_state.update({"quiz_loaded": False, "finished": False, "q_idx": 0})
        st.rerun()

st.caption(f"Ver {VERSION}")

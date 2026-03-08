# ==============================================================================
# 🧩 英文全能練習系統 (V2.7.0 穩定紀錄版)
# ==============================================================================
# 📌 版本編號 (VERSION): 2.7.0
# 📅 更新日期: 2026-03-08
#
# 📜 【GitHub 開發日誌】
# ------------------------------------------------------------------------------
# V2.7.0 [2026-03-08]: 
#   - 修復 AttributeError: 增加題目ID解析安全性檢查，防止非題目紀錄導致崩潰。
#   - 優化主頁紀錄框：修正時間顯示格式，強化 ✅/❌ 視覺對比。
#   - 穩定手動範圍設定與自動排序。
# ==============================================================================

import streamlit as st
import pandas as pd
import random
import re
import time
from datetime import datetime
from streamlit_gsheets import GSheetsConnection

VERSION = "2.7.0"
IDLE_TIMEOUT = 300 

st.set_page_config(page_title=f"英文練習系統 V{VERSION}", layout="wide")

# --- 1. 資料讀取與快取 ---
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
        return df_a, df_l
    except: return None, None

def log_event_fast(action_type, detail="", result="-"):
    now_ts = time.time()
    start_ts = st.session_state.get('start_time_ts', now_ts)
    duration = round(now_ts - start_ts, 1)
    
    st.session_state.pending_log = {
        "時間": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "帳號": st.session_state.user_id,
        "姓名": st.session_state.user_name,
        "分組": st.session_state.group_id,
        "題目ID": st.session_state.get('current_qid','-'), 
        "動作": action_type,
        "內容": detail,
        "結果": result,
        "費時": duration
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

# --- 2. 登入系統 ---
if 'logged_in' not in st.session_state: st.session_state.logged_in = False

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

# --- 3. 介面樣式 ---
st.markdown("""
<style>
    .log-container {
        max-height: 250px;
        overflow-y: auto;
        background-color: #ffffff;
        border: 2px solid #eeeeee;
        border-radius: 10px;
        padding: 15px;
    }
    .log-entry {
        border-bottom: 1px solid #f0f0f0;
        padding: 8px 0;
        font-size: 14px;
        display: flex;
        justify-content: space-between;
        font-family: 'Courier New', Courier, monospace;
    }
    .res-ok { color: #28a745; font-weight: bold; }
    .res-no { color: #dc3545; font-weight: bold; }
</style>
""", unsafe_allow_html=True)

# --- 4. 學生主介面 ---
df_q, df_s = load_static_data()
df_a, df_l = load_dynamic_data()

st.title(f"👋 {st.session_state.user_name}")

with st.sidebar:
    if st.button("🚪 登出系統", use_container_width=True):
        st.session_state.logged_in = False
        st.rerun()

# [手動設定區]
with st.expander("⚙️ 設定練習範圍", expanded=not st.session_state.get('quiz_loaded', False)):
    c = st.columns(5)
    sv = c[0].selectbox("版本", sorted(df_q['版本'].unique()), key="sv")
    su = c[1].selectbox("項目", sorted(df_q[df_q['版本']==sv]['單元'].unique()), key="su")
    sy = c[2].selectbox("年度", sorted(df_q[(df_q['版本']==sv)&(df_q['單元']==su)]['年度'].unique()), key="sy")
    sb = c[3].selectbox("冊別", sorted(df_q[(df_q['版本']==sv)&(df_q['單元']==su)&(df_q['年度']==sy)]['冊編號'].unique()), key="sb")
    sl = c[4].selectbox("課次", sorted(df_q[(df_q['版本']==sv)&(df_q['單元']==su)&(df_q['年度']==sy)&(df_q['冊編號']==sb)]['課編號'].unique()), key="sl")
    
    base = df_q[(df_q['版本']==sv)&(df_q['單元']==su)&(df_q['年度']==sy)&(df_q['冊編號']==sb)&(df_q['課編號']==sl)].copy()
    if not base.empty:
        base['句編號_int'] = pd.to_numeric(base['句編號'], errors='coerce')
        base = base.sort_values('句編號_int')
        nums = base['句編號_int'].dropna().unique().tolist()
        st.info(f"📊 範圍內共 {len(base)} 題 | 編號：{int(min(nums))} ~ {int(max(nums))}")
        sc = st.columns(2)
        start = sc[0].number_input("起始句編號", int(min(nums)), int(max(nums)), int(min(nums)))
        num = sc[1].number_input("練習題數", 1, 50, 10)
        if st.button("🚀 開始練習", use_container_width=True):
            st.session_state.quiz_list = base[base['句編號_int'] >= start].head(int(num)).to_dict('records')
            st.session_state.update({"q_idx": 0, "quiz_loaded": True, "ans": [], "used_history": [], "shuf": [], "show_analysis": False, "start_time_ts": time.time()})
            st.rerun()

# --- 5. 核心練習區 ---
if st.session_state.get('quiz_loaded') and not st.session_state.get('finished'):
    q = st.session_state.quiz_list[st.session_state.q_idx]
    st.session_state.current_qid = f"{q['版本']}_{q['年度']}_{q['冊編號']}_{q['單元']}_{q['課編號']}_{q['句編號']}"
    is_mcq = "單選" in q["單元"]
    disp = q["單選題目"] if is_mcq else q["重組中文題目"]
    clean_ans = re.sub(r'[^A-Za-z]', '', str(q["單選答案"])).upper() if is_mcq else str(q["重組英文答案"]).strip()

    st.markdown(f'<div style="background:#f0f7ff; padding:20px; border-radius:10px; border-left:6px solid #007bff; margin-bottom:15px;">'
                f'<b>📝 題目 {st.session_state.q_idx+1} / {len(st.session_state.quiz_list)} (原句編號: {q["句編號"]})</b><br><br>'
                f'<span style="font-size:22px;">{disp}</span></div>', unsafe_allow_html=True)
    
    if is_mcq:
        cols = st.columns(4)
        for i, opt in enumerate(["A", "B", "C", "D"]):
            if cols[i].button(opt, key=f"opt_{i}", use_container_width=True, disabled=st.session_state.get('show_analysis', False)):
                is_ok = (opt == clean_ans)
                log_event_fast("單選", detail=opt, result="✅" if is_ok else "❌")
                st.session_state.current_res = ("✅ 正確！" if is_ok else f"❌ 錯誤！答案是 ({clean_ans})")
                st.session_state.show_analysis = True
                st.rerun()
        if st.session_state.get('show_analysis'):
            if "✅" in st.session_state.current_res: st.success(st.session_state.current_res)
            else: st.error(st.session_state.current_res)
            if st.button("下一題 ➡️", type="primary"):
                flush_pending_log()
                if st.session_state.q_idx + 1 < len(st.session_state.quiz_list):
                    st.session_state.q_idx += 1
                    st.session_state.update({"ans": [], "used_history": [], "shuf": [], "show_analysis": False, "start_time_ts": time.time()})
                    st.rerun()
                else: st.session_state.finished = True; st.rerun()
    else:
        # 重組邏輯
        st.markdown(f'<div style="background:white; padding:15px; border-radius:10px; border:1px solid #ddd; min-height:70px; display:flex; flex-wrap:wrap; gap:8px; align-items:center; justify-content:center; font-size:22px;">'
                    f'{" ".join(st.session_state.ans) if st.session_state.ans else "......"}</div>', unsafe_allow_html=True)
        tk = re.findall(r"[\w']+|[^\w\s]", clean_ans)
        if not st.session_state.get('shuf'): st.session_state.shuf = tk.copy(); random.shuffle(st.session_state.shuf)
        bs = st.columns(2)
        for i, t in enumerate(st.session_state.shuf):
            if i not in st.session_state.used_history:
                if bs[i%2].button(t, key=f"btn_{i}", use_container_width=True):
                    st.session_state.ans.append(t); st.session_state.used_history.append(i); st.rerun()
        if st.button("🔄 重填"): st.session_state.update({"ans": [], "used_history": []}); st.rerun()
        if len(st.session_state.ans) == len(tk):
            if st.button("✅ 檢查答案", type="primary"):
                is_ok = "".join(st.session_state.ans).lower() == clean_ans.replace(" ","").lower()
                log_event_fast("重組", detail=" ".join(st.session_state.ans), result="✅" if is_ok else "❌")
                if is_ok: st.success("正確！"); time.sleep(0.5)
                else: st.error(f"正確答案: {clean_ans}")
                flush_pending_log()
                if st.session_state.q_idx + 1 < len(st.session_state.quiz_list):
                    st.session_state.q_idx += 1
                    st.session_state.update({"ans": [], "used_history": [], "shuf": [], "show_analysis": False, "start_time_ts": time.time()})
                    st.rerun()
                else: st.session_state.finished = True; st.rerun()

# --- 6. 個人學習紀錄框 (修復解析崩潰 Bug) ---
st.divider()
st.subheader("📜 最近練習紀錄")

if df_l is not None and not df_l.empty:
    my_logs = df_l[df_l['帳號'] == st.session_state.user_id].copy()
    if not my_logs.empty:
        my_logs = my_logs.sort_index(ascending=False)
        
        log_html = '<div class="log-container">'
        for _, row in my_logs.iterrows():
            # 💡 安全解析題號
            raw_qid = str(row['題目ID'])
            if "_" in raw_qid:
                item_display = f"題: {raw_qid.split('_')[-1]}"
            else:
                item_display = f"{row['動作']}" # 非題目時顯示動作(如登入)
                
            res_class = "res-ok" if row['結果'] == "✅" else "res-no"
            time_str = str(row['時間']).split(' ')[-1][:8] # 取得 00:00:00
            
            log_html += f'''
            <div class="log-entry">
                <span>🕒 {time_str} | <b>{item_display}</b></span>
                <span>結果: <span class="{res_class}">{row['結果']}</span> | 費時: {row['費時']}s</span>
            </div>
            '''
        log_html += '</div>'
        st.markdown(log_html, unsafe_allow_html=True)
    else:
        st.info("尚無紀錄")

if st.session_state.get('finished'):
    st.balloons(); st.success("🎉 完成！")
    if st.button("返回設定"):
        st.session_state.update({"quiz_loaded": False, "finished": False, "q_idx": 0})
        st.rerun()

st.caption(f"Stable Log Ver {VERSION}")

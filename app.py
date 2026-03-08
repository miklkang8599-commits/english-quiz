# ==============================================================================
# 🧩 英文重組練習旗艦版 (English Sentence Scramble App)
# ==============================================================================
# 📌 版本編號 (VERSION): 2.2.0
# 📅 更新日期: 2026-03-08
#
# 📜 【GitHub 開發日誌】
# ------------------------------------------------------------------------------
# V2.2.0 [2026-03-08]: 
#   - 多重錯題篩選：支援依「冊數、單元、課次、錯誤次數」交叉篩選錯題。
#   - 預覽模式：指派前可先預覽題目內容（中文/英文），確保指派精確。
#   - 連動式選單：篩選介面會隨選擇範圍自動更新選項。
# ==============================================================================

import streamlit as st
import pandas as pd
import random
import re
import time
from datetime import datetime
from streamlit_gsheets import GSheetsConnection

VERSION = "2.2.0"
IDLE_TIMEOUT = 300 

st.set_page_config(page_title=f"英文重組 V{VERSION}", layout="wide")

# --- 1. 核心檢查與連線 ---
def enforce_auto_logout():
    if st.session_state.get('logged_in'):
        if time.time() - st.session_state.get('last_activity', time.time()) > IDLE_TIMEOUT:
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
        
        # 統一處理數值格式避免連動錯誤
        for df in [df_q, df_a, df_l]:
            if df is not None:
                for col in ['年度', '冊編號', '課編號', '句編號']:
                    if col in df.columns:
                        df[col] = pd.to_numeric(df[col], errors='coerce')
        return df_q, df_s, df_a, df_l
    except: return None, None, None, None

# --- 2. 輔助函數 ---
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
    st.session_state.q_idx = 0
    st.session_state.ans, st.session_state.used_history, st.session_state.shuf = [], [], []
    st.session_state.start_time = datetime.now()
    st.session_state.finished = False

# --- 3. 登入系統 ---
if 'logged_in' not in st.session_state: st.session_state.logged_in = False
enforce_auto_logout()

if not st.session_state.logged_in:
    _, c_login, _ = st.columns([1, 1.2, 1])
    with c_login:
        st.title("🧩 學生登入系統")
        input_id = st.text_input("帳號 (後四碼)", placeholder="0001")
        input_pw = st.text_input("密碼", type="password")
        if st.button("🚀 登入", use_container_width=True):
            df_q, df_s, _, _ = load_all_data()
            df_s['帳號_c'] = df_s['帳號'].astype(str).str.split('.').str[0].str.zfill(4)
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

# --- 4. 主介面資料載入 ---
st.session_state.last_activity = time.time()
df_q, df_s, df_a, df_l = load_all_data()

# --- 5. 導師管理後台 (V2.2 多重篩選更新) ---
if st.session_state.group_id == "ADMIN":
    with st.expander("👨‍🏫 導師管理後台 V2.2", expanded=True):
        t_tabs = st.tabs(["📊 任務進度追蹤", "🎯 多重錯題指派", "🔍 分組全覽"])
        
        with t_tabs[0]: # 任務追蹤 (同前)
            if df_a is not None and not df_a.empty:
                for idx, row in df_a.iterrows():
                    st.write(f"**任務：{row['說明文字']} (對象: {row['對象 (分組/姓名)']})**")
                    q_list = str(row['題目ID清單']).split(', ')
                    relevant_logs = df_l[(df_l['動作']=='作答') & (df_l['題目ID'].isin(q_list))]
                    st.dataframe(relevant_logs[['時間', '姓名', '題目ID', '結果', '費時']], use_container_width=True)

        with t_tabs[1]: # 重點更新：多重篩選器
            st.subheader("🛠️ 進階錯題任務篩選")
            if df_l is not None and not df_l.empty:
                # 取得所有錯題紀錄並與原始題庫關聯
                wrong_logs = df_l[df_l['結果']=='❌'].copy()
                
                # 建立多重篩選控制列
                c1, c2, c3, c4 = st.columns(4)
                f_y = c1.selectbox("篩選年度", ["全部"] + sorted(list(df_q['年度'].unique())))
                f_b = c2.selectbox("篩選冊別", ["全部"] + sorted([int(x) for x in df_q['冊編號'].unique()]))
                f_l = c3.selectbox("篩選課次", ["全部"] + sorted([int(x) for x in df_q['課編號'].unique()]))
                min_err = c4.number_input("最低錯誤次數門檻", min_value=1, value=1)
                
                # 執行篩選邏輯
                wrong_counts = wrong_logs['題目ID'].value_counts().reset_index()
                wrong_counts.columns = ['題目ID', '錯誤次數']
                filtered_stats = wrong_counts[wrong_counts['錯誤次數'] >= min_err]
                
                # 與題庫關聯以獲取詳細資訊 (年度_冊_單元_課_句)
                def get_details(qid):
                    try:
                        p = qid.split('_')
                        # 這裡假設 QID 格式穩定為 年度_冊_單元_課_句
                        return {'年度': int(p[0]), '冊編號': int(p[1]), '單元': p[2], '課編號': int(p[3]), '句編號': int(p[4])}
                    except: return None

                # 增加詳細欄位供過濾
                detailed_list = []
                for _, r in filtered_stats.iterrows():
                    det = get_details(r['題目ID'])
                    if det:
                        det['題目ID'] = r['題目ID']
                        det['錯誤次數'] = r['錯誤次數']
                        detailed_list.append(det)
                
                df_filtered = pd.DataFrame(detailed_list)
                
                if not df_filtered.empty:
                    if f_y != "全部": df_filtered = df_filtered[df_filtered['年度'] == f_y]
                    if f_b != "全部": df_filtered = df_filtered[df_filtered['冊編號'] == f_b]
                    if f_l != "全部": df_filtered = df_filtered[df_filtered['課編號'] == f_l]
                
                if not df_filtered.empty:
                    # 結合題庫抓取中文對照，方便老師預覽
                    final_preview = pd.merge(df_filtered, df_q[['年度','冊編號','單元','課編號','句編號','中文','英文']], on=['年度','冊編號','單元','課編號','句編號'], how='left')
                    
                    st.write(f"🔍 找到 {len(final_preview)} 題符合條件的錯題：")
                    st.dataframe(final_preview[['題目ID', '錯誤次數', '中文', '英文']], use_container_width=True)
                    
                    # 指派區域
                    st.divider()
                    col_target, col_note = st.columns(2)
                    assign_to = col_target.selectbox("指派任務給：", ["全體"] + sorted(df_s['分組'].unique().tolist()) + sorted(df_s['姓名'].unique().tolist()))
                    default_note = f"加強練習：{f_b if f_b!='全部' else ''}冊 L{f_l if f_l!='全部' else ''} 錯題集"
                    task_note = col_note.text_input("任務名稱/說明", value=default_note)
                    
                    if st.button("📢 確定指派選中的所有錯題", type="primary"):
                        q_list_str = ", ".join(final_preview['題目ID'].tolist())
                        new_task = pd.DataFrame([{
                            "對象 (分組/姓名)": assign_to,
                            "任務類型": "多重篩選錯題",
                            "題目ID清單": q_list_str,
                            "說明文字": task_note,
                            "指派時間": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        }])
                        conn.update(worksheet="assignments", data=pd.concat([df_a, new_task], ignore_index=True))
                        st.success(f"已指派 {len(final_preview)} 個題目給 {assign_to}！")
                        st.cache_data.clear()
                else:
                    st.warning("查無符合條件的錯題，請放寬篩選標準。")

# --- 6. 學生端任務接收 (優化題目解析) ---
st.title(f"👋 {st.session_state.user_name}")

if df_a is not None:
    my_tasks = df_a[(df_a['對象 (分組/姓名)'] == st.session_state.user_name) | 
                    (df_a['對象 (分組/姓名)'] == st.session_state.group_id) |
                    (df_a['對象 (分組/姓名)'] == "全體")]
    
    if not my_tasks.empty:
        task = my_tasks.iloc[-1]
        st.info(f"🎯 **任務**：{task['說明文字']}")
        if st.button("⚡ 開始執行老師指派的篩選任務", type="primary"):
            q_ids = str(task['題目ID清單']).split(', ')
            task_quiz = []
            for qid in q_ids:
                p = qid.split('_')
                if len(p) >= 5:
                    match = df_q[
                        (df_q['年度'] == int(p[0])) & 
                        (df_q['冊編號'] == int(p[1])) & 
                        (df_q['單元'] == p[2]) & 
                        (df_q['課編號'] == int(p[3])) & 
                        (df_q['句編號'] == int(p[4]))
                    ]
                    if not match.empty: task_quiz.append(match.iloc[0].to_dict())
            
            if task_quiz:
                st.session_state.quiz_list = task_quiz
                st.session_state.quiz_loaded = True
                reset_quiz()
                st.rerun()

# --- 7. 練習區邏輯 (同 V2.1) ---
if st.session_state.get('quiz_loaded') and not st.session_state.get('finished'):
    q = st.session_state.quiz_list[st.session_state.q_idx]
    st.session_state.current_qid = f"{int(q['年度'])}_{int(q['冊編號'])}_{q['單元']}_{int(q['課編號'])}_{int(q['句編號'])}"
    
    st.markdown(f'<div style="background:#f0f7ff; padding:20px; border-radius:10px; border-left:5px solid #007bff; margin-bottom:10px;">'
                f'<b>第 {st.session_state.q_idx + 1} 題 / 共 {len(st.session_state.quiz_list)} 題</b><br>'
                f'<span style="font-size:20px;">{q["中文"]}</span></div>', unsafe_allow_html=True)
    
    # [此處保留與 V2.1 相同的按鈕組與作答檢查邏輯]
    tokens = re.findall(r"[\w']+|[^\w\s]", str(q['英文']).strip())
    if not st.session_state.shuf: st.session_state.shuf = tokens.copy(); random.shuffle(st.session_state.shuf)
    
    st.markdown(f'<div style="background:white; padding:15px; border:1px solid #ddd; min-height:60px; font-size:22px; text-align:center;">'
                f'{" ".join(st.session_state.ans) if st.session_state.ans else "......"}</div>', unsafe_allow_html=True)
    
    st.write("---")
    cols = st.columns(2)
    for i, t in enumerate(st.session_state.shuf):
        if i not in st.session_state.used_history:
            if cols[i%2].button(t, key=f"btn_{i}", use_container_width=True):
                st.session_state.ans.append(t); st.session_state.used_history.append(i); st.rerun()

    c_btns = st.columns(2)
    if c_btns[0].button("🔄 重填", use_container_width=True): st.session_state.ans, st.session_state.used_history = [], []; st.rerun()
    if len(st.session_state.ans) == len(tokens):
        if c_btns[1].button("✅ 檢查答案", type="primary", use_container_width=True):
            is_ok = "".join(st.session_state.ans).lower() == str(q['英文']).replace(" ","").lower()
            log_event("作答", detail=" ".join(st.session_state.ans), result="✅" if is_ok else "❌")
            if is_ok:
                st.success("正確！自動前往下一題..."); time.sleep(1)
                if st.session_state.q_idx + 1 < len(st.session_state.quiz_list):
                    st.session_state.q_idx += 1; reset_quiz(); st.rerun()
                else: st.session_state.finished = True; st.rerun()
            else: st.error(f"正確答案: {q['英文']}")

elif st.session_state.get('finished'):
    st.balloons()
    st.success("✨ 任務完成！太棒了！")
    if st.button("回主選單"): st.session_state.quiz_loaded = False; st.rerun()

st.caption(f"Ver {VERSION}")

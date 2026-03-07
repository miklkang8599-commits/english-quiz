# ==============================================================================
# 🧩 英文重組練習旗艦版 V1.7.0
# ==============================================================================
# 功能說明:
# 1. 學生帳號登入系統 (EA+4位數)，支援分組識別。
# 2. 全校做題跑馬燈：即時抓取最新 logs 並滾動顯示。
# 3. 行為全紀錄：記錄作答結果、點擊功能鍵(退回/重填/換題)及花費時間。
# 4. 同組學習足跡：折疊式選單查看組員詳細進度與競爭榮譽榜。
# ==============================================================================

import streamlit as st
import pandas as pd
import random
import re
from datetime import datetime
from streamlit_gsheets import GSheetsConnection

VERSION = "1.7.0"

st.set_page_config(page_title=f"英文重組旗艦版 V{VERSION}", layout="centered")

# --- 1. 連線 Google Sheets ---
conn = st.connection("gsheets", type=GSheetsConnection)

# --- 2. CSS 樣式 (含跑馬燈動畫) ---
st.markdown(f"""
    <style>
    @keyframes marquee {{
        0% {{ transform: translateX(100%); }}
        100% {{ transform: translateX(-100%); }}
    }}
    .marquee-container {{
        background: #333; color: #00ff00; padding: 5px 0;
        overflow: hidden; white-space: nowrap; font-family: monospace;
    }}
    .marquee-text {{
        display: inline-block; animation: marquee 20s linear infinite;
        font-size: 16px;
    }}
    .hint-box {{
        background-color: #f8f9fa; padding: 15px; border-radius: 10px;
        border-left: 6px solid #1e88e5; font-size: 18px; margin-bottom: 15px;
    }}
    .stButton > button {{ border-radius: 8px; height: 48px; }}
    </style>
""", unsafe_allow_html=True)

# --- 3. 核心功能函數 ---

def load_all_data():
    """讀取題目與學生資料"""
    try:
        df_q = conn.read(worksheet="questions", ttl=30)
        df_s = conn.read(worksheet="students", ttl=30)
        return df_q.dropna(subset=['英文', '中文']), df_s
    except:
        st.error("讀取 Google Sheets 失敗，請檢查分頁名稱是否為 'questions' 與 'students'")
        return None, None

def log_event(action_type, detail="", result="-", duration=0):
    """背景寫入紀錄到 logs 分頁"""
    if not st.session_state.get('logged_in'): return
    try:
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        qid = st.session_state.get('current_qid', "N/A")
        new_row = pd.DataFrame([{
            "時間": now,
            "帳號": st.session_state.user_id,
            "姓名": st.session_state.user_name,
            "分組": st.session_state.group_id,
            "題目ID": qid,
            "動作": action_type,
            "內容": detail,
            "結果": result,
            "費時": duration
        }])
        # 使用 append 模式寫入 (需要實作或是使用 conn.create 邏輯)
        # 註: st.connection 的寫入邏輯視版本而定，以下為常見寫法
        existing_logs = conn.read(worksheet="logs", ttl=0)
        updated_logs = pd.concat([existing_logs, new_row], ignore_index=True)
        conn.update(worksheet="logs", data=updated_logs)
    except Exception as e:
        pass # 避免寫入失敗卡住學生

def get_marquee_text():
    """抓取最新 5 筆 ✅ 的紀錄做跑馬燈"""
    try:
        logs = conn.read(worksheet="logs", ttl=10)
        recent = logs[logs['結果'] == '✅'].tail(5)
        texts = [f"🔥 {row['姓名']}({row['分組']}) 剛答對了題號 {row['題目ID']}!" for _, row in recent.iterrows()]
        return " | ".join(texts) if texts else "🏃 大家都還在熱身中，加油！"
    except: return "跑馬燈連線中..."

# --- 4. 登入邏輯 ---
if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False

if not st.session_state.logged_in:
    st.title("🧩 學生學習系統登入")
    st.info("請輸入您的 4 位數帳號與密碼")
    
    col1, col2 = st.columns([1, 4])
    col1.markdown("### EA")
    input_id = col2.text_input("帳號 (4位數字)", max_chars=4, placeholder="0003")
    input_pw = st.text_input("密碼 (4位數字)", type="password", max_chars=4)
    
    if st.button("確認登入", type="primary", use_container_width=True):
        _, df_s = load_all_data()
        if df_s is not None:
            # 轉換為字串比對，避免格式問題
            user = df_s[df_s['帳號'].astype(str).str.zfill(4) == input_id.zfill(4)]
            if not user.empty and str(user.iloc[0]['密碼']).zfill(4) == input_pw.zfill(4):
                st.session_state.logged_in = True
                st.session_state.user_id = f"EA{input_id.zfill(4)}"
                st.session_state.user_name = user.iloc[0]['姓名']
                st.session_state.group_id = user.iloc[0]['分組']
                st.rerun()
            else:
                st.error("帳號或密碼錯誤，請重新輸入")
    st.stop()

# --- 5. 正式練習畫面 ---

# 跑馬燈
marquee_content = get_marquee_text()
st.markdown(f'<div class="marquee-container"><div class="marquee-text">{marquee_content}</div></div>', unsafe_allow_html=True)

df_q, _ = load_all_data()

# 初始化練習狀態
if 'q_idx' not in st.session_state:
    st.session_state.q_idx = 0
    st.session_state.ans = []
    st.session_state.used_history = []
    st.session_state.shuf = []
    st.session_state.history = {}
    st.session_state.finished = False
    st.session_state.start_time = datetime.now()

# 範圍篩選
with st.sidebar:
    st.title(f"👋 你好, {st.session_state.user_name}")
    st.write(f"分組: **{st.session_state.group_id}**")
    st.divider()
    
    if st.button("🚪 登出"):
        st.session_state.logged_in = False
        st.rerun()

    st.subheader("📊 組員足跡")
    with st.expander("查看同組動態"):
        try:
            all_logs = conn.read(worksheet="logs", ttl=10)
            group_logs = all_logs[all_logs['分組'] == st.session_state.group_id].tail(10)
            st.table(group_logs[['姓名', '動作', '結果']])
        except: st.write("尚無足跡紀錄")

if df_q is not None:
    # 練習範圍設定 (簡化版，連動 Session)
    with st.expander("⚙️ 練習範圍與題數設定", expanded=False):
        lessons = sorted(df_q['課編號'].unique().tolist())
        sel_l = st.selectbox("選擇課次", lessons)
        quiz_list = df_q[df_q['課編號'] == sel_l].to_dict('records')

    if quiz_list and not st.session_state.finished:
        q = quiz_list[st.session_state.q_idx]
        # 產生唯一識別碼 QID
        qid = f"{q.get('年度','0')}_{q.get('冊編號','0')}_{q.get('課編號','0')}_{q.get('句編號','0')}"
        st.session_state.current_qid = qid
        
        eng_raw = str(q['英文']).strip()
        correct_tokens = re.findall(r"[\w']+|[^\w\s]", eng_raw)

        if not st.session_state.shuf:
            tmp = correct_tokens.copy()
            random.shuffle(tmp)
            st.session_state.shuf = tmp

        # 題目區
        st.markdown(f'<div class="hint-box">題號 {st.session_state.q_idx + 1} (句編號 {q.get("句編號")}) &nbsp;&nbsp; {q["中文"]}</div>', unsafe_allow_html=True)
        
        # 拼湊顯示
        res_str = " ".join(st.session_state.ans)
        st.markdown(f'<div style="background:#fff; padding:20px; border-radius:10px; border:1px solid #ddd; min-height:80px; font-size:22px; margin-bottom:15px; text-align:center;">{res_str if res_str else "......"}</div>', unsafe_allow_html=True)

        # 底部功能鍵 (記錄行為)
        nav_cols = st.columns(4)
        if nav_cols[0].button("退回"):
            if st.session_state.ans:
                st.session_state.ans.pop(); st.session_state.used_history.pop()
                log_event("按鍵:退回")
                st.rerun()
        if nav_cols[1].button("重填"):
            st.session_state.ans, st.session_state.used_history = [], []
            log_event("按鍵:重填")
            st.rerun()
        if nav_cols[2].button("上一題", disabled=(st.session_state.q_idx == 0)):
            st.session_state.q_idx -= 1
            st.session_state.ans, st.session_state.used_history, st.session_state.shuf = [], [], []
            log_event("導覽:上一題")
            st.rerun()
        if nav_cols[3].button("下一題"):
            if st.session_state.q_idx + 1 < len(quiz_list):
                st.session_state.q_idx += 1
                st.session_state.ans, st.session_state.used_history, st.session_state.shuf = [], [], []
                log_event("導覽:下一題")
                st.rerun()

        # 單字按鈕
        st.write("---")
        btn_cols = st.columns(2)
        for idx, token in enumerate(st.session_state.shuf):
            if idx not in st.session_state.used_history:
                with btn_cols[idx % 2]:
                    if st.button(token, key=f"t_{idx}", use_container_width=True):
                        st.session_state.ans.append(token)
                        st.session_state.used_history.append(idx)
                        st.rerun()

        # 檢查答案
        if len(st.session_state.ans) == len(correct_tokens):
            if st.button("✅ 檢查答案", type="primary", use_container_width=True):
                duration = (datetime.now() - st.session_state.start_time).seconds
                is_ok = "".join(st.session_state.ans).lower() == eng_raw.replace(" ", "").lower()
                result_tag = "✅" if is_ok else "❌"
                
                # 寫入日誌
                log_event("作答", detail=" ".join(st.session_state.ans), result=result_tag, duration=duration)
                
                if is_ok:
                    st.success("Correct! 🎉")
                    st.balloons()
                else:
                    st.error(f"再試一次！正確答案是: {eng_raw}")
                st.session_state.start_time = datetime.now() # 重置計時

st.caption(f"Flagship Ver {VERSION}")

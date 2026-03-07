# ==============================================================================
# 🧩 程式版本資訊 (VERSION HISTORY)
# ==============================================================================
# 版本編號: 1.6.1
# 更新日期: 2026-03-07
# 功能說明:
# 1. 修正「練習範圍設定」消失問題，恢復年度、冊別、單元、課次篩選。
# 2. 底部功能鍵完全對齊截圖：【退回、重填、上一題、下一題】四鍵併排。
# 3. 調整按鈕間距與字體大小，確保在手機直立模式下不重疊且易於點選。
# 4. 拼湊空格區採用底線強化視覺感，模擬填空練習。
# ==============================================================================

import streamlit as st
import pandas as pd
import random
import re

VERSION = "1.6.1"

st.set_page_config(page_title=f"英文重組 V{VERSION}", layout="centered")

# CSS 手機版面極致對齊
st.markdown(f"""
    <style>
    /* 中文提示區塊 */
    .hint-box {{
        background-color: #f8f9fa;
        padding: 12px;
        border-radius: 8px;
        color: #333;
        font-weight: bold;
        font-size: 16px;
        margin-bottom: 10px;
        border-left: 5px solid #2196f3;
    }}
    /* 拼湊空格區塊 */
    .answer-display {{
        background-color: #ffffff;
        padding: 15px;
        border-radius: 8px;
        border: 1px solid #dee2e6;
        min-height: 70px;
        display: flex;
        flex-wrap: wrap;
        gap: 8px;
        align-items: center;
        justify-content: center;
        font-size: 20px;
        margin-bottom: 15px;
    }}
    /* 下方四個功能鍵 */
    .nav-btn > div > button {{
        height: 45px !important;
        font-size: 14px !important;
        padding: 0px !important;
        border-radius: 5px !important;
    }}
    /* 單字按鈕 */
    .word-btn > div > button {{
        font-size: 18px !important;
        height: 48px !important;
        margin-bottom: 5px !important;
        border-radius: 10px !important;
        background-color: #f1f3f4 !important;
        border: 1px solid #dadce0 !important;
    }}
    </style>
""", unsafe_allow_html=True)

# 1. 資料讀取
SHEET_ID = "1zVUNGboZALvK3val1RSbCQvEESLRSNEulqpNSzsPJ14"
GID = "176577556"
url = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/export?format=csv&gid={GID}"

@st.cache_data(ttl=60)
def load_data():
    try:
        df = pd.read_csv(url)
        df.columns = [str(c).strip() for c in df.columns]
        for col in ['年度', '冊編號', '課編號', '句編號']:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce')
        return df.dropna(subset=['英文', '中文'])
    except: return None

def reset_all_state():
    st.session_state.q_idx = 0
    st.session_state.ans = []
    st.session_state.used_history = []
    st.session_state.shuf = []
    st.session_state.history = {}
    st.session_state.finished = False
    st.session_state.is_correct = False
    st.session_state.check_clicked = False

if 'q_idx' not in st.session_state: reset_all_state()

df = load_data()

# --- 主標題 ---
st.title("🧩 英文句子重組練習")

if df is not None:
    # --- 頂部：範圍設定 (確保顯示) ---
    with st.expander("📖 練習範圍設定", expanded=True):
        c1, c2 = st.columns(2)
        years = sorted(df['年度'].unique().astype(int).tolist()) if '年度' in df.columns else [0]
        sel_y = c1.selectbox("年度", years)
        df_y = df[df['年度'] == sel_y]
        
        books = sorted(df_y['冊編號'].unique().astype(int).tolist())
        sel_b = c2.selectbox("冊別", books)
        df_b = df_y[df_y['冊編號'] == sel_b]
        
        c3, c4 = st.columns(2)
        units = sorted(df_b['單元'].unique().tolist()) if '單元' in df.columns else ["預設"]
        sel_u = c3.selectbox("單元", units)
        df_u = df_b[df_b['單元'] == sel_u]
        
        lessons = sorted(df_u['課編號'].unique().astype(int).tolist())
        sel_l = c4.selectbox("課次", lessons)
        
        base_df = df_u[df_u['課編號'] == sel_l].sort_values('句編號')
        
        if not base_df.empty:
            start_id = st.number_input(f"起始句號", int(base_df['句編號'].min()), int(base_df['句編號'].max()))
            num_q = st.slider("題數", 1, len(base_df[base_df['句編號']>=start_id]), 5)
            quiz_list = base_df[base_df['句編號']>=start_id].head(num_q).to_dict('records')

            # 檢測設定是否變動
            curr_key = f"{sel_y}-{sel_b}-{sel_u}-{sel_l}-{start_id}-{num_q}"
            if st.session_state.get('last_config_key') != curr_key:
                st.session_state.last_config_key = curr_key
                reset_all_state()
                st.rerun()

    if not base_df.empty and not st.session_state.finished:
        if st.session_state.q_idx < len(quiz_list):
            q = quiz_list[st.session_state.q_idx]
            eng_raw = str(q['英文']).strip()
            correct_tokens = re.findall(r"[\w']+|[^\w\s]", eng_raw)

            if not st.session_state.shuf:
                tmp = correct_tokens.copy()
                random.shuffle(tmp)
                st.session_state.shuf = tmp

            # 1. 中文提示
            st.markdown(f'<div class="hint-box">Q{st.session_state.q_idx + 1} | {q["中文"]}</div>', unsafe_allow_html=True)

            # 2. 拼湊區
            res_str = " ".join(st.session_state.ans)
            st.markdown(f'<div class="answer-display">{res_str if res_str else "......"}</div>', unsafe_allow_html=True)

            # 3. 底部四功能鍵 (退回、重填、上一題、下一題)
            st.write("---")
            nav_cols = st.columns(4)
            
            with nav_cols[0]:
                if st.button("退回", key="btn_undo"):
                    if st.session_state.used_history:
                        st.session_state.used_history.pop()
                        st.session_state.ans.pop()
                        st.session_state.check_clicked = False
                        st.rerun()
            
            with nav_cols[1]:
                if st.button("重填", key="btn_clear"):
                    st.session_state.ans, st.session_state.used_history, st.session_state.check_clicked = [], [], False
                    st.rerun()
            
            with nav_cols[2]:
                if st.button("上一題", key="btn_prev", disabled=(st.session_state.q_idx == 0)):
                    st.session_state.q_idx -= 1
                    st.session_state.ans, st.session_state.used_history, st.session_state.shuf, st.session_state.is_correct, st.session_state.check_clicked = [], [], [], False, False
                    st.rerun()
                    
            with nav_cols[3]:
                is_last = (st.session_state.q_idx + 1 == len(quiz_list))
                if st.button("下一題", key="btn_next"):
                    if not is_last:
                        st.session_state.q_idx += 1
                        st.session_state.ans, st.session_state.used_history, st.session_state.shuf, st.session_state.is_correct, st.session_state.check_clicked = [], [], [], False, False
                        st.rerun()
                    else:
                        st.session_state.finished = True
                        st.rerun()

            # 4. 單字按鈕區
            st.write("---")
            btn_cols = st.columns(2)
            for idx, token in enumerate(st.session_state.shuf):
                if idx not in st.session_state.used_history:
                    with btn_cols[idx % 2]:
                        st.markdown('<div class="word-btn">', unsafe_allow_html=True)
                        if st.button(token, key=f"t_{idx}", use_container_width=True):
                            st.session_state.ans.append(token)
                            st.session_state.used_history.append(idx)
                            st.session_state.check_clicked = False
                            st.rerun()
                        st.markdown('</div>', unsafe_allow_html=True)

            # 5. 檢查答案
            if len(st.session_state.ans) == len(correct_tokens) and not st.session_state.is_correct:
                if st.button("✅ 檢查答案", type="primary", use_container_width=True):
                    st.session_state.check_clicked = True
                    user_f = "".join(st.session_state.ans).lower()
                    target_f = eng_raw.replace(" ", "").lower()
                    st.session_state.is_correct = (user_f == target_f)
                    st.session_state.history[st.session_state.q_idx] = {
                        "題號": q['句編號'], "正確答案": eng_raw, "狀態": "✅" if st.session_state.is_correct else "❌"
                    }
                    if st.session_state.is_correct:
                        t_url = f"https://translate.google.com/translate_tts?ie=UTF-8&tl=en&client=tw-ob&q={eng_raw.replace(' ', '%20')}"
                        st.markdown(f'<audio autoplay src="{t_url}"></audio>', unsafe_allow_html=True)
                    st.rerun()
            
            if st.session_state.is_correct:
                st.success("Correct! 🎉")

    else:
        st.header("🎊 練習成果回顧")
        if st.session_state.history:
            st.table(pd.DataFrame([v for k, v in sorted(st.session_state.history.items())]))
        if st.button("🔄 重新開始練習"): reset_all_state(); st.rerun()

st.caption(f"Ver {VERSION}")

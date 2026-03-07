# ==============================================================================
# 🧩 程式版本資訊 (VERSION HISTORY)
# ==============================================================================
# 版本編號: 1.6.6
# 更新日期: 2026-03-07
# 功能說明:
# 1. 版面優化：將「題號/句編號」與「題目內容」恢復至同一列顯示以節省空間。
# 2. 間距調整：在編號與內容之間加入三個全形空格，解決視覺過於擁擠的問題。
# 3. 穩定讀取：延續 V1.6.4 的「句編號」精確抓取與欄位標準化邏輯。
# 4. 介面同步：底部四功能鍵【退回、重填、上一題、下一題】維持手機最優併排佈局。
# ==============================================================================

import streamlit as st
import pandas as pd
import random
import re

VERSION = "1.6.6"

st.set_page_config(page_title=f"英文重組 V{VERSION}", layout="centered")

# CSS 樣式優化
st.markdown(f"""
    <style>
    .hint-box {{
        background-color: #f8f9fa;
        padding: 15px 20px;
        border-radius: 10px;
        color: #333;
        font-weight: bold;
        border-left: 6px solid #1e88e5;
        font-size: 18px;
        margin-bottom: 15px;
        line-height: 1.4;
    }}
    .q-meta {{
        color: #1e88e5;
        font-size: 16px;
        margin-right: 15px; /* 增加編號後的右側間距 */
    }}
    .answer-display {{
        background-color: #ffffff;
        padding: 20px;
        border-radius: 10px;
        border: 1px solid #dee2e6;
        min-height: 80px;
        display: flex;
        flex-wrap: wrap;
        gap: 10px;
        align-items: center;
        justify-content: center;
        font-size: 22px;
        margin-bottom: 15px;
    }}
    .word-btn > div > button {{
        font-size: 19px !important;
        height: 52px !important;
        background-color: #fdfdfd !important;
        border: 2px solid #eaebed !important;
    }}
    </style>
""", unsafe_allow_html=True)

# 1. 資料讀取
SHEET_ID = "1zVUNGboZALvK3val1RSbCQvEESLRSNEulqpNSzsPJ14"
GID = "176577556"
url = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/export?format=csv&gid={GID}"

@st.cache_data(ttl=30)
def load_data():
    try:
        df = pd.read_csv(url)
        df.columns = [str(c).strip() for c in df.columns]
        for col in ['年度', '冊編號', '課編號', '句編號']:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col].astype(str).str.strip(), errors='coerce')
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

st.title("🧩 英文句子重組練習")

if df is not None:
    # --- 範圍設定 ---
    with st.expander("⚙️ 練習範圍設定", expanded=True):
        c1, c2 = st.columns(2)
        years = sorted(df['年度'].dropna().unique().astype(int).tolist()) if '年度' in df.columns else [0]
        sel_y = c1.selectbox("年度", years)
        df_y = df[df['年度'] == sel_y]
        
        books = sorted(df_y['冊編號'].dropna().unique().astype(int).tolist())
        sel_b = c2.selectbox("冊別", books)
        df_b = df_y[df_y['冊編號'] == sel_b]
        
        c3, c4 = st.columns(2)
        units = sorted(df_b['單元'].dropna().unique().tolist()) if '單元' in df.columns else ["預設"]
        sel_u = c3.selectbox("單元", units)
        df_u = df_b[df_b['單元'] == sel_u]
        
        lessons = sorted(df_u['課編號'].dropna().unique().astype(int).tolist())
        sel_l = c4.selectbox("課次", lessons)
        
        base_df = df_u[df_u['課編號'] == sel_l].sort_values('句編號')
        
        if not base_df.empty:
            min_s = int(base_df['句編號'].min())
            max_s = int(base_df['句編號'].max())
            start_id = st.number_input(f"起始句編號", min_s, max_s, min_s)
            
            valid_quiz = base_df[base_df['句編號'] >= start_id]
            num_q = st.slider("測驗題數", 1, len(valid_quiz), min(10, len(valid_quiz)))
            quiz_list = valid_quiz.head(num_q).to_dict('records')

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

            # --- 題目顯示區：單列寬間距格式 ---
            q_num = st.session_state.q_idx + 1
            s_num = int(q['句編號']) if pd.notnull(q.get('句編號')) else 0
            
            # 使用 &nbsp; (不換行空格) 來增加間距
            st.markdown(f"""
                <div class="hint-box">
                    <span class="q-meta">題號 {q_num} (句編號 {s_num})</span>&nbsp;&nbsp;&nbsp;{q['中文']}
                </div>
            """, unsafe_allow_html=True)

            # 拼湊顯示區
            res_str = " ".join(st.session_state.ans)
            st.markdown(f'<div class="answer-display">{res_str if res_str else "......"}</div>', unsafe_allow_html=True)

            # 功能鍵
            nav_cols = st.columns(4)
            with nav_cols[0]:
                if st.button("退回", key="btn_undo"):
                    if st.session_state.used_history:
                        st.session_state.used_history.pop(); st.session_state.ans.pop()
                        st.session_state.check_clicked = False; st.rerun()
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
                if st.button("下一題", key="btn_next"):
                    if st.session_state.q_idx + 1 < len(quiz_list):
                        st.session_state.q_idx += 1
                        st.session_state.ans, st.session_state.used_history, st.session_state.shuf, st.session_state.is_correct, st.session_state.check_clicked = [], [], [], False, False
                        st.rerun()
                    else:
                        st.session_state.finished = True; st.rerun()

            st.write("---")
            # 單字按鈕
            btn_cols = st.columns(2)
            for idx, token in enumerate(st.session_state.shuf):
                if idx not in st.session_state.used_history:
                    with btn_cols[idx % 2]:
                        st.markdown('<div class="word-btn">', unsafe_allow_html=True)
                        if st.button(token, key=f"t_{idx}", use_container_width=True):
                            st.session_state.ans.append(token)
                            st.session_state.used_history.append(idx)
                            st.session_state.check_clicked = False; st.rerun()
                        st.markdown('</div>', unsafe_allow_html=True)

            # 檢查按鈕
            if len(st.session_state.ans) == len(correct_tokens) and not st.session_state.is_correct:
                if st.button("✅ 檢查答案", type="primary", use_container_width=True):
                    st.session_state.check_clicked = True
                    is_ok = "".join(st.session_state.ans).lower() == eng_raw.replace(" ", "").lower()
                    st.session_state.is_correct = is_ok
                    st.session_state.history[st.session_state.q_idx] = {
                        "題目": q_num, "句編號": s_num, "狀態": "✅" if is_ok else "❌", "正確答案": eng_raw
                    }
                    if is_ok:
                        t_url = f"https://translate.google.com/translate_tts?ie=UTF-8&tl=en&client=tw-ob&q={eng_raw.replace(' ', '%20')}"
                        st.markdown(f'<audio autoplay src="{t_url}"></audio>', unsafe_allow_html=True)
                    st.rerun()
            
            if st.session_state.is_correct:
                st.success("Correct! 🎉")

            if st.button("🏁 查看結果報告", type="secondary", use_container_width=True):
                st.session_state.finished = True; st.rerun()
    else:
        st.header("🎊 練習成果回顧")
        if st.session_state.history:
            st.table(pd.DataFrame([v for k, v in sorted(st.session_state.history.items())]))
        if st.button("🔄 重新開始練習"): reset_all_state(); st.rerun()

st.caption(f"Ver {VERSION}")

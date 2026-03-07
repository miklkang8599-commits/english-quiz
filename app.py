# ==============================================================================
# 🧩 程式版本資訊 (VERSION HISTORY)
# ==============================================================================
# 版本編號: 1.5.3
# 更新日期: 2026-03-07
# 功能說明:
# 1. 空間優化：將「上一題/下一題」與「退回/重填」改為緊湊的兩列式佈局，節省手機畫面空間。
# 2. 移除冗餘間距，讓單字按鈕區更接近輸入區。
# 3. 修正拼湊顯示區的 HTML 渲染邏輯，防止代碼洩漏。
# 4. 版本資訊保留於程式碼註解中，執行畫面僅顯示簡約版號。
# ==============================================================================

import streamlit as st
import pandas as pd
import random
import re

VERSION = "1.5.3"

st.set_page_config(page_title=f"英文重組 V{VERSION}", layout="centered")

# CSS 極致節省空間樣式
st.markdown(f"""
    <style>
    .stButton > button {{
        width: 100%;
        border-radius: 10px;
        font-weight: bold;
        height: 48px;
        font-size: 15px !important;
        padding: 0px;
    }}
    .answer-box {{
        font-size: 20px;
        color: #1e40af;
        background-color: #eff6ff;
        padding: 15px;
        border-radius: 12px;
        border: 2px dashed #3b82f6;
        margin: 5px 0;
        min-height: 80px;
    }}
    .ver-tag {{
        text-align: right;
        color: #9ca3af;
        font-size: 10px;
        margin-top: 20px;
    }}
    /* 縮減區塊間距 */
    .block-container {{
        padding-top: 2rem !important;
        padding-bottom: 1rem !important;
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

# --- 主標題與版號 ---
st.title("🧩 英文句子重組")
st.caption(f"Ver {VERSION}")

if df is not None:
    # --- 範圍設定 (預設收合以節省空間) ---
    with st.expander("📖 範圍設定", expanded=not st.session_state.get('history')):
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

            key = f"{sel_y}-{sel_b}-{sel_u}-{sel_l}-{start_id}-{num_q}"
            if st.session_state.get('last_key') != key:
                st.session_state.last_key = key
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

            st.write(f"**Q{st.session_state.q_idx + 1}/{len(quiz_list)}** | {q['中文']}")

            # 拼湊顯示區
            res_str = " ".join(st.session_state.ans)
            display_text = res_str if res_str else "請點選單字..."
            st.markdown(f'<div class="answer-box">{display_text}</div>', unsafe_allow_html=True)

            # --- 核心功能鍵：同一排佈局 ---
            # 第一排：導覽 (上一題 / 下一題)
            n1, n2 = st.columns(2)
            with n1:
                if st.button("⬅️ 上一題", key="top_prev", disabled=(st.session_state.q_idx == 0)):
                    st.session_state.q_idx -= 1
                    st.session_state.ans, st.session_state.used_history, st.session_state.shuf, st.session_state.is_correct, st.session_state.check_clicked = [], [], [], False, False
                    st.rerun()
            with n2:
                btn_label = "下一題 ➡️" if st.session_state.q_idx + 1 < len(quiz_list) else "🏁 完成"
                if st.button(btn_label, key="top_next"):
                    if st.session_state.q_idx + 1 < len(quiz_list):
                        st.session_state.q_idx += 1
                        st.session_state.ans, st.session_state.used_history, st.session_state.shuf, st.session_state.is_correct, st.session_state.check_clicked = [], [], [], False, False
                        st.rerun()
                    else:
                        st.session_state.finished = True
                        st.rerun()

            # 第二排：編輯 (退回 / 重填)
            e1, e2 = st.columns(2)
            with e1:
                if st.button("↺ 退回一步", key="undo"):
                    if st.session_state.used_history:
                        st.session_state.used_history.pop()
                        st.session_state.ans.pop()
                        st.session_state.check_clicked = False
                        st.rerun()
            with e2:
                if st.button("🗑️ 全部重填", key="clear"):
                    st.session_state.ans, st.session_state.used_history, st.session_state.check_clicked = [], [], False
                    st.rerun()

            st.write("---")
            # 單字按鈕
            if not st.session_state.is_correct:
                btn_cols = st.columns(3)
                for idx, token in enumerate(st.session_state.shuf):
                    if idx not in st.session_state.used_history:
                        if btn_cols[idx % 3].button(token, key=f"t_{idx}"):
                            st.session_state.ans.append(token)
                            st.session_state.used_history.append(idx)
                            st.session_state.check_clicked = False
                            st.rerun()

            # 檢查按鈕
            if len(st.session_state.ans) == len(correct_tokens) and not st.session_state.is_correct:
                if st.button("✅ 檢查答案", type="primary"):
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

            if st.button("🛑 提前看報告", type="secondary"):
                st.session_state.finished = True
                st.rerun()

    else:
        st.header("🎊 練習成果回顧")
        if st.session_state.history:
            st.table(pd.DataFrame([v for k, v in sorted(st.session_state.history.items())]))
        if st.button("🔄 重新開始練習"): reset_all_state(); st.rerun()

st.markdown(f'<p class="ver-tag">App Ver {VERSION}</p>', unsafe_allow_html=True)

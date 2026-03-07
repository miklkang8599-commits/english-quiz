import streamlit as st
import pandas as pd
import random
import re

# ==========================================
# 程式版本資訊 (僅紀錄，主畫面隱藏說明)
# ==========================================
VERSION = "1.5.1"

st.set_page_config(page_title=f"英文重組練習 V{VERSION}", layout="centered")

# CSS 手機直立版面優化
st.markdown(f"""
    <style>
    .stButton > button {{
        width: 100%;
        border-radius: 12px;
        font-weight: bold;
        height: 55px;
        margin-bottom: 8px;
        font-size: 18px !important;
    }}
    .answer-box {{
        font-size: 22px;
        color: #1e40af;
        background-color: #eff6ff;
        padding: 18px;
        border-radius: 15px;
        border: 2px dashed #3b82f6;
        margin: 15px 0;
        min-height: 100px;
        word-wrap: break-word;
        text-align: left;
    }}
    .ver-tag {{
        text-align: right;
        color: #9ca3af;
        font-size: 12px;
        margin-top: 20px;
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

# 初始化
if 'q_idx' not in st.session_state: reset_all_state()

df = load_data()

# --- 執行畫面表頭 ---
st.title("🧩 英文句子重組練習")
st.caption(f"版本編號：V{VERSION}")

if df is not None:
    # --- 頂部：範圍設定 ---
    with st.expander("📖 練習範圍設定", expanded=True):
        c1, c2 = st.columns(2)
        years = sorted(df['年度'].unique().astype(int).tolist()) if '年度' in df.columns else [0]
        sel_y = c1.selectbox("1. 年度", years)
        df_y = df[df['年度'] == sel_y]
        
        books = sorted(df_y['冊編號'].unique().astype(int).tolist())
        sel_b = c2.selectbox("2. 冊別", books)
        df_b = df_y[df_y['冊編號'] == sel_b]
        
        c3, c4 = st.columns(2)
        units = sorted(df_b['單元'].unique().tolist()) if '單元' in df.columns else ["預設"]
        sel_u = c3.selectbox("3. 單元", units)
        df_u = df_b[df_b['單元'] == sel_u]
        
        lessons = sorted(df_u['課編號'].unique().astype(int).tolist())
        sel_l = c4.selectbox("4. 課次", lessons)
        
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

    if not base_df.empty and st.session_state.q_idx < len(quiz_list):
        if not st.session_state.finished:
            q = quiz_list[st.session_state.q_idx]
            eng_raw = str(q['英文']).strip()
            correct_tokens = re.findall(r"[\w']+|[^\w\s]", eng_raw)

            if not st.session_state.shuf:
                tmp = correct_tokens.copy()
                random.shuffle(tmp)
                st.session_state.shuf = tmp

            st.write(f"**Question {st.session_state.q_idx + 1} / {len(quiz_list)}**")
            st.info(f"💡 {q['中文']}")

            # --- 修正後的拼湊顯示區 ---
            res_str = " ".join(st.session_state.ans)
            display_text = res_str if res_str else "請點選下方單字開始拼湊..."
            st.markdown(f'<div class="answer-box">{display_text}</div>', unsafe_allow_html=True)

            # 功能鍵：退回/重填
            f1, f2 = st.columns(2)
            if f1.button("⬅️ 退回", key="undo"):
                if st.session_state.used_history:
                    st.session_state.used_history.pop()
                    st.session_state.ans.pop()
                    st.session_state.check_clicked = False
                    st.rerun()
            if f2.button("🔄 重填", key="clear"):
                st.session_state.ans, st.session_state.used_history, st.session_state.check_clicked = [], [], False
                st.rerun()

            # 單字按鈕區
            st.write("---")
            btn_cols = st.columns(3)
            for idx, token in enumerate(st.session_state.shuf):
                if idx not in st.session_state.used_history:
                    if btn_cols[idx % 3].button(token, key=f"token_{idx}"):
                        st.session_state.ans.append(token)
                        st.session_state.used_history.append(idx)
                        st.session_state.check_clicked = False
                        st.rerun()

            st.write("---")
            
            # 檢查按鈕與判定
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

            # --- 導覽鍵：上一題 / 下一題 (保證出現) ---
            st.write("---")
            nav1, nav2 = st.columns(2)
            
            if st.session_state.q_idx > 0:
                if nav1.button("⬅️ 上一題", key="prev_btn"):
                    st.session_state.q_idx -= 1
                    st.session_state.ans, st.session_state.used_history, st.session_state.shuf, st.session_state.is_correct, st.session_state.check_clicked = [], [], [], False, False
                    st.rerun()
            
            if st.session_state.is_correct or st.session_state.check_clicked or len(st.session_state.ans) == 0:
                if nav2.button("下一題 ➡️", type="primary", key="next_btn"):
                    if st.session_state.q_idx + 1 < len(quiz_list):
                        st.session_state.q_idx += 1
                        st.session_state.ans, st.session_state.used_history, st.session_state.shuf, st.session_state.is_correct, st.session_state.check_clicked = [], [], [], False, False
                        st.rerun()
                    else:
                        st.session_state.finished = True
                        st.rerun()

            if st.button("🛑 結束練習並看報告"):
                st.session_state.finished = True
                st.rerun()

        else:
            st.header("🎊 練習成果回顧")
            if st.session_state.history:
                st.table(pd.DataFrame([v for k, v in sorted(st.session_state.history.items())]))
            if st.button("🔄 重新開始"): reset_all_state(); st.rerun()
    else:
        st.header("🎊 練習成果回顧")
        if st.session_state.history:
            st.table(pd.DataFrame([v for k, v in sorted(st.session_state.history.items())]))
        if st.button("🔄 重新開始"): reset_all_state(); st.rerun()

st.markdown(f'<p class="ver-tag">Version {VERSION}</p>', unsafe_allow_html=True)

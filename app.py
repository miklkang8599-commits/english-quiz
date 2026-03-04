import streamlit as st
import pandas as pd
import random
import re

st.set_page_config(page_title="英文重組練習 - 邏輯修正版", layout="wide")

# 1. 資料讀取 (讀取您的 Google Sheets)
SHEET_ID = "1zVUNGboZALvK3val1RSbCQvEESLRSNEulqpNSzsPJ14"
GID = "176577556"
url = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/export?format=csv&gid={GID}"

@st.cache_data(ttl=60)
def load_data():
    try:
        df = pd.read_csv(url)
        df.columns = [str(c).strip() for c in df.columns]
        for col in ['冊編號', '課編號', '句編號']:
            df[col] = pd.to_numeric(df[col], errors='coerce')
        return df.dropna(subset=['英文', '中文'])
    except:
        return None

def reset_all_state():
    st.session_state.q_idx = 0
    st.session_state.ans = []
    st.session_state.used_history = []
    st.session_state.shuf = []
    st.session_state.history = {}
    st.session_state.finished = False
    st.session_state.is_correct = False
    st.session_state.has_started_quiz = False

if 'q_idx' not in st.session_state: reset_all_state()

df = load_data()

if df is not None:
    # --- 側邊欄設定 ---
    st.sidebar.header("⚙️ 練習範圍設定")
    b_vals = sorted(df['冊編號'].unique().astype(int).tolist())
    sel_b = st.sidebar.selectbox("1. 選擇冊別", b_vals)
    l_vals = sorted(df[df['冊編號']==sel_b]['課編號'].unique().astype(int).tolist())
    sel_l = st.sidebar.selectbox("2. 選擇課次", l_vals)
    
    base_df = df[(df['冊編號']==sel_b) & (df['課編號']==sel_l)].sort_values('句編號')
    
    if not base_df.empty:
        min_id = int(base_df['句編號'].min())
        max_id = int(base_df['句編號'].max())
        start_id = st.sidebar.number_input(f"3. 起始句編號", min_id, max_id, min_id)
        
        filtered_df = base_df[base_df['句編號'] >= start_id]
        total_available = len(filtered_df)
        num_q = st.sidebar.slider("4. 練習題數", 1, total_available, min(10, total_available))
        quiz_list = filtered_df.head(num_q).to_dict('records')

        # 換範圍自動重置
        key = f"{sel_b}-{sel_l}-{start_id}-{num_q}"
        if 'last_k' not in st.session_state or st.session_state.last_k != key:
            st.session_state.last_k = key
            reset_all_state()
            st.rerun()

        # 防作弊鎖定
        if len(st.session_state.ans) > 0 or st.session_state.q_idx > 0 or st.session_state.history:
            st.session_state.has_started_quiz = True

        if st.session_state.has_started_quiz and not st.session_state.finished:
            st.sidebar.warning("🔒 測驗已開始，預習模式已鎖定。")
            is_study_mode = False
        else:
            is_study_mode = st.sidebar.checkbox("📖 開啟預習模式", value=False)

        # --- 預習模式 ---
        if is_study_mode:
            st.header("📖 課文預習模式")
            for item in quiz_list:
                with st.expander(f"句編號 {item['句編號']}：{item['中文']}", expanded=True):
                    col_txt, col_btn = st.columns([4, 1])
                    col_txt.write(f"### {item['英文']}")
                    t_url = f"https://translate.google.com/translate_tts?ie=UTF-8&tl=en&client=tw-ob&q={str(item['英文']).replace(' ', '%20')}"
                    col_btn.write(f'[🔊 播放]({t_url})')

        # --- 測驗主畫面 ---
        elif not st.session_state.finished and st.session_state.q_idx < len(quiz_list):
            q = quiz_list[st.session_state.q_idx]
            eng_raw = str(q['英文']).strip()
            # 統一拆解標點為獨立按鈕
            correct_tokens = re.findall(r"[\w']+|[^\w\s]", eng_raw)

            if not st.session_state.shuf:
                tmp = correct_tokens.copy()
                random.shuffle(tmp)
                st.session_state.shuf = tmp

            st.title(f"Question {st.session_state.q_idx + 1} / {len(quiz_list)}")
            st.info(f"💡 中文：{q['中文']}")

            st.write("### 拼湊結果：")
            res_str = " ".join(st.session_state.ans)
            st.markdown(f'<div style="font-size:24px; color:#1e40af; background-color:#eff6ff; padding:20px; border-radius:12px; border:2px dashed #3b82f6; min-height:80px;">{res_str if res_str else "點選單字按鈕..."}</div>', unsafe_allow_html=True)

            c1, c2, c3 = st.columns([1, 1, 2])
            if not st.session_state.is_correct:
                if c1.button("🔄 全部重填", use_container_width=True):
                    st.session_state.ans, st.session_state.used_history = [], []
                    st.rerun()
                if c2.button("⬅️ 退回一步", use_container_width=True):
                    if st.session_state.used_history:
                        st.session_state.used_history.pop()
                        st.session_state.ans.pop()
                        st.rerun()

            if c3.button("⏭️ 跳過此題", use_container_width=True):
                st.session_state.history[st.session_state.q_idx] = {
                    "題號": st.session_state.q_idx + 1, "中文提示": q['中文'], "正確答案": eng_raw,
                    "你的拼湊": " ".join(st.session_state.ans) if st.session_state.ans else "(已跳過)", "狀態": "❌ 跳過"
                }
                st.session_state.q_idx += 1
                st.session_state.ans, st.session_state.used_history, st.session_state.shuf = [], [], []
                st.session_state.is_correct = False
                st.rerun()

            st.write("---")
            if not st.session_state.is_correct:
                cols = st.columns(6)
                for i, t in enumerate(st.session_state.shuf):
                    if i not in st.session_state.used_history:
                        with cols[i % 6]:
                            if st.button(t, key=f"b_{i}", use_container_width=True):
                                st.session_state.ans.append(t)
                                st.session_state.used_history.append(i)
                                st.rerun()

            # --- 核心檢查邏輯修正 ---
            if len(st.session_state.ans) == len(correct_tokens):
                if not st.session_state.is_correct:
                    if st.button("✅ 檢查答案", type="primary", use_container_width=True):
                        # 修正：移除所有空格後進行不分大小寫的比對
                        user_flat = "".join(st.session_state.ans).lower()
                        target_flat = eng_raw.replace(" ", "").lower()
                        
                        is_ok = (user_flat == target_flat)
                        st.session_state.is_correct = is_ok
                        
                        st.session_state.history[st.session_state.q_idx] = {
                            "題號": st.session_state.q_idx + 1, "中文提示": q['中文'], "正確答案": eng_raw,
                            "你的拼湊": " ".join(st.session_state.ans), "狀態": "✅ 正確" if is_ok else "❌ 錯誤"
                        }
                        if is_ok:
                            t_url = f"https://translate.google.com/translate_tts?ie=UTF-8&tl=en&client=tw-ob&q={eng_raw.replace(' ', '%20')}"
                            st.markdown(f'<audio autoplay src="{t_url}"></audio>', unsafe_allow_html=True)
                        st.rerun()
                else:
                    st.success("完全正確！🎉")
                    if st.button("下一題 Next ➡️", type="primary", use_container_width=True):
                        st.session_state.q_idx += 1
                        st.session_state.ans, st.session_state.used_history, st.session_state.shuf = [], [], []
                        st.session_state.is_correct = False
                        st.rerun()
            
            if len(st.session_state.ans) == len(correct_tokens) and not st.session_state.is_correct:
                st.error("順序不對喔！請修正後再次檢查。")

            if st.sidebar.button("🛑 提前結束並查看結果", type="primary"):
                if st.session_state.q_idx not in st.session_state.history:
                    st.session_state.history[st.session_state.q_idx] = {
                        "題號": st.session_state.q_idx + 1, "中文提示": q['中文'], "正確答案": eng_raw,
                        "你的拼湊": " ".join(st.session_state.ans) if st.session_state.ans else "(未完成)", "狀態": "未完成"
                    }
                st.session_state.finished = True
                st.rerun()

        # --- 成果回顧 ---
        else:
            st.header("🎊 練習成果回顧")
            if st.session_state.history:
                final_history = [v for k, v in sorted(st.session_state.history.items())]
                st.table(pd.DataFrame(final_history))
            if st.button("🔄 重新開始練習 (徹底清空進度)"):
                reset_all_state()
                st.rerun()

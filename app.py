import streamlit as st
import pandas as pd
import random
import re

st.set_page_config(page_title="英文重組練習 - 即時紀錄版", layout="wide")

# CSS 樣式
st.markdown("""
    <style>
    .stButton > button { border-radius: 8px; font-weight: bold; }
    .answer-box {
        font-size: 24px; color: #1e40af; background-color: #eff6ff;
        padding: 20px; border-radius: 12px; border: 2px dashed #3b82f6;
        margin-bottom: 20px; min-height: 80px;
    }
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
        for col in ['冊編號', '課編號', '句編號']:
            df[col] = pd.to_numeric(df[col], errors='coerce')
        return df.dropna(subset=['英文', '中文'])
    except:
        return None

# 徹底重置函數
def reset_all_state():
    st.session_state.q_idx = 0
    st.session_state.ans = []
    st.session_state.used_history = []
    st.session_state.shuf = []
    st.session_state.history = {}
    st.session_state.finished = False
    st.session_state.is_correct = False

# 初始化 Session State
if 'q_idx' not in st.session_state: st.session_state.q_idx = 0
if 'ans' not in st.session_state: st.session_state.ans = []
if 'used_history' not in st.session_state: st.session_state.used_history = []
if 'shuf' not in st.session_state: st.session_state.shuf = []
if 'history' not in st.session_state: st.session_state.history = {}
if 'finished' not in st.session_state: st.session_state.finished = False
if 'is_correct' not in st.session_state: st.session_state.is_correct = False

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
        num_q = st.sidebar.slider("4. 練習題數", 1, total_available, min(5, total_available))
        
        quiz_list = filtered_df.head(num_q).to_dict('records')
        
        # 切換範圍時重置
        key = f"{sel_b}-{sel_l}-{start_id}-{num_q}"
        if 'last_k' not in st.session_state or st.session_state.last_k != key:
            st.session_state.last_k = key
            reset_all_state()
            st.rerun()

        # --- 預習/測驗切換 ---
        is_study_mode = st.sidebar.checkbox("📖 開啟預習模式", value=False)
        
        if is_study_mode:
            st.header("📖 課文預習")
            for item in quiz_list:
                with st.container():
                    col_t, col_s = st.columns([5, 1])
                    col_t.markdown(f"**[{item['句編號']}] {item['英文']}**")
                    col_t.caption(f"中文：{item['中文']}")
                    if col_s.button("🔊 發音", key=f"sp_{item['句編號']}"):
                        t_url = f"https://translate.google.com/translate_tts?ie=UTF-8&tl=en&client=tw-ob&q={str(item['英文']).replace(' ', '%20')}"
                        st.markdown(f'<audio autoplay src="{t_url}"></audio>', unsafe_allow_html=True)
                    st.write("---")

        # --- 測驗主畫面 ---
        elif not st.session_state.finished and st.session_state.q_idx < len(quiz_list):
            q = quiz_list[st.session_state.q_idx]
            eng_raw = str(q['英文']).strip()
            correct_tokens = re.findall(r"[\w']+|[^\w\s]", eng_raw)

            if not st.session_state.shuf:
                tmp = correct_tokens.copy()
                random.shuffle(tmp)
                st.session_state.shuf = tmp

            st.title(f"Question {st.session_state.q_idx + 1} / {len(quiz_list)}")
            st.info(f"💡 中文提示：{q['中文']}")

            st.write("### 拼湊結果：")
            res_str = " ".join(st.session_state.ans)
            st.markdown(f'<div class="answer-box">{res_str if res_str else "請點選單字..."}</div>', unsafe_allow_html=True)

            c1, c2, c3 = st.columns([1, 1, 2])
            if not st.session_state.is_correct:
                if c1.button("🔄 全部重填", use_container_width=True):
                    st.session_state.ans = []
                    st.session_state.used_history = []
                    st.rerun()
                if c2.button("⬅️ 退回一步", use_container_width=True):
                    if st.session_state.used_history:
                        st.session_state.used_history.pop()
                        st.session_state.ans.pop()
                        st.rerun()

            if c3.button("⏭️ 跳過此題", use_container_width=True):
                st.session_state.history[st.session_state.q_idx] = {
                    "題號": st.session_state.q_idx + 1, "中文提示": q['中文'], "正確答案": eng_raw,
                    "你的拼湊": " ".join(st.session_state.ans) if st.session_state.ans else "(未作答)", "狀態": "❌ 跳過"
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

            st.write("---")
            # 檢查答案邏輯
            if len(st.session_state.ans) == len(correct_tokens):
                if not st.session_state.is_correct:
                    if st.button("✅ 檢查答案", type="primary", use_container_width=True):
                        # 寬鬆比對 (忽略大小寫)
                        is_ok = [t.lower() for t in st.session_state.ans] == [t.lower() for t in correct_tokens]
                        st.session_state.is_correct = is_ok
                        
                        # 只要按了檢查，不管對錯立刻存入 history
                        st.session_state.history[st.session_state.q_idx] = {
                            "題號": st.session_state.q_idx + 1,
                            "中文提示": q['中文'],
                            "正確答案": eng_raw,
                            "你的拼湊": " ".join(st.session_state.ans),
                            "狀態": "✅ 正確" if is_ok else "❌ 錯誤"
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
                st.error("順序不對喔！紀錄已更新。請修正後再次『檢查答案』或『跳過』。")

            if st.sidebar.button("🛑 提前結束並查看結果", type="primary"):
                # 強制存入最後一題的狀態
                if st.session_state.q_idx not in st.session_state.history:
                    st.session_state.history[st.session_state.q_idx] = {
                        "題號": st.session_state.q_idx + 1,
                        "中文提示": q['中文'],
                        "正確答案": eng_raw,
                        "你的拼湊": " ".join(st.session_state.ans) if st.session_state.ans else "(未完成)",
                        "狀態": "未完成"
                    }
                st.session_state.finished = True
                st.rerun()

        # --- 顯示總結報告 ---
        else:
            st.header("🎊 練習成果回顧")
            if st.session_state.history:
                # 確保表格包含所有已作答或標記的題目
                final_history = [v for k, v in sorted(st.session_state.history.items())]
                report_df = pd.DataFrame(final_history)
                st.table(report_df)
            else:
                st.write("目前無紀錄，請先開始測驗。")

            if st.button("🔄 重新開始練習 (徹底重置)"):
                reset_all_state()
                st.rerun()
    else:
        st.warning("查無題目。")

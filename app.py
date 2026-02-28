import streamlit as st
import pandas as pd
import random
import re

# 正式網頁佈局優化
st.set_page_config(page_title="國中英文句子重組練習", layout="centered")

# 1. 資料讀取 (讀取您的 Google Sheets)
SHEET_ID = "1zVUNGboZALvK3val1RSbCQvEESLRSNEulqpNSzsPJ14"
GID = "176577556"
url = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/export?format=csv&gid={GID}"

@st.cache_data(ttl=60)
def load_data():
    try:
        df = pd.read_csv(url)
        df.columns = [str(c).strip() for c in df.columns]
        return df.dropna(subset=['英文', '中文'])
    except:
        return None

# 初始化變數
if 'q_idx' not in st.session_state: st.session_state.q_idx = 0
if 'ans' not in st.session_state: st.session_state.ans = []
if 'used' not in st.session_state: st.session_state.used = set()
if 'shuf' not in st.session_state: st.session_state.shuf = []

df = load_data()

if df is not None:
    st.sidebar.header("🎯 範圍設定")
    b_vals = sorted(df['冊編號'].astype(str).unique().tolist())
    sel_b = st.sidebar.selectbox("1. 選擇冊別", b_vals)
    l_vals = sorted(df[df['冊編號'].astype(str)==sel_b]['課編號'].astype(str).unique().tolist())
    sel_l = st.sidebar.selectbox("2. 選擇課次", l_vals)
    
    quiz_df = df[(df['冊編號'].astype(str)==sel_b) & (df['課編號'].astype(str)==sel_l)].sort_values('句編號')
    
    if not quiz_df.empty:
        qs = quiz_df.to_dict('records')
        
        # 換課重置邏輯
        key = f"{sel_b}-{sel_l}"
        if 'last_k' not in st.session_state or st.session_state.last_k != key:
            st.session_state.last_k = key
            st.session_state.q_idx = 0
            st.session_state.ans = []
            st.session_state.used = set()
            st.session_state.shuf = []
            st.rerun()

        if st.session_state.q_idx < len(qs):
            q = qs[st.session_state.q_idx]
            # 拆解英文元素
            correct_tokens = re.findall(r"[\w']+|[^\w\s]", str(q['英文']).strip())

            if not st.session_state.shuf:
                tmp = correct_tokens.copy()
                random.shuffle(tmp)
                st.session_state.shuf = tmp

            st.header(f"Question {st.session_state.q_idx + 1} / {len(qs)}")
            st.info(f"💡 中文提示：{q['中文']}")

            st.subheader("拼湊結果：")
            res_str = " ".join(st.session_state.ans)
            st.success(res_str if res_str else "請點選下方單字開始拼湊...")

            st.write("---")
            st.subheader("點選單字與標點：")
            
            # 使用流動排版顯示按鈕，確保寬度充足
            for i, t in enumerate(st.session_state.shuf):
                if i not in st.session_state.used:
                    if st.button(t, key=f"b_{i}"):
                        st.session_state.ans.append(t)
                        st.session_state.used.add(i)
                        st.rerun()

            st.write("---")
            c1, c2 = st.columns(2)
            if c1.button("🔄 全部重填", use_container_width=True):
                st.session_state.ans = []
                st.session_state.used = set()
                st.rerun()
            
            if len(st.session_state.ans) == len(correct_tokens):
                with c2:
                    if st.button("✅ 檢查答案", type="primary", use_container_width=True):
                        if st.session_state.ans == correct_tokens:
                            st.success("完全正確！🎉")
                            # TTS 發音
                            t_url = f"https://translate.google.com/translate_tts?ie=UTF-8&tl=en&client=tw-ob&q={str(q['英文']).replace(' ', '%20')}"
                            st.markdown(f'<audio autoplay src="{t_url}"></audio>', unsafe_allow_html=True)
                        else:
                            st.error("順序不對喔！")
                
                if st.session_state.ans == correct_tokens:
                    if st.button("下一題 Next ➡️", type="primary", use_container_width=True):
                        st.session_state.q_idx += 1
                        st.session_state.ans = []
                        st.session_state.used = set()
                        st.session_state.shuf = []
                        st.rerun()
    else:
        st.warning("查無題目內容。")

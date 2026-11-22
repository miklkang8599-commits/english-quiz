# ==============================================================================
# 🗣️ 對話練習（替換字＋圖卡）模組 — 英文全能練習系統 V2.9.555 起
# ==============================================================================
# 一段固定對話，句中 {欄位} 換成不同單字（每個單字一張圖卡）反覆練習。
# 學生：跟讀 → 看圖說 → 角色對話，每句可錄音，自己勾「說對了／再練」（不自動評分）。
# 老師：圖卡管理（上傳圖片／AI 產生）、指派（選對話、勾圖卡、輪數）、學生紀錄（抽聽錄音）。
#
# 資料：
#   Google Sheets「對話範本」：對話ID｜標題｜程度｜回合｜角色｜角色名稱｜英文｜中文
#                            （選填 V2.9.558：情境｜角色描述 → 給 AI 畫背景與角色立繪）
#   Google Sheets「替換字」  ：對話ID｜欄位｜英文｜中文｜圖｜圖片描述
#   （兩張表不存在也能用：程式內建「D00 天氣示範」）
#   Supabase：dialog_cards（圖卡圖片）、dialog_assignments（指派）、dialog_logs（練習紀錄）
#   Supabase Storage：flashcards（圖卡，公開）、dialog_audio（學生錄音，不公開）
# ==============================================================================

import html
import hashlib
import io
import json
import random
import re
from datetime import datetime, timedelta

import pandas as pd
import streamlit as st

DLG_VERSION = "2.9.562"   # 只改這個模組時，老師端「🗣️ 對話練習」最上面會顯示這個版本

# ------------------------------------------------------------------------------
# 內建示範對話
# ------------------------------------------------------------------------------
DEMO_ID = "D00"
DEMO_DIALOG = {
    "title": "天氣（示範）",
    "level": "國小",
    "names": {"A": "Amy", "B": "Ben"},
    # V2.9.558 情境畫面：背景（不含人物）＋兩位角色立繪
    "scene_desc": "the front gate of a Taiwanese elementary school on a weekday morning, "
                  "trees, a wide sidewalk, school building behind the gate, open sky",
    "char_desc": {
        "A": "Amy, a cheerful elementary school girl with a black ponytail, white school shirt, "
             "navy blue skirt, red backpack",
        "B": "Ben, a friendly elementary school boy with short black hair, white school T-shirt, "
             "navy blue shorts, blue backpack",
    },
    "turns": [
        {"turn": 1, "role": "A", "en": "Hi, Ben! How's the weather today?", "zh": "嗨，Ben！今天天氣如何？"},
        {"turn": 2, "role": "B", "en": "It's {weather} today.", "zh": "今天{weather}。"},
        {"turn": 3, "role": "A", "en": "Do you want to {activity}?", "zh": "你想要{activity}嗎？"},
        {"turn": 4, "role": "B", "en": "Sure! Let's {activity} together.", "zh": "好啊！我們一起{activity}吧。"},
    ],
    "cards": {
        "weather": [
            {"en": "sunny", "zh": "晴天", "img": "☀️", "desc": "a bright smiling sun"},
            {"en": "cloudy", "zh": "陰天", "img": "☁️", "desc": "grey clouds covering the sky"},
            {"en": "rainy", "zh": "下雨", "img": "🌧️", "desc": "a cloud with rain drops"},
            {"en": "windy", "zh": "刮風", "img": "🌬️", "desc": "strong wind blowing leaves"},
            {"en": "snowy", "zh": "下雪", "img": "❄️", "desc": "snow falling, a snowman"},
            {"en": "hot", "zh": "很熱", "img": "🥵", "desc": "a child sweating under a hot sun"},
            {"en": "cold", "zh": "很冷", "img": "🥶", "desc": "a child shivering in a scarf"},
        ],
        "activity": [
            {"en": "play basketball", "zh": "打籃球", "img": "🏀", "desc": "a child playing basketball"},
            {"en": "fly a kite", "zh": "放風箏", "img": "🪁", "desc": "a child flying a kite"},
            {"en": "go swimming", "zh": "去游泳", "img": "🏊", "desc": "a child swimming in a pool"},
            {"en": "watch TV", "zh": "看電視", "img": "📺", "desc": "a child watching TV on a sofa"},
            {"en": "ride a bike", "zh": "騎腳踏車", "img": "🚲", "desc": "a child riding a bicycle"},
        ],
    },
}

STAGES = ["① 全文示範", "② 看圖說", "③ 角色對話"]
STAGE_HELP = {
    "① 全文示範": "按場景裡的 ▶️，兩位角色把整段對話演一遍；點下面任一句可以單獨再聽。換下一輪會換一組單字。",
    "② 看圖說": "替換字變成圖卡，看圖自己說出完整句子，錄完按「看答案」對照。",
    "③ 角色對話": "對方只出聲音；輪到你時只看中文提示和圖卡，說出英文。",
}
AVATARS = ["🧒", "👧", "👦", "🧑", "🐶", "🐱", "🐼", "🦊", "🐰", "🐯", "🐸", "🤖"]
VOICE = {"A": "nova", "B": "onyx"}
IMG_STYLE = ("A cute, simple cartoon flashcard illustration for young English learners. "
             "Single clear subject, centered, thick clean outlines, bright friendly colors, "
             "plain white background. No text, no letters, no words, no numbers.")
# V2.9.558 情境畫面：半寫實繪本／動畫電影風（比照片級寫實更能維持同一角色長相）
SCENE_STYLE = ("A semi-realistic illustration in the style of a modern animated film or picture book, "
               "soft natural lighting, warm friendly colors, detailed but clean, eye-level wide view. "
               "No text, no letters, no signs with words.")
SCENE_TAIL = (" Background scene only: no people, no animals. Leave open ground on the lower left "
              "and lower right for characters to stand.")
CHAR_STYLE = ("A semi-realistic character illustration in the style of a modern animated film, "
              "soft lighting, friendly natural expression. Full body, standing, whole figure visible "
              "from head to shoes, three-quarter view with the body turned toward the viewer's right. "
              "Transparent background, no ground, no shadow, no other objects. No text.")
# V2.9.559 卡通畫風（預設）：鮮豔、生動，像兒童動畫影集
SCENE_CARTOON = ("A vibrant 2D cartoon background illustration in the style of a modern kids' animated TV series, "
                 "bold clean outlines, bright saturated colors, playful simple shapes, cheerful mood, eye-level wide view. "
                 "No text, no letters, no signs with words.")
CHAR_CARTOON = ("A cute, lively 2D cartoon character in the style of a modern kids' animated TV series, "
                "big expressive eyes, big friendly smile, bold clean outlines, bright saturated colors, "
                "energetic pose with one hand waving. Full body, standing, whole figure visible from head to shoes, "
                "three-quarter view with the body turned toward the viewer's right. "
                "Transparent background, no ground, no shadow, no other objects. No text.")
STYLE_SETS = {"🎨 卡通（生動）": (SCENE_CARTOON, CHAR_CARTOON), "🖼️ 半寫實": (SCENE_STYLE, CHAR_STYLE)}

_SLOT_RE = re.compile(r"\{([^{}]+)\}")

SETUP_SQL = """-- 🗣️ 對話練習（V2.9.555）Supabase 設定：在 Supabase → SQL Editor 貼上整段執行一次
create table if not exists dialog_cards (
  card_id text primary key,
  dialog_id text, slot text, word text,
  image_url text,
  updated_at timestamptz default now()
);
create table if not exists dialog_assignments (
  id bigserial primary key,
  created_at timestamptz default now(),
  dialog_id text, title text,
  cards text,            -- JSON：{"weather": ["sunny","windy"], ...}
  rounds int default 5,
  stages text,           -- 例如 ① 跟讀,② 看圖說,③ 角色對話
  students text,         -- 學生姓名，逗號分隔
  end_date date,
  status text default '進行中',
  created_by text
);
create table if not exists dialog_logs (
  id bigserial primary key,
  created_at timestamptz default now(),
  name text, user_id text, group_id text,
  assign_id bigint, dialog_id text,
  stage text, round_no int, turn_no int,
  words text, self_check text, audio_path text
);
create index if not exists dialog_logs_assign_idx on dialog_logs(assign_id, created_at);
alter table dialog_cards disable row level security;
alter table dialog_assignments disable row level security;
alter table dialog_logs disable row level security;
-- 有些 Supabase 專案會自動把新資料表的 RLS 打開，所以再加上允許讀寫的規則
create policy "dlg_cards_rw" on dialog_cards for all to anon, authenticated using (true) with check (true);
create policy "dlg_assign_rw" on dialog_assignments for all to anon, authenticated using (true) with check (true);
create policy "dlg_logs_rw" on dialog_logs for all to anon, authenticated using (true) with check (true);

-- Storage：flashcards 圖卡（公開讀取）、dialog_audio 學生錄音（不公開，老師用簽名網址抽聽）
insert into storage.buckets (id, name, public) values ('flashcards', 'flashcards', true)
  on conflict (id) do nothing;
insert into storage.buckets (id, name, public) values ('dialog_audio', 'dialog_audio', false)
  on conflict (id) do nothing;
create policy "dlg_flashcards_rw" on storage.objects for all to anon, authenticated
  using (bucket_id = 'flashcards') with check (bucket_id = 'flashcards');
create policy "dlg_audio_rw" on storage.objects for all to anon, authenticated
  using (bucket_id = 'dialog_audio') with check (bucket_id = 'dialog_audio');
"""

_CSS = """<style>
.dlg-row{display:flex;margin:.35rem 0;align-items:flex-end;gap:.45rem}
.dlg-row.mine{flex-direction:row-reverse}
.dlg-av{font-size:2.1rem;line-height:1}
.dlg-bub{max-width:82%;padding:.55rem .8rem;border-radius:14px;background:#f1f3f5;color:#111;
  font-size:1.15rem;line-height:1.6}
.dlg-row.mine .dlg-bub{background:#dbeeff}
.dlg-name{font-size:.8rem;color:#666;margin-bottom:.1rem}
.dlg-zh{font-size:.92rem;color:#555;margin-top:.15rem}
.dlg-mark{background:#ffe066;color:#111;border-radius:5px;padding:0 .25rem;font-weight:600}
.dlg-blank{display:inline-block;border:2px dashed #339af0;border-radius:8px;padding:0 .3rem;
  margin:0 .1rem;background:#fff;vertical-align:middle}
.dlg-hidden{color:#999;font-style:italic}
.dlg-cards{display:flex;flex-wrap:wrap;gap:.6rem;margin:.3rem 0 .6rem}
.dlg-card{border:1px solid #dee2e6;border-radius:12px;padding:.4rem .6rem;text-align:center;
  background:#fff;color:#111;min-width:96px}
.dlg-card .w{font-weight:600;font-size:1rem}
.dlg-card .z{font-size:.8rem;color:#666}
.dlg-stage{position:relative;width:100%;aspect-ratio:3/2;max-height:380px;border-radius:16px;overflow:hidden;
  margin:.3rem 0 .7rem;background:#cfe8ff center/cover no-repeat}
.dlg-ch{position:absolute;bottom:0;height:86%;width:38%;display:flex;justify-content:center;align-items:flex-end}
.dlg-ch.l{left:2%}
.dlg-ch.r{right:2%}
.dlg-ch .fig{height:82%;display:flex;align-items:flex-end;justify-content:center;
  transform-origin:50% 100%;animation:dlg-idle 2.6s ease-in-out infinite}
.dlg-ch.r .fig{animation-delay:-1.3s}
.dlg-ch.act .fig{animation:dlg-talk .55s ease-in-out infinite alternate}
.dlg-ch.dim .fig{filter:brightness(.82) saturate(.85)}
.dlg-ch img{height:100%;width:auto;max-width:100%;object-fit:contain;object-position:bottom;
  filter:drop-shadow(0 6px 8px rgba(0,0,0,.35))}
.dlg-ch.r img{transform:scaleX(-1)}
.dlg-ch .emo{font-size:5rem;line-height:1;margin-bottom:12%}
@keyframes dlg-idle{0%,100%{transform:translateY(0) scale(1)}50%{transform:translateY(-2%) scale(1.01)}}
@keyframes dlg-talk{from{transform:translateY(0) scale(1.04)}to{transform:translateY(-5%) scale(1.07)}}
.dlg-say{position:absolute;top:4%;max-width:56%;background:#fff;color:#111;border:3px solid #222;border-radius:18px;
  padding:.35rem .7rem;font-size:1.02rem;line-height:1.45;font-weight:600;z-index:3;
  box-shadow:0 3px 0 rgba(0,0,0,.25);animation:dlg-pop .35s ease-out}
.dlg-say.l{left:22%}
.dlg-say.r{right:22%}
.dlg-say:after{content:"";position:absolute;bottom:-14px;width:0;height:0;border:8px solid transparent;border-top:12px solid #222}
.dlg-say.l:after{left:14px}
.dlg-say.r:after{right:14px}
@keyframes dlg-pop{from{transform:scale(.6);opacity:0}to{transform:scale(1);opacity:1}}
.dlg-say .dlg-zh{font-weight:400}
.dlg-say.prev{opacity:.72;font-size:.85rem;max-width:40%;font-weight:500;border-width:2px;animation:none;z-index:2}
.dlg-stage.nobg{background:linear-gradient(#a9dcff 0%,#e3f4ff 58%,#9be37f 58%,#6fc257 100%)}
.dlg-stage.wp{border-radius:16px 16px 0 0;margin-bottom:0}
.st-key-dlg_panel{background:linear-gradient(#3d5a73,#2c3e50);border-radius:0 0 16px 16px;
  padding:.55rem .75rem .75rem;margin-top:-1rem;box-shadow:0 4px 10px rgba(0,0,0,.18)}
.st-key-dlg_panel .dlg-ph{color:#fff;font-weight:700;font-size:1rem}
.st-key-dlg_panel label p,.st-key-dlg_panel [data-testid="stCaptionContainer"],
.st-key-dlg_panel [data-testid="stCaptionContainer"] p{color:#e9eef3 !important}
.st-key-dlg_panel [data-testid="stAlert"] p{color:inherit !important}
.dlg-fx{position:absolute;inset:0;pointer-events:none;overflow:hidden;z-index:2}
.dlg-fx .p{position:absolute;top:-12%;animation:dlg-fall linear infinite}
.dlg-fx .drop{width:2px;height:16px;border-radius:2px;background:linear-gradient(rgba(255,255,255,0),rgba(70,130,255,.85))}
.dlg-fx .flake{color:#fff;font-size:15px;text-shadow:0 0 3px rgba(0,0,0,.25)}
.dlg-fx .leaf{position:absolute;left:-12%;font-size:18px;animation:dlg-blow linear infinite}
.dlg-fx .cloud{position:absolute;left:-30%;font-size:46px;opacity:.9;animation:dlg-drift linear infinite}
.dlg-fx .sun{position:absolute;top:3%;left:3%;font-size:46px;animation:dlg-glow 2.4s ease-in-out infinite}
.dlg-fx .tint{position:absolute;inset:0}
@keyframes dlg-fall{from{top:-12%}to{top:108%}}
@keyframes dlg-blow{from{left:-12%;transform:rotate(0)}to{left:112%;transform:rotate(720deg)}}
@keyframes dlg-drift{from{left:-30%}to{left:110%}}
@keyframes dlg-glow{0%,100%{transform:scale(1);filter:drop-shadow(0 0 6px #ffd43b)}50%{transform:scale(1.12);filter:drop-shadow(0 0 18px #ffd43b)}}
.dlg-tag{position:absolute;bottom:6px;left:50%;transform:translateX(-50%);white-space:nowrap;
  background:rgba(0,0,0,.6);color:#fff;border-radius:8px;padding:0 .45rem;font-size:.82rem}
.dlg-sign{position:absolute;bottom:4%;left:50%;transform:translateX(-50%);display:flex;gap:.35rem;z-index:3;
  background:rgba(255,255,255,.9);border-radius:12px;padding:.3rem .5rem;box-shadow:0 2px 6px rgba(0,0,0,.2)}
.dlg-sign .it{text-align:center;color:#111;font-size:.8rem;font-weight:600;line-height:1.2}
.dlg-face{width:2.9rem;height:2.9rem;border-radius:50%;flex:0 0 auto;background:#e7f1ff no-repeat;
  background-size:230%;background-position:50% 3%;border:2px solid #fff;box-shadow:0 1px 3px rgba(0,0,0,.25)}
</style>"""


# ------------------------------------------------------------------------------
# 資料載入
# ------------------------------------------------------------------------------
def _s(v):
    v = "" if v is None else str(v)
    return "" if v.lower() == "nan" else v.strip()


@st.cache_data(ttl=300, show_spinner=False)
def _read_sheet(_conn, name):
    try:
        return _conn.read(worksheet=name, ttl=300).fillna("").astype(str).replace(r"\.0$", "", regex=True)
    except Exception:
        return pd.DataFrame()


@st.cache_data(ttl=60, show_spinner=False)
def _load_card_images(_sb_factory):
    try:
        res = _sb_factory().table("dialog_cards").select("card_id,image_url").execute()
        return {r["card_id"]: r.get("image_url") or "" for r in (res.data or [])}
    except Exception:
        return {}


def card_id(dialog_id, slot, en):
    return f"{dialog_id}|{slot}|{en}"


def load_dialogs(ctx):
    """回傳 {對話ID: {title, level, names, turns, cards{slot:[card]}}}，內建示範在最前面"""
    dialogs = {DEMO_ID: json.loads(json.dumps(DEMO_DIALOG, ensure_ascii=False))}
    df_t = _read_sheet(ctx["conn"], "對話範本")
    df_c = _read_sheet(ctx["conn"], "替換字")
    if not df_t.empty and "對話ID" in df_t.columns:
        for _, r in df_t.iterrows():
            did = _s(r.get("對話ID"))
            if not did or not _s(r.get("英文")):
                continue
            d = dialogs.setdefault(did, {"title": "", "level": "", "names": {}, "turns": [], "cards": {}})
            if did == DEMO_ID and d.get("_from_demo", True):
                # 試算表自己寫了 D00：整段改用試算表
                d.update({"title": "", "level": "", "names": {}, "turns": [], "cards": {}, "_from_demo": False})
            if _s(r.get("標題")):
                d["title"] = _s(r.get("標題"))
            if _s(r.get("程度")):
                d["level"] = _s(r.get("程度"))
            role = (_s(r.get("角色")) or "A").upper()[:1]
            if _s(r.get("角色名稱")):
                d["names"][role] = _s(r.get("角色名稱"))
            # V2.9.558 選填欄：情境（背景描述）、角色描述（立繪描述）
            if _s(r.get("情境")):
                d["scene_desc"] = _s(r.get("情境"))
            if _s(r.get("角色描述")):
                d.setdefault("char_desc", {})[role] = _s(r.get("角色描述"))
            try:
                tno = int(float(_s(r.get("回合")) or 0))
            except ValueError:
                tno = 0
            d["turns"].append({"turn": tno or len(d["turns"]) + 1, "role": role,
                               "en": _s(r.get("英文")), "zh": _s(r.get("中文"))})
    if not df_c.empty and "對話ID" in df_c.columns:
        seen_sheet_cards = set()
        for _, r in df_c.iterrows():
            did, slot, en = _s(r.get("對話ID")), _s(r.get("欄位")), _s(r.get("英文"))
            if not did or not slot or not en or did not in dialogs:
                continue
            d = dialogs[did]
            if (did, slot) not in seen_sheet_cards:
                d["cards"][slot] = []          # 試算表有這個欄位就整組取代示範
                seen_sheet_cards.add((did, slot))
            d["cards"][slot].append({"en": en, "zh": _s(r.get("中文")),
                                     "img": _s(r.get("圖")), "desc": _s(r.get("圖片描述"))})
    imgs = _load_card_images(ctx["sb"])
    for did, d in dialogs.items():
        d.pop("_from_demo", None)
        d["turns"].sort(key=lambda t: t["turn"])
        d["title"] = d["title"] or did
        for slot, cards in d["cards"].items():
            for c in cards:
                c["slot"] = slot
                c["id"] = card_id(did, slot, c["en"])
                if imgs.get(c["id"]):
                    c["img"] = imgs[c["id"]]
        # V2.9.558 情境畫面（背景＋兩位角色立繪），圖存在 dialog_cards（欄位 _scene／_char）
        sid = card_id(did, "_scene", "bg")
        d["scene"] = {"id": sid, "slot": "_scene", "en": "bg", "zh": "情境背景", "img": imgs.get(sid, ""),
                      "desc": d.pop("scene_desc", "") or f"an everyday scene for a dialogue about {d['title']}"}
        cdesc = d.pop("char_desc", {}) or {}
        d["chars"] = {}
        for role in ("A", "B"):
            cid = card_id(did, "_char", role)
            nm = d["names"].get(role, role)
            d["chars"][role] = {"id": cid, "slot": "_char", "en": role, "zh": nm, "img": imgs.get(cid, ""),
                                "desc": cdesc.get(role) or f"{nm}, a friendly elementary school student"}
    return dialogs


def _slots_in(dialog):
    out = []
    for t in dialog["turns"]:
        for m in _SLOT_RE.finditer(t["en"] + " " + t["zh"]):
            s = m.group(1).strip()
            if s not in out:
                out.append(s)
    return out


# ------------------------------------------------------------------------------
# 顯示小工具
# ------------------------------------------------------------------------------
def _img_html(card, px=40):
    src = _s(card.get("img"))
    if src.startswith("http"):
        return (f"<img src='{html.escape(src, quote=True)}' alt='{html.escape(card.get('en',''))}' "
                f"style='height:{px}px;max-width:{int(px*1.6)}px;object-fit:contain;vertical-align:middle;border-radius:6px'>")
    if src:
        return f"<span style='font-size:{int(px*0.8)}px;vertical-align:middle'>{html.escape(src)}</span>"
    return f"<span style='font-size:{int(px*0.6)}px;vertical-align:middle'>🖼️</span>"


def _fill(tpl, combo, field="en", mode="plain"):
    """mode: plain（純文字，給語音）／mark（替換字上色）／blank（替換字換成圖卡）"""
    out, pos = [], 0
    for m in _SLOT_RE.finditer(tpl):
        seg = tpl[pos:m.start()]
        out.append(seg if mode == "plain" else html.escape(seg))
        card = combo.get(m.group(1).strip())
        if card is None:
            out.append(m.group(0) if mode == "plain" else html.escape(m.group(0)))
        else:
            val = card["en"] if field == "en" else (card.get("zh") or card["en"])
            if mode == "plain":
                out.append(val)
            elif mode == "mark":
                out.append(f"<span class='dlg-mark'>{html.escape(val)}</span>")
            else:
                out.append(f"<span class='dlg-blank'>{_img_html(card, 34)}</span>")
        pos = m.end()
    tail = tpl[pos:]
    out.append(tail if mode == "plain" else html.escape(tail))
    return "".join(out)


def _bubble(avatar, name, body, zh="", mine=False):
    zh_html = f"<div class='dlg-zh'>{zh}</div>" if zh else ""
    st.markdown(
        f"<div class='dlg-row{' mine' if mine else ''}'><div class='dlg-av'>{avatar}</div>"
        f"<div class='dlg-bub'><div class='dlg-name'>{html.escape(name)}</div>{body}{zh_html}</div></div>",
        unsafe_allow_html=True)


def _cards_strip(cards, px=64, show_text=True):
    items = []
    for c in cards:
        txt = (f"<div class='w'>{html.escape(c['en'])}</div><div class='z'>{html.escape(c.get('zh',''))}</div>"
               if show_text else "")
        items.append(f"<div class='dlg-card'>{_img_html(c, px)}{txt}</div>")
    st.markdown(f"<div class='dlg-cards'>{''.join(items)}</div>", unsafe_allow_html=True)


# ── V2.9.558 情境畫面 ──
def _url(card):
    v = _s((card or {}).get("img"))
    return v if v.startswith("http") else ""


def has_scene(d):
    return bool(_url(d.get("scene")) or any(_url(c) for c in d.get("chars", {}).values()))


def _face_html(d, role, fallback="🧑"):
    """對話泡泡旁的大頭：有立繪就裁頭部，沒有就用 emoji"""
    u = _url(d.get("chars", {}).get(role))
    if u:
        return f"<div class='dlg-face' style=\"background-image:url('{html.escape(u, quote=True)}')\"></div>"
    return html.escape(fallback)


_FX_WORDS = [  # V2.9.559 天氣特效：單字比對 → 特效
    (r"\brain", "rain"), (r"\bstorm", "rain"), (r"\bsnow", "snow"), (r"\bwind(y|s)?\b", "wind"),
    (r"\bcloud", "cloud"), (r"\bfog", "cloud"), (r"\bsun(ny|shine)?\b", "sun"),
    (r"\bhot\b", "hot"), (r"\bcold\b", "cold"),
]


def _fx_kinds(cards):
    out = []
    for c in cards or []:
        w = str(c.get("en", "")).lower()
        for pat, fx in _FX_WORDS:
            if re.search(pat, w) and fx not in out:
                out.append(fx)
    return out


def _fx_html(kinds):
    if not kinds:
        return ""
    p = []
    for fx in kinds:
        if fx == "rain":
            for i in range(28):
                p.append(f"<span class='p drop' style='left:{(i * 37) % 100}%;"
                         f"animation-duration:{0.55 + (i % 5) * 0.08:.2f}s;animation-delay:-{(i * 0.13) % 1:.2f}s'></span>")
            p.append("<span class='tint' style='background:rgba(40,60,90,.18)'></span>")
        elif fx in ("snow", "cold"):
            n = 22 if fx == "snow" else 10
            for i in range(n):
                p.append(f"<span class='p flake' style='left:{(i * 41) % 100}%;"
                         f"animation-duration:{3 + (i % 4) * 0.7:.1f}s;animation-delay:-{(i * 0.37) % 4:.2f}s'>❄</span>")
            if fx == "cold":
                p.append("<span class='tint' style='background:rgba(120,180,255,.18)'></span>")
        elif fx == "wind":
            for i in range(7):
                p.append(f"<span class='leaf' style='top:{12 + (i * 23) % 60}%;"
                         f"animation-duration:{2.2 + (i % 3) * 0.6:.1f}s;animation-delay:-{i * 0.5:.1f}s'>🍃</span>")
        elif fx == "cloud":
            for i in range(3):
                p.append(f"<span class='cloud' style='top:{2 + i * 9}%;"
                         f"animation-duration:{18 + i * 6}s;animation-delay:-{i * 7}s'>☁️</span>")
            p.append("<span class='tint' style='background:rgba(90,100,110,.12)'></span>")
        elif fx in ("sun", "hot"):
            p.append("<span class='sun'>☀️</span>")
            if fx == "hot":
                p.append("<span class='tint' style='background:rgba(255,120,40,.14)'></span>")
    return f"<div class='dlg-fx'>{''.join(p)}</div>"


def _stage_html(d, cards=None, tags=None, show_text=True, emo=None, active=None, say="",
                prev_role=None, prev_say="", panel=False):
    """情境舞台：背景圖＋左右兩位角色立繪（說話的人會動）＋場景內對話泡泡（含上一句）＋天氣特效＋本輪圖卡看板"""
    bg = _url(d.get("scene"))
    style = f" style=\"background-image:url('{html.escape(bg, quote=True)}')\"" if bg else ""
    cls = "dlg-stage" + ("" if bg else " nobg") + (" wp" if panel else "")
    parts = [f"<div class='{cls}'{style}>", _fx_html(_fx_kinds(cards))]
    if prev_role and prev_say:
        parts.append(f"<div class='dlg-say prev {'l' if prev_role == 'A' else 'r'}'>{prev_say}</div>")
    tags = tags or {}
    emo = emo or {"A": "👧", "B": "👦"}
    for role, side in (("A", "l"), ("B", "r")):
        u = _url(d.get("chars", {}).get(role))
        fig = (f"<img src='{html.escape(u, quote=True)}' alt=''>" if u
               else f"<span class='emo'>{html.escape(emo.get(role, '🧑'))}</span>")
        tag = tags.get(role) or d["names"].get(role, role)
        st_cls = "" if not active else (" act" if role == active else " dim")
        parts.append(f"<div class='dlg-ch {side}{st_cls}'><div class='fig'>{fig}</div>"
                     f"<span class='dlg-tag'>{html.escape(tag)}</span></div>")
    if active and say:
        parts.append(f"<div class='dlg-say {'l' if active == 'A' else 'r'}'>{say}</div>")
    if cards:
        its = []
        for c in cards:
            txt = f"<div>{html.escape(c['en'])}</div>" if show_text else ""
            its.append(f"<div class='it'>{_img_html(c, 46)}{txt}</div>")
        parts.append(f"<div class='dlg-sign'>{''.join(its)}</div>")
    parts.append("</div>")
    return "".join(parts)


@st.cache_data(show_spinner=False, max_entries=600)
def _tts(text, voice, speed):
    # 失敗會丟例外（不快取失敗結果），由 _play 接住
    import openai
    cl = openai.OpenAI(api_key=st.secrets["OPENAI_API_KEY"])
    return cl.audio.speech.create(model="tts-1", voice=voice, input=text, speed=speed).content


def _play(text, role, speed, autoplay=False):
    try:
        audio = _tts(text, VOICE.get(role, "nova"), speed)
    except Exception:
        audio = None
    if audio:
        try:
            st.audio(audio, format="audio/mp3", autoplay=autoplay)
        except TypeError:          # 舊版 Streamlit 沒有 autoplay
            st.audio(audio, format="audio/mp3")
    else:
        st.caption("（語音暫時無法產生）")


# ------------------------------------------------------------------------------
# Supabase 存取
# ------------------------------------------------------------------------------
@st.cache_data(ttl=30, show_spinner=False)
def _load_assignments(_sb_factory, ver=0):
    try:
        res = (_sb_factory().table("dialog_assignments").select("*")
               .neq("status", "已刪除").order("created_at", desc=True).execute())
        return res.data or [], ""
    except Exception as e:
        return [], f"{type(e).__name__}: {e}"


def _assign_ver():
    return st.session_state.get("_dlg_assign_ver", 0)


def _bump_assign():
    st.session_state["_dlg_assign_ver"] = _assign_ver() + 1


def _setup_hint(err=""):
    st.warning("⚠️ 對話練習的 Supabase 資料表／儲存空間還沒建立。請老師到「🗣️ 對話練習 → ⚙️ 設定說明」"
               "複製 SQL，貼到 Supabase 的 SQL Editor 執行一次。")
    if err:
        with st.expander("🔍 錯誤詳情"):
            st.code(err)


def _signed_url(sb, path, secs=3600):
    try:
        r = sb.storage.from_("dialog_audio").create_signed_url(path, secs)
        if isinstance(r, dict):
            return r.get("signedURL") or r.get("signedUrl") or r.get("signed_url") or ""
        return getattr(r, "signed_url", "") or ""
    except Exception:
        return ""


def _save_log(ctx, run, stage, rno, tno, combo_words, check, audio_bytes):
    sb = ctx["sb"]()
    path = ""
    if audio_bytes:
        ts = datetime.utcnow().strftime("%Y%m%d%H%M%S%f")
        path = f"{ctx['user_id']}/{run.get('assign_id') or 'trial'}/{ts}_s{STAGES.index(stage)+1}_r{rno}_t{tno}.wav"
        try:
            sb.storage.from_("dialog_audio").upload(path, audio_bytes, {"content-type": "audio/wav"})
        except Exception as e:
            # V2.9.557：錯誤留在畫面上（toast 會被 st.rerun 蓋掉）
            st.session_state["dlg_last_err"] = f"錄音上傳失敗（紀錄仍會存）：{type(e).__name__}: {e}"
            path = ""
    aid = run.get("assign_id")
    try:
        sb.table("dialog_logs").insert({
            "name": str(ctx.get("user_name") or ""), "user_id": str(ctx.get("user_id") or ""),
            "group_id": str(ctx.get("group_id") or ""),
            "assign_id": int(aid) if aid not in (None, "") else None, "dialog_id": str(run["dialog_id"]),
            "stage": str(stage), "round_no": int(rno), "turn_no": int(tno),
            "words": ";".join(f"{k}={v}" for k, v in combo_words.items()),
            "self_check": str(check), "audio_path": path,
        }).execute()
        return True
    except Exception as e:
        st.session_state["dlg_last_err"] = f"紀錄寫入失敗：{type(e).__name__}: {e}"
        return False


# ------------------------------------------------------------------------------
# 學生端
# ------------------------------------------------------------------------------
def _make_combos(sel, n):
    cols = {}
    for slot, words in sel.items():
        words = list(words)
        if not words:
            continue
        seq = []
        while len(seq) < n:
            w = words[:]
            random.shuffle(w)
            if seq and len(w) > 1 and w[0] == seq[-1]:
                w.append(w.pop(0))
            seq += w
        cols[slot] = seq[:n]
    return [{s: cols[s][i] for s in cols} for i in range(n)]


def _start_run(dialog_id, dialog, sel, rounds, stages, assign_id=None, title=""):
    stages = ["① 全文示範" if str(x).strip() == "① 跟讀" else str(x).strip() for x in stages]  # 舊指派相容
    allc = {s: [c["en"] for c in dialog["cards"].get(s, [])] for s in _slots_in(dialog)}
    sel = {s: (sel.get(s) or allc.get(s, [])) for s in allc}
    for k in [k for k in st.session_state.keys() if str(k).startswith(("dlg_rec_", "dlg_stage"))]:
        st.session_state.pop(k, None)
    st.session_state["dlg_run"] = {
        "assign_id": assign_id, "dialog_id": dialog_id, "title": title or dialog["title"],
        "sel": sel, "rounds": max(1, int(rounds)), "stages": [x for x in STAGES if x in stages] or STAGES[:],
        "combos": _make_combos(sel, max(1, int(rounds))), "avatar": None, "role": None,
        "round": 0, "checks": {}, "reveal": {},
    }


def render_student_entry(ctx):
    """放在學生任務列表最前面。若正在練對話，畫練習畫面並 st.stop()。"""
    st.markdown(_CSS, unsafe_allow_html=True)
    if st.session_state.get("dlg_run"):
        _render_run(ctx)
        st.stop()

    rows, err = _load_assignments(ctx["sb"], _assign_ver())
    today = ctx["today"]
    mine = []
    for a in rows:
        try:
            if a.get("end_date") and datetime.strptime(str(a["end_date"])[:10], "%Y-%m-%d").date() < today:
                continue
        except ValueError:
            pass
        names = [x.strip() for x in str(a.get("students") or "").split(",") if x.strip()]
        if ctx["is_admin"] or ctx["user_name"] in names:
            mine.append(a)
    if not mine and not ctx["is_admin"]:
        return

    dialogs = load_dialogs(ctx)
    st.markdown("<h2 style='margin-bottom:0'>🗣️ 對話練習</h2>", unsafe_allow_html=True)
    if err and ctx["is_admin"]:
        _setup_hint(err)
    for a in mine:
        d = dialogs.get(a.get("dialog_id"))
        c1, c2 = st.columns([4, 1])
        c1.markdown(f"**{html.escape(a.get('title') or '對話練習')}**  \n"
                    f"<span style='color:#888;font-size:.85rem'>{a.get('rounds', 5)} 輪｜截止 {str(a.get('end_date') or '')[:10]}</span>",
                    unsafe_allow_html=True)
        if d is None:
            c2.caption("找不到對話")
            continue
        if c2.button("▶️ 開始", key=f"dlg_go_{a['id']}", use_container_width=True, type="primary"):
            try:
                sel = json.loads(a.get("cards") or "{}")
            except ValueError:
                sel = {}
            _start_run(a["dialog_id"], d, sel, a.get("rounds") or 5,
                       [x.strip() for x in str(a.get("stages") or "").split(",")], a["id"], a.get("title"))
            st.rerun()
    if ctx["is_admin"]:
        with st.expander("🧪 老師試玩（不需指派、全部圖卡）"):
            ids = list(dialogs.keys())
            pick = st.selectbox("對話", ids, format_func=lambda i: f"{i}｜{dialogs[i]['title']}", key="dlg_trial_pick")
            n = st.number_input("輪數", 1, 30, 5, key="dlg_trial_n")
            if st.button("▶️ 開始試玩", key="dlg_trial_go"):
                _start_run(pick, dialogs[pick], {}, n, STAGES)
                st.rerun()
    st.divider()


def _render_run(ctx):
    run = st.session_state["dlg_run"]
    dialogs = load_dialogs(ctx)
    d = dialogs.get(run["dialog_id"])
    top1, top2 = st.columns([4, 1])
    top1.markdown(f"### 🗣️ {html.escape(run['title'])}")
    _err = st.session_state.pop("dlg_last_err", "")
    if _err:
        st.error("⚠️ " + _err)
    if top2.button("⬅️ 返回", key="dlg_back", use_container_width=True):
        st.session_state.pop("dlg_run", None)
        st.rerun()
    if d is None:
        st.error("找不到這段對話（可能已從試算表刪除）。")
        return
    names = {"A": d["names"].get("A", "A"), "B": d["names"].get("B", "B")}
    by_en = {s: {c["en"]: c for c in d["cards"].get(s, [])} for s in d["cards"]}

    # ── 第一步：選角色 ──
    both_chars = all(_url(d.get("chars", {}).get(r)) for r in ("A", "B"))
    if not run["avatar"] or not run["role"]:
        st.markdown(_stage_html(d), unsafe_allow_html=True)
        if both_chars:
            av = "🧑"   # 兩位角色都有立繪：不用另外選頭像
        else:
            st.markdown("#### 1️⃣ 選一個你的頭像")
            av = st.radio("頭像", AVATARS, horizontal=True, key="dlg_av_pick", label_visibility="collapsed")
        st.markdown("#### 你要演誰？" if both_chars else "#### 2️⃣ 你要演誰？")
        role = st.radio("角色", ["A", "B"], horizontal=True, key="dlg_role_pick",
                        format_func=lambda r: f"{r}：{names[r]}" + ("（先開口）" if d["turns"] and d["turns"][0]["role"] == r else ""),
                        label_visibility="collapsed")
        with st.expander("👀 先看看整段對話"):
            for t in d["turns"]:
                st.markdown(f"**{names.get(t['role'], t['role'])}**：{html.escape(t['en'])}　<span style='color:#888'>{html.escape(t['zh'])}</span>",
                            unsafe_allow_html=True)
        if st.button("🚀 開始練習", type="primary", key="dlg_setup_ok", use_container_width=True):
            run["avatar"], run["role"] = av, role
            st.rerun()
        return

    me = run["role"]
    partner_av = AVATARS[(AVATARS.index(run["avatar"]) + 4) % len(AVATARS)] if run["avatar"] in AVATARS else "🧑"
    avatars = {me: run["avatar"], ("B" if me == "A" else "A"): partner_av}
    avatars = {r: _face_html(d, r, a) for r, a in avatars.items()}   # V2.9.558 有立繪就用立繪大頭
    disp = {me: f"{ctx['user_name']}（{names[me]}）", ("B" if me == "A" else "A"): names["B" if me == "A" else "A"]}

    # V2.9.562：更新前就開始的練習可能還記著舊關卡名稱（① 跟讀），換成目前的名稱
    run["stages"] = [x for x in STAGES if x in ["① 全文示範" if s == "① 跟讀" else s for s in run["stages"]]] or STAGES[:]
    if st.session_state.get("dlg_stage") == "① 跟讀":
        st.session_state["dlg_stage"] = STAGES[0]
    if run.get("goto_stage"):
        # 不能在 radio 畫出來之後才改它的值，所以下一關的切換放在這裡（畫 radio 之前）
        st.session_state["dlg_stage"] = run.pop("goto_stage")
    if st.session_state.get("dlg_stage") not in run["stages"]:
        st.session_state["dlg_stage"] = run["stages"][0]
    c1, c2 = st.columns([3, 2])
    stage = c1.radio("關卡", run["stages"], horizontal=True, key="dlg_stage")
    speed_lbl = c2.radio("語速", ["正常", "慢速"], horizontal=True, key="dlg_speed")
    speed = 1.0 if speed_lbl == "正常" else 0.75
    st.caption("💡 " + STAGE_HELP.get(stage, ""))

    n = run["rounds"]
    rno = min(run["round"], n - 1)
    combo_words = run["combos"][rno]
    combo = {s: by_en.get(s, {}).get(w, {"en": w, "zh": "", "img": "", "slot": s}) for s, w in combo_words.items()}
    turns = d["turns"]
    other = "B" if me == "A" else "A"

    if stage == STAGES[0]:
        _render_demo(d, run, combo, me, other, names, partner_av, speed, rno, n)
        return

    # V2.9.560 場景播放器：一次演一句，A／B 的對話都出現在場景裡，操作按鈕在場景下方的面板
    sk = f"{stage}|{rno}"
    steps = run.setdefault("step", {})
    i = max(0, min(int(steps.get(sk, 0)), len(turns)))      # i == len(turns)：這一輪演完
    st.progress((rno + 1) / n, text=f"第 {rno + 1} / {n} 輪")

    def line_html(t):
        k_ = f"{stage}|{rno}|{t['turn']}"
        mine_ = t["role"] == me
        if stage == STAGES[0] or run["reveal"].get(k_):
            out = _fill(t["en"], combo, "en", "mark")
            if stage == STAGES[0] and t["zh"]:
                out += f"<div class='dlg-zh'>{_fill(t['zh'], combo, 'zh', 'mark')}</div>"
            return out
        if stage == STAGES[1]:
            return _fill(t["en"], combo, "en", "blank" if mine_ else "mark")
        if mine_:
            zh_ = _fill(t["zh"], combo, "zh", "blank") if t["zh"] else ""
            return "🎤 換你說！" + (f"<div class='dlg-zh'>{zh_}</div>" if zh_ else "")
        return "🔊 ……"

    cur = turns[i] if i < len(turns) else None
    if cur is not None:
        active, say = cur["role"], line_html(cur)
    else:
        active, say = me, "🎉 這一輪完成！"
    prev = turns[i - 1] if i >= 1 and cur is not None else None
    prev_role = prev["role"] if prev and prev["role"] != active else None
    st.markdown(_stage_html(d, list(combo.values()),
                            tags={me: f"{names[me]}（你）", other: names[other]},
                            show_text=(stage == STAGES[0]),
                            emo={me: run["avatar"], other: partner_av},
                            active=active, say=say,
                            prev_role=prev_role, prev_say=line_html(prev) if prev_role else "",
                            panel=True), unsafe_allow_html=True)

    def go(step):
        steps[sk] = max(0, min(step, len(turns)))
        st.rerun()

    with st.container(key="dlg_panel"):
        if cur is not None:
            k = f"{stage}|{rno}|{cur['turn']}"
            mine = cur["role"] == me
            revealed = run["reveal"].get(k, False)
            plain = _fill(cur["en"], combo, "en", "plain")
            played = run.setdefault("played", [])
            first_show = k not in played
            if first_show:
                played.append(k)
            who = "🎤 輪到你說" if mine else f"👂 聽 {names[cur['role']]} 說"
            st.markdown(f"<div class='dlg-ph'>第 {i + 1} / {len(turns)} 句｜{html.escape(who)}</div>",
                        unsafe_allow_html=True)
            if not mine:
                _play(plain, cur["role"], speed, autoplay=first_show)
                c1, c2, c3 = st.columns(3)
                if c1.button("⬅️ 上一句", key=f"dlg_pv_{k}", disabled=i == 0, use_container_width=True):
                    go(i - 1)
                if stage == STAGES[2] and not revealed:
                    if c2.button("📝 顯示文字", key=f"dlg_rv_{k}", use_container_width=True):
                        run["reveal"][k] = True
                        st.rerun()
                if c3.button("下一句 ➡️", key=f"dlg_nx_{k}", type="primary", use_container_width=True):
                    go(i + 1)
            else:
                if stage == STAGES[0] or revealed:
                    _play(plain, cur["role"], speed, autoplay=first_show and stage == STAGES[0])
                rec = st.audio_input("🎙️ 錄下你說的這一句", key=f"dlg_rec_{k}")
                done = run["checks"].get(k)
                c1, c2, c3, c4 = st.columns(4)
                if c1.button("⬅️ 上一句", key=f"dlg_pv_{k}", disabled=i == 0, use_container_width=True):
                    go(i - 1)
                if stage != STAGES[0] and not revealed:
                    if c2.button("👀 看答案", key=f"dlg_ans_{k}", use_container_width=True):
                        run["reveal"][k] = True
                        st.rerun()
                if c3.button("✅ 說對了", key=f"dlg_ok_{k}", use_container_width=True,
                             type="primary" if done == "✅" else "secondary"):
                    if _save_log(ctx, run, stage, rno + 1, cur["turn"], combo_words, "✅", rec.getvalue() if rec else None):
                        run["checks"][k] = "✅"
                        go(i + 1)
                    st.rerun()
                if c4.button("🔁 再練", key=f"dlg_again_{k}", use_container_width=True,
                             type="primary" if done == "🔁" else "secondary"):
                    if _save_log(ctx, run, stage, rno + 1, cur["turn"], combo_words, "🔁", rec.getvalue() if rec else None):
                        run["checks"][k] = "🔁"
                        go(i + 1)
                    st.rerun()
                if done:
                    st.caption(f"已記錄：{done}（再按一次會再記一筆）")
        else:
            rk = [v for kk, v in run["checks"].items() if kk.startswith(f"{sk}|")]
            st.markdown(f"<div class='dlg-ph'>🎉 第 {rno + 1} 輪完成！✅ {rk.count('✅')}　🔁 {rk.count('🔁')}</div>",
                        unsafe_allow_html=True)
            c1, c2, c3 = st.columns(3)
            if c1.button("🔁 這一輪再演一次", key=f"dlg_again_round_{sk}", use_container_width=True):
                go(0)
            if c2.button("⬅️ 上一句", key=f"dlg_pv_end_{sk}", use_container_width=True):
                go(len(turns) - 1)
            if rno < n - 1:
                if c3.button("下一輪 ➡️", key="dlg_next", type="primary", use_container_width=True):
                    run["round"] = rno + 1
                    st.rerun()
            else:
                nxt = run["stages"].index(stage) + 1
                if nxt < len(run["stages"]):
                    if c3.button(f"進入 {run['stages'][nxt]} ➡️", key="dlg_next_stage", type="primary",
                                 use_container_width=True):
                        run["goto_stage"] = run["stages"][nxt]
                        run["round"] = 0
                        st.rerun()
                else:
                    sc = [v for kk, v in run["checks"].items()]
                    c3.success(f"🏁 全部完成！✅ {sc.count('✅')}　🔁 {sc.count('🔁')}")

    with st.expander("📜 這一輪的整段對話"):
        for j, t in enumerate(turns):
            mark = "▶️ " if j == i else ""
            st.markdown(f"{mark}**{html.escape(names.get(t['role'], t['role']))}**："
                        f"{line_html(t) if j < i or stage == STAGES[0] else '……'}", unsafe_allow_html=True)
    if rno > 0:
        if st.button("⬅️ 回上一輪", key="dlg_prev"):
            run["round"] = rno - 1
            st.rerun()


# ── V2.9.561 ① 全文示範：場景自動演完整段對話（瀏覽器端播放，控制鈕在場景裡） ──
_DEMO_CSS = """<style>
html,body{margin:0;padding:0;background:transparent;font-family:"Source Sans Pro",system-ui,sans-serif}
.dlg-stage{margin:0 !important}
.dm-start{position:absolute;inset:0;display:flex;align-items:center;justify-content:center;z-index:6;
  background:rgba(0,0,0,.18);cursor:pointer}
.dm-start span{background:#ff922b;color:#fff;font-size:1.25rem;font-weight:800;padding:.6rem 1.3rem;border-radius:999px;
  border:3px solid #fff;box-shadow:0 4px 0 rgba(0,0,0,.25);animation:dm-pulse 1.2s ease-in-out infinite}
@keyframes dm-pulse{0%,100%{transform:scale(1)}50%{transform:scale(1.07)}}
.dm-ctrl{position:absolute;right:8px;top:8px;display:flex;gap:6px;z-index:5}
.dm-ctrl button{border:2px solid #222;background:#fff;border-radius:999px;width:38px;height:38px;font-size:17px;
  cursor:pointer;box-shadow:0 2px 0 rgba(0,0,0,.25);padding:0}
.dm-ctrl button.main{background:#ffd43b;width:46px}
.dm-cnt{position:absolute;left:8px;top:8px;z-index:5;background:rgba(0,0,0,.55);color:#fff;border-radius:999px;
  padding:.1rem .6rem;font-size:.85rem}
.dlg-say.mid{left:30%}
.dm-tr{margin-top:.5rem}
.dm-row{display:flex;gap:.5rem;align-items:flex-start;padding:.35rem .5rem;border-radius:10px;cursor:pointer;
  font-size:1.02rem;line-height:1.5;color:#222}
.dm-row:hover{background:#f1f3f5}
.dm-row.on{background:#fff3bf}
.dm-row .nm{font-weight:700;min-width:3.2rem;color:#1c7ed6}
.dm-row .nm.B{color:#e8590c}
.dm-row .zh{font-size:.88rem;color:#666}
</style>"""


def _demo_html(d, combo, tags, emo, speed):
    import base64
    lines, rows = [], []
    for j, t in enumerate(d["turns"]):
        plain = _fill(t["en"], combo, "en", "plain")
        try:
            a = "data:audio/mp3;base64," + base64.b64encode(_tts(plain, VOICE.get(t["role"], "nova"), speed)).decode()
        except Exception:
            a = ""
        en_html = _fill(t["en"], combo, "en", "mark")
        zh_html = _fill(t["zh"], combo, "zh", "mark") if t["zh"] else ""
        bub = en_html + (f"<div class='dlg-zh'>{zh_html}</div>" if zh_html else "")
        lines.append({"r": t["role"], "h": bub, "a": a})
        nm = html.escape(d["names"].get(t["role"], t["role"]))
        rows.append(f"<div class='dm-row' id='r{j}' onclick='one({j})'><span class='nm {t['role']}'>{nm}</span>"
                    f"<div><div>{en_html}</div><div class='zh'>{zh_html}</div></div></div>")
    stage = _stage_html(d, list(combo.values()), tags=tags, show_text=True, emo=emo)
    data = json.dumps(lines, ensure_ascii=False).replace("</", "<\\/")
    js = """<script>
const L=__DATA__;
const S=document.querySelector('.dlg-stage');
const CH={A:S.querySelector('.dlg-ch.l'),B:S.querySelector('.dlg-ch.r')};
const say=document.createElement('div');say.style.display='none';S.appendChild(say);
const pv=document.createElement('div');pv.style.display='none';S.appendChild(pv);
const cnt=document.createElement('div');cnt.className='dm-cnt';cnt.textContent='全文示範';S.appendChild(cnt);
const ctl=document.createElement('div');ctl.className='dm-ctrl';
ctl.innerHTML="<button title='重來' onclick='restart()'>⏮</button><button title='上一句' onclick='one(Math.max(0,i-1))'>⏪</button>"+
 "<button class='main' id='pp' title='播放／暫停' onclick='toggle()'>▶️</button><button title='下一句' onclick='one(Math.min(L.length-1,i+1))'>⏩</button>";
S.appendChild(ctl);
const st=document.createElement('div');st.className='dm-start';st.innerHTML='<span>▶️ 播放全文示範</span>';
st.onclick=()=>{st.remove();restart();};S.appendChild(st);
const au=new Audio();let i=-1,playing=false,tm=null;
function pop(el){el.style.animation='none';void el.offsetWidth;el.style.animation='';}
function show(k){
  i=k;
  for(const r of ['A','B']){CH[r].classList.remove('act','dim');if(k>=0&&k<L.length)CH[r].classList.add(L[k].r===r?'act':'dim');}
  document.querySelectorAll('.dm-row').forEach((e,n)=>e.classList.toggle('on',n===k));
  if(k>=L.length){say.className='dlg-say mid';say.innerHTML='🎉 示範完畢！再按 ⏮ 可以重看';say.style.display='';pv.style.display='none';pop(say);cnt.textContent='全文示範';return;}
  const side=L[k].r==='A'?'l':'r';
  say.className='dlg-say '+side;say.innerHTML=L[k].h;say.style.display='';pop(say);
  if(k>0&&L[k-1].r!==L[k].r){pv.className='dlg-say prev '+(L[k-1].r==='A'?'l':'r');pv.innerHTML=L[k-1].h;pv.style.display='';}
  else pv.style.display='none';
  cnt.textContent='第 '+(k+1)+' / '+L.length+' 句';
}
function upd(){document.getElementById('pp').textContent=playing?'⏸':'▶️';}
function sound(k){clearTimeout(tm);au.pause();if(L[k].a){au.src=L[k].a;au.play().catch(()=>{});}else{tm=setTimeout(()=>au.onended(),2500);}}
function play(k){show(k);if(k>=L.length){playing=false;upd();return;}sound(k);}
au.onended=()=>{if(playing)tm=setTimeout(()=>play(i+1),450);};
function restart(){const s=document.querySelector('.dm-start');if(s)s.remove();playing=true;upd();play(0);}
function one(k){const s=document.querySelector('.dm-start');if(s)s.remove();playing=false;upd();show(k);sound(k);}
function toggle(){const s=document.querySelector('.dm-start');if(s)s.remove();
  if(playing){playing=false;au.pause();clearTimeout(tm);}
  else{playing=true;if(i<0||i>=L.length)play(0);else if(au.src&&au.paused&&!au.ended&&au.currentTime>0)au.play();else play(i);}
  upd();}
</script>""".replace("__DATA__", data)
    return (_CSS + _DEMO_CSS + stage + f"<div class='dm-tr'>{''.join(rows)}</div>" + js)


def _render_demo(d, run, combo, me, other, names, partner_av, speed, rno, n):
    st.progress((rno + 1) / n, text=f"第 {rno + 1} / {n} 輪（每輪換一組單字）")
    page = _demo_html(d, combo, tags={me: f"{names[me]}（你）", other: names[other]},
                      emo={me: run["avatar"], other: partner_av}, speed=speed)
    try:
        import streamlit.components.v1 as components
        components.html(page, height=410 + 64 * len(d["turns"]), scrolling=False)
    except Exception as e:
        st.error(f"示範畫面無法顯示：{type(e).__name__}: {e}")
    c1, c2, c3 = st.columns(3)
    if c1.button("⬅️ 上一輪", key="dlg_demo_prev", disabled=rno == 0, use_container_width=True):
        run["round"] = rno - 1
        st.rerun()
    if rno < n - 1 and c2.button("🔀 換一組單字（下一輪）", key="dlg_demo_next", use_container_width=True):
        run["round"] = rno + 1
        st.rerun()
    nxt = 1 if len(run["stages"]) > 1 else None
    if nxt and c3.button(f"進入 {run['stages'][nxt]} ➡️", key="dlg_demo_stage", type="primary", use_container_width=True):
        run["goto_stage"] = run["stages"][nxt]
        run["round"] = 0
        st.rerun()


# ------------------------------------------------------------------------------
# 老師端
# ------------------------------------------------------------------------------
def _gen_image(prompt, size="1024x1024", transparent=False, quality="low"):
    import base64
    import openai
    cl = openai.OpenAI(api_key=st.secrets["OPENAI_API_KEY"])
    last = None
    gkw = {"quality": quality, "size": size}
    if transparent:
        gkw["background"] = "transparent"
    dsize = {"1536x1024": "1792x1024", "1024x1536": "1024x1792"}.get(size, size)
    for model, kw in (("gpt-image-1-mini", gkw),
                      ("gpt-image-1", gkw),
                      ("dall-e-3", {"quality": "standard", "response_format": "b64_json", "size": dsize})):
        try:
            r = cl.images.generate(model=model, prompt=prompt, n=1, **kw)
            b64 = r.data[0].b64_json
            if b64:
                return base64.b64decode(b64), model
        except Exception as e:
            last = e
    raise RuntimeError(f"{type(last).__name__}: {last}")


def _to_png(raw):
    from PIL import Image
    im = Image.open(io.BytesIO(raw))
    im = im.convert("RGBA") if im.mode in ("RGBA", "LA", "P") else im.convert("RGB")
    im.thumbnail((512, 512))
    buf = io.BytesIO()
    im.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


def _prep_image(raw, kind):
    """回傳 (bytes, 副檔名, content-type)。背景 → JPG 寬 1024；立繪 → 保留透明的 PNG；圖卡 → PNG 512"""
    if kind == "scene":
        from PIL import Image
        im = Image.open(io.BytesIO(raw)).convert("RGB")
        im.thumbnail((1024, 1024))
        buf = io.BytesIO()
        im.save(buf, format="JPEG", quality=82, optimize=True)
        return buf.getvalue(), "jpg", "image/jpeg"
    if kind == "char":
        from PIL import Image
        im = Image.open(io.BytesIO(raw))
        im = im.convert("RGBA")
        bb = im.getbbox()          # 裁掉透明留白，人物在舞台上才站得大
        if bb:
            im = im.crop(bb)
        im.thumbnail((420, 640))
        buf = io.BytesIO()
        im.save(buf, format="PNG", optimize=True)
        return buf.getvalue(), "png", "image/png"
    return _to_png(raw), "png", "image/png"


def _kind(card):
    return {"_scene": "scene", "_char": "char"}.get(card.get("slot"), "card")


def _gen_for(card, desc):
    """依種類（圖卡／背景／立繪）產生圖片"""
    k = _kind(card)
    scene_style, char_style = STYLE_SETS.get(st.session_state.get("dlg_style"), next(iter(STYLE_SETS.values())))
    if k == "scene":
        return _gen_image(f"{scene_style} Scene: {desc}.{SCENE_TAIL}", size="1536x1024", quality="medium")
    if k == "char":
        return _gen_image(f"{char_style} Character: {desc}.", size="1024x1536", transparent=True, quality="medium")
    return _gen_image(f"{IMG_STYLE} Subject: {desc}.")


def _save_card_image(ctx, dialog_id, card, raw):
    sb = ctx["sb"]()
    png, ext, ctype = _prep_image(raw, _kind(card))
    path = f"{re.sub(r'[^A-Za-z0-9_-]', '_', dialog_id)}/{hashlib.md5(card['id'].encode('utf-8')).hexdigest()}.{ext}"
    sb.storage.from_("flashcards").upload(path, png, {"content-type": ctype, "upsert": "true"})
    url = sb.storage.from_("flashcards").get_public_url(path)
    if isinstance(url, dict):
        url = url.get("publicUrl") or url.get("publicURL") or ""
    url = str(url).rstrip("?") + f"?v={int(datetime.utcnow().timestamp())}"
    sb.table("dialog_cards").upsert({
        "card_id": card["id"], "dialog_id": dialog_id, "slot": card["slot"], "word": card["en"],
        "image_url": url, "updated_at": datetime.utcnow().isoformat(),
    }).execute()
    _load_card_images.clear()
    return url


def render_teacher(ctx):
    st.markdown(_CSS, unsafe_allow_html=True)
    st.caption(f"對話練習模組 V{DLG_VERSION}")
    dialogs = load_dialogs(ctx)
    tabs = st.tabs(["🖼️ 對話與圖卡", "📌 指派", "🎧 學生紀錄", "⚙️ 設定說明"])
    with tabs[0]:
        _teacher_cards(ctx, dialogs)
    with tabs[1]:
        _teacher_assign(ctx, dialogs)
    with tabs[2]:
        _teacher_records(ctx, dialogs)
    with tabs[3]:
        _teacher_setup()


def _pick_dialog(dialogs, key):
    ids = list(dialogs.keys())
    return st.selectbox("對話", ids, key=key,
                        format_func=lambda i: f"{i}｜{dialogs[i]['title']}" + (f"（{dialogs[i]['level']}）" if dialogs[i]["level"] else ""))


def _teacher_cards(ctx, dialogs):
    c1, c2 = st.columns([5, 1])
    with c1:
        did = _pick_dialog(dialogs, "dlg_t_pick")
    if c2.button("🔄", key="dlg_t_reload", help="重新讀取試算表與圖卡"):
        _read_sheet.clear()
        _load_card_images.clear()
        st.rerun()
    d = dialogs[did]
    with st.expander("📜 對話內容", expanded=True):
        for t in d["turns"]:
            st.markdown(f"**{t['turn']}. {html.escape(d['names'].get(t['role'], t['role']))}**："
                        f"{html.escape(t['en'])}　<span style='color:#888'>{html.escape(t['zh'])}</span>",
                        unsafe_allow_html=True)
    _teacher_scene(ctx, did, d)
    missing_slots = [s for s in _slots_in(d) if not d["cards"].get(s)]
    if missing_slots:
        st.warning("這些欄位在「替換字」表還沒有單字：" + "、".join(missing_slots))

    all_cards = [c for s in d["cards"] for c in d["cards"][s]]
    no_img = [c for c in all_cards if not _s(c.get("img")).startswith("http")]
    st.markdown(f"**圖卡：{len(all_cards)} 張，其中 {len(no_img)} 張還沒有圖片檔**（emoji 只是暫代）")
    if no_img and st.button(f"🎨 一次 AI 產生 {len(no_img)} 張缺圖", key="dlg_gen_all"):
        bar = st.progress(0.0)
        ok = 0
        for i, c in enumerate(no_img):
            try:
                raw, _m = _gen_image(f"{IMG_STYLE} Subject: {c.get('desc') or c['en']}.")
                _save_card_image(ctx, did, c, raw)
                ok += 1
            except Exception as e:
                st.error(f"{c['en']}：{e}")
            bar.progress((i + 1) / len(no_img), text=f"{i + 1}/{len(no_img)}")
        st.success(f"完成 {ok} 張")
        st.rerun()

    ncol = 2 if ctx.get("is_phone") else 4
    for slot, cards in d["cards"].items():
        st.markdown(f"##### 欄位 `{{{slot}}}`")
        for i in range(0, len(cards), ncol):
            cols = st.columns(ncol)
            for col, c in zip(cols, cards[i:i + ncol]):
                with col:
                    _card_editor(ctx, did, c)


def _teacher_scene(ctx, did, d):
    """V2.9.558 情境畫面：背景（不含人物）＋角色 A／B 立繪（透明背景）"""
    st.markdown("#### 🎬 情境畫面（背景＋角色立繪）")
    st.caption("學生練習時，對話會出現在這個場景裡，兩位角色站左右兩邊。"
               "背景和人物分開畫，同一個角色每一輪長相都一樣。半寫實插畫風，每張約 20–60 秒。")
    first = {}
    for s in _slots_in(d):
        if d["cards"].get(s):
            first[s] = d["cards"][s][0]
    t0 = d["turns"][0] if d["turns"] else None
    st.markdown(_stage_html(d, list(first.values()), active=t0["role"] if t0 else None,
                            say=_fill(t0["en"], first, "en", "mark") if t0 else ""), unsafe_allow_html=True)
    st.caption("↑ 預覽：說話的人會跳動、場景裡出現對話泡泡；抽到天氣單字會有下雨、下雪、颳風等特效。")
    st.radio("畫風（AI 產生時用）", list(STYLE_SETS.keys()), horizontal=True, key="dlg_style")
    items = [d["scene"], d["chars"]["A"], d["chars"]["B"]]
    missing = [c for c in items if not _url(c)]
    b1, b2 = st.columns(2)
    go_missing = bool(missing) and b1.button(f"🎨 一次 AI 產生情境畫面（缺 {len(missing)} 張）", key=f"dlg_scene_all_{did}")
    go_redo = b2.button("🔁 三張全部用目前畫風重畫", key=f"dlg_scene_redo_{did}")
    todo = items if go_redo else (missing if go_missing else [])
    if todo:
        bar = st.progress(0.0)
        for i, c in enumerate(todo):
            try:
                raw, _m = _gen_for(c, c["desc"])
                _save_card_image(ctx, did, c, raw)
            except Exception as e:
                st.error(f"{c['zh']}：{e}")
            bar.progress((i + 1) / len(todo), text=f"{i + 1}/{len(todo)}")
        st.rerun()
    cols = st.columns(3)
    for col, c, lbl in zip(cols, items, ["🏞️ 背景", f"🧍 A：{d['names'].get('A', 'A')}", f"🧍 B：{d['names'].get('B', 'B')}"]):
        with col:
            st.caption(lbl)
            _card_editor(ctx, did, c)
    st.divider()


def _card_editor(ctx, did, c):
    if _kind(c) == "card":
        st.markdown(f"<div class='dlg-card'>{_img_html(c, 88)}<div class='w'>{html.escape(c['en'])}</div>"
                    f"<div class='z'>{html.escape(c.get('zh', ''))}</div></div>", unsafe_allow_html=True)
    elif _url(c):
        st.image(_url(c))
    else:
        st.caption("（還沒有圖）")
    hk = hashlib.md5(c["id"].encode("utf-8")).hexdigest()[:10]
    with st.popover("✏️ 換圖", use_container_width=True):
        up = st.file_uploader("上傳圖片", type=["png", "jpg", "jpeg", "webp"], key=f"dlg_up_{hk}")
        if up is not None and st.button("💾 使用上傳的圖", key=f"dlg_upok_{hk}"):
            try:
                _save_card_image(ctx, did, c, up.getvalue())
                st.success("已儲存")
                st.rerun()
            except Exception as e:
                st.error(f"儲存失敗：{type(e).__name__}: {e}")
        st.markdown("---")
        desc = st.text_input("AI 圖片描述（英文較準）", value=c.get("desc") or c["en"], key=f"dlg_desc_{hk}")
        pend_key = f"dlg_pending_{hk}"
        if st.button("🎨 AI 產生", key=f"dlg_gen_{hk}"):
            with st.spinner("產生中（約 10–30 秒）…"):
                try:
                    raw, model = _gen_for(c, desc)
                    st.session_state[pend_key] = raw
                except Exception as e:
                    st.error(f"產生失敗：{e}")
        raw = st.session_state.get(pend_key)
        if raw:
            st.image(raw, width=200)
            a1, a2 = st.columns(2)
            if a1.button("✅ 使用這張", key=f"dlg_genok_{hk}"):
                try:
                    _save_card_image(ctx, did, c, raw)
                    st.session_state.pop(pend_key, None)
                    st.rerun()
                except Exception as e:
                    st.error(f"儲存失敗：{type(e).__name__}: {e}")
            if a2.button("🗑️ 不要", key=f"dlg_gendel_{hk}"):
                st.session_state.pop(pend_key, None)
                st.rerun()


def _teacher_assign(ctx, dialogs):
    did = _pick_dialog(dialogs, "dlg_a_pick")
    d = dialogs[did]
    sel = {}
    for slot in _slots_in(d):
        cards = d["cards"].get(slot, [])
        opts = [c["en"] for c in cards]
        lab = {c["en"]: f"{c['en']}｜{c.get('zh', '')}" for c in cards}
        sel[slot] = st.multiselect(f"欄位 {{{slot}}} 要練的圖卡", opts, default=opts, key=f"dlg_a_sel_{did}_{slot}",
                                   format_func=lambda x, lab=lab: lab.get(x, x))
        chosen = [c for c in cards if c["en"] in sel[slot]]
        if chosen:
            _cards_strip(chosen, px=44)
    longest = max([len(v) for v in sel.values()] or [5])
    c1, c2 = st.columns(2)
    rounds = c1.number_input("練幾輪（每輪換一組圖卡）", 1, 30, max(3, min(longest, 10)), key=f"dlg_a_n_{did}")
    end = c2.date_input("截止日期", value=ctx["today"] + timedelta(days=7), key="dlg_a_end")
    if "dlg_a_stages" in st.session_state:   # 舊關卡名稱留在畫面狀態裡會出錯，先濾掉
        st.session_state["dlg_a_stages"] = [x for x in STAGES if x in
                                            ["① 全文示範" if s == "① 跟讀" else s for s in st.session_state["dlg_a_stages"]]]
    stages = st.multiselect("關卡", STAGES, default=STAGES, key="dlg_a_stages")

    df_s = ctx["df_s"]
    stu = df_s[~df_s["分組"].isin(["ADMIN", "TEACHER"])] if "分組" in df_s.columns else df_s
    groups = sorted([g for g in stu["分組"].unique().tolist() if g]) if "分組" in stu.columns else []
    g_pick = st.multiselect("指派班級（整班）", groups, key="dlg_a_groups",
                            format_func=lambda g: f"{g}（{'、'.join(sorted(stu[stu['分組'] == g]['姓名'].tolist()))}）")
    s_pick = st.multiselect("或指定學生", sorted(stu["姓名"].unique().tolist()) if "姓名" in stu.columns else [],
                            key="dlg_a_stus")
    targets = sorted(set(stu[stu["分組"].isin(g_pick)]["姓名"].tolist() if g_pick else []) | set(s_pick))
    words_txt = "、".join(w for v in sel.values() for w in v)
    title = st.text_input("任務名稱", value=f"🗣️ {d['title']}：{words_txt[:40]}", key=f"dlg_a_title_{did}")
    st.caption(f"將指派給 {len(targets)} 位學生")
    if st.button("📤 發布對話練習", type="primary", key="dlg_a_publish",
                 disabled=not targets or any(not v for v in sel.values()) or not stages):
        try:
            ctx["sb"]().table("dialog_assignments").insert({
                "dialog_id": did, "title": title, "cards": json.dumps(sel, ensure_ascii=False),
                "rounds": int(rounds), "stages": ",".join(stages), "students": ",".join(targets),
                "end_date": end.strftime("%Y-%m-%d"), "status": "進行中", "created_by": ctx["user_name"],
            }).execute()
            _bump_assign()
            st.success(f"🎉 已發布，指派給 {len(targets)} 位學生")
        except Exception as e:
            _setup_hint(f"{type(e).__name__}: {e}")

    st.divider()
    st.markdown("#### 📋 已發布的對話練習")
    rows, err = _load_assignments(ctx["sb"], _assign_ver())
    if err:
        _setup_hint(err)
    for a in rows:
        c1, c2 = st.columns([5, 1])
        n_stu = len([x for x in str(a.get("students") or "").split(",") if x.strip()])
        c1.markdown(f"**{html.escape(a.get('title') or '')}**  \n"
                    f"<span style='color:#888;font-size:.85rem'>#{a['id']}｜{a.get('rounds')} 輪｜{n_stu} 人｜截止 {str(a.get('end_date') or '')[:10]}</span>",
                    unsafe_allow_html=True)
        if c2.button("🗑️", key=f"dlg_a_del_{a['id']}", help="刪除這個指派"):
            ctx["sb"]().table("dialog_assignments").update({"status": "已刪除"}).eq("id", a["id"]).execute()
            _bump_assign()
            st.rerun()


def _teacher_records(ctx, dialogs):
    rows, err = _load_assignments(ctx["sb"], _assign_ver())
    if err:
        _setup_hint(err)
        return
    opts = [None] + [a["id"] for a in rows]
    titles = {a["id"]: a.get("title") or f"#{a['id']}" for a in rows}
    aid = st.selectbox("指派", opts, key="dlg_r_pick",
                       format_func=lambda i: "🧪 老師試玩紀錄" if i is None else f"#{i}｜{titles.get(i, '')}")
    if st.button("🔄 重新整理", key="dlg_r_reload"):
        st.session_state.pop("dlg_r_urls", None)
    sb = ctx["sb"]()
    try:
        q = sb.table("dialog_logs").select("*").order("created_at", desc=True).limit(2000)
        q = q.is_("assign_id", "null") if aid is None else q.eq("assign_id", aid)
        data = q.execute().data or []
    except Exception as e:
        _setup_hint(f"{type(e).__name__}: {e}")
        return
    if not data:
        st.info("還沒有練習紀錄。")
        return
    df = pd.DataFrame(data)
    df["有錄音"] = df["audio_path"].fillna("").astype(str).str.len() > 0
    summ = df.groupby("name").agg(
        練習句數=("id", "count"),
        說對了=("self_check", lambda s: int((s == "✅").sum())),
        再練=("self_check", lambda s: int((s == "🔁").sum())),
        錄音=("有錄音", "sum"),
        最後練習=("created_at", "max"),
    ).reset_index().rename(columns={"name": "姓名"}).sort_values("再練", ascending=False)
    summ["最後練習"] = summ["最後練習"].astype(str).str[:16].str.replace("T", " ")
    st.markdown("#### 👩‍🎓 每位學生")
    st.dataframe(summ, use_container_width=True, hide_index=True)

    wrows = []
    for _, r in df.iterrows():
        for kv in str(r.get("words") or "").split(";"):
            if "=" in kv:
                wrows.append({"圖卡": kv.split("=", 1)[1], "self_check": r["self_check"]})
    if wrows:
        wdf = pd.DataFrame(wrows)
        ws = wdf.groupby("圖卡").agg(說對了=("self_check", lambda s: int((s == "✅").sum())),
                                     再練=("self_check", lambda s: int((s == "🔁").sum()))).reset_index()
        st.markdown("#### 🖼️ 哪張圖卡最常「再練」")
        st.dataframe(ws.sort_values("再練", ascending=False), use_container_width=True, hide_index=True)

    st.markdown("#### 🎧 抽聽錄音")
    names = sorted(df["name"].dropna().unique().tolist())
    who = st.selectbox("學生", names, key="dlg_r_who")
    only_again = st.checkbox("只看「再練」", key="dlg_r_again")
    sub = df[(df["name"] == who) & df["有錄音"]]
    if only_again:
        sub = sub[sub["self_check"] == "🔁"]
    sub = sub.head(30)
    d_map = {did: dd for did, dd in dialogs.items()}
    if sub.empty:
        st.caption("沒有錄音")
        return
    if st.button(f"▶️ 載入 {len(sub)} 段錄音", key="dlg_r_load"):
        st.session_state["dlg_r_urls"] = {r["audio_path"]: _signed_url(sb, r["audio_path"]) for _, r in sub.iterrows()}
    urls = st.session_state.get("dlg_r_urls", {})
    for _, r in sub.iterrows():
        dd = d_map.get(r.get("dialog_id"))
        line = ""
        if dd:
            t = next((t for t in dd["turns"] if t["turn"] == r.get("turn_no")), None)
            if t:
                combo = {}
                for kv in str(r.get("words") or "").split(";"):
                    if "=" in kv:
                        s, w = kv.split("=", 1)
                        combo[s] = {"en": w, "zh": ""}
                line = _fill(t["en"], combo, "en", "plain")
        st.markdown(f"{r['self_check']} **{html.escape(str(r.get('stage','')))}** 第 {r.get('round_no')} 輪｜"
                    f"{html.escape(line)}　<span style='color:#888;font-size:.8rem'>{str(r['created_at'])[:16].replace('T',' ')}</span>",
                    unsafe_allow_html=True)
        u = urls.get(r["audio_path"])
        if u:
            st.audio(u)


def _teacher_setup():
    st.markdown("""
**一次性設定（只要做一次）**
1. 到 Supabase 專案 → 左邊 **SQL Editor** → **New query**，把下面整段貼上，按 **Run**。
2. 會建立 3 張資料表（圖卡、指派、練習紀錄）和 2 個儲存空間（`flashcards` 圖卡、`dialog_audio` 錄音）。

**自己加對話（Google 試算表，可選）**
- 新增工作表 **對話範本**，欄位：`對話ID｜標題｜程度｜回合｜角色｜角色名稱｜英文｜中文`
  - 一列一句；要替換的地方寫 `{欄位名}`，例如 `It's {weather} today.`、中文 `今天{weather}。`
  - 角色填 A 或 B；角色名稱（例如 Amy）同一段寫一次就好。
- 新增工作表 **替換字**，欄位：`對話ID｜欄位｜英文｜中文｜圖｜圖片描述`
  - 英文寫放進句子後的完整片語（`an apple`、`apples`），a/an、單複數才會對。
  - 圖：可留空、填 emoji、或貼圖片網址；之後在「🖼️ 對話與圖卡」上傳或 AI 產生會覆蓋。
  - 圖片描述：給 AI 畫圖用的英文說明（例如 `a dad holding a child`），留空就用英文單字。
- 沒建這兩張表也能用內建的 **D00 天氣示範**。
""")
    st.code(SETUP_SQL, language="sql")

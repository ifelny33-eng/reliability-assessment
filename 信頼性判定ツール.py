import html
import json
import re
import streamlit as st
from janome.tokenizer import Tokenizer
from google import genai

st.set_page_config(
    page_title="認知バイアス・レントゲン",
    layout="wide"
)

@st.cache_resource
def load_tokenizer():
    return Tokenizer()

tokenizer = load_tokenizer()

def get_gemini_client():
    try:
        api_key = st.secrets.get("GEMINI_API_KEY")
    except Exception:
        return None
    if not api_key:
        return None
    return genai.Client(api_key=api_key)

NUMBER_PATTERN = r'\d+(?:\.\d+)?(?:%|％|割|倍|人|件|円|kg|m|年|月|日)?'

AUTHORITY_WORDS = [
    "最新の調査",
    "研究結果",
    "専門家",
    "科学的に",
    "公式",
    "実績",
    "データ"
]

EMPHASIS_WORDS = [
    "絶対",
    "確実",
    "間違いなく",
    "100%",
    "100％",
    "唯一",
    "完全",
    "最高",
    "衝撃",
    "驚愕",
    "今すぐ",
    "誰でも"
]

ASSERTIVE_ENDINGS = (
    "だ",
    "である",
    "に違いない",
    "はずだ",
    "べきだ",
    "断言できる",
    "なのだ",
    "のです"
)

SPECULATIVE_ENDINGS = (
    "かもしれない",
    "だろう",
    "と思われる",
    "ようだ",
    "らしい",
    "みたいだ",
    "と思う",
    "かもしれません"
)

PURPOSE_FIELDS = {
    "ニュース": [
        "いつ",
        "どこで",
        "誰が",
        "何を",
        "なぜ",
        "どのように",
        "結果・影響",
        "情報源・根拠"
    ],
    "商品・広告": [
        "商品・サービス名",
        "価格",
        "主な特徴",
        "メリット",
        "デメリット・注意点",
        "対象者",
        "販売元・情報源"
    ],
    "研究・論文": [
        "研究目的",
        "研究方法",
        "研究対象",
        "実施時期・場所",
        "研究結果",
        "結論",
        "限界・注意点",
        "論文・情報源"
    ],
    "一般情報": [
        "概要",
        "重要な事実",
        "日時・数値",
        "関係者・対象",
        "理由・背景",
        "根拠・情報源",
        "注意点・不明点"
    ]
}

def analyze_text_advanced(text, reader_states):
    lines = [
        line.strip()
        for line in text.strip().split('\n')
        if line.strip()
    ]
    total_lines = len(lines) if lines else 1
    total_chars = len(re.sub(r'\s+', '', text))
    numbers_found = re.findall(NUMBER_PATTERN, text)
    authority_words_found = [
        w for w in AUTHORITY_WORDS if w in text
    ]
    number_count = len(numbers_found) + len(authority_words_found)
    emphasis_count = (
        sum(text.count(word) for word in EMPHASIS_WORDS)
        + text.count("！")
        + text.count("!")
    )
    sentences = [
        s.strip()
        for s in re.split(r'[。！？!?\n]+', text)
        if s.strip()
    ]
    assertive_count = 0
    speculative_count = 0
    for s in sentences:
        if s.endswith(ASSERTIVE_ENDINGS):
            assertive_count += 1
        elif s.endswith(SPECULATIVE_ENDINGS):
            speculative_count += 1
    tokens = list(tokenizer.tokenize(text))
    bullet_count = sum(
        1 for line in lines
        if re.match(r'^[・\-•\*▶▷◆■●]|\d+[\.\)．]', line)
    )
    bullet_ratio = round(bullet_count / total_lines, 2)
    length_bonus = (
        20 if 50 <= total_chars <= 1000
        else (10 if total_chars > 10 else 0)
    )
    fluency_score = min(
        100,
        int(
            (bullet_ratio * 60)
            + length_bonus
            + (20 if total_lines >= 2 else 0)
        )
    )
    authority_score = min(
        100,
        int(
            (number_count * 15)
            + (assertive_count * 20)
            + (emphasis_count * 15)
        )
    )
    text_vulnerability_score = min(
        100,
        int(
            (fluency_score * 0.4)
            + (authority_score * 0.6)
        )
    )
    reader_bonus = 0
    if reader_states["confirmation"]:
        reader_bonus += 15
    if reader_states["urgency"]:
        reader_bonus += 15
    if reader_states["fatigue"]:
        reader_bonus += 10
    total_vulnerability_score = min(
        100,
        text_vulnerability_score + reader_bonus
    )
    return {
        "total_chars": total_chars,
        "sentence_count": len(sentences),
        "token_count": len(tokens),
        "number_count": number_count,
        "numbers_found": numbers_found + authority_words_found,
        "emphasis_count": emphasis_count,
        "bullet_ratio": bullet_ratio,
        "assertive_count": assertive_count,
        "speculative_count": speculative_count,
        "fluency_score": fluency_score,
        "authority_score": authority_score,
        "text_vulnerability_score": text_vulnerability_score,
        "reader_bonus": reader_bonus,
        "total_vulnerability_score": total_vulnerability_score
    }

def render_bias_xray(text):
    char_styles = [None] * len(text)
    rules = [
        (
            r'(?:^|(?<=\n))[ \t]*([・\-•\*▶▷◆■●]|\d+[\.\)．])',
            "#bbdefb",
            "#0d47a1",
            "構造化・箇条書き（処理流暢性）"
        ),
        (
            r'(' + NUMBER_PATTERN + r'|' + '|'.join(
                re.escape(w) for w in AUTHORITY_WORDS
            ) + ')',
            "#fff9c4",
            "#f57f17",
            "数字・権威付け（具体性バイアス）"
        ),
        (
            r'(' + '|'.join(
                re.escape(w) for w in EMPHASIS_WORDS
            ) + r'|！|!)',
            "#ffe0b2",
            "#e65100",
            "強調・煽り表現（感情バイアス）"
        ),
        (
            r'(' + '|'.join(
                re.escape(w) for w in ASSERTIVE_ENDINGS
            ) + r')(?=[。！？!?\n]|$)',
            "#ffcdd2",
            "#b71c1c",
            "断定表現（確信バイアス）"
        )
    ]
    for pattern, bg, fg, title in rules:
        for match in re.finditer(pattern, text):
            start, end = (
                match.span(1)
                if match.lastindex
                else match.span(0)
            )
            for idx in range(start, end):
                char_styles[idx] = (bg, fg, title)
    out = []
    i = 0
    n = len(text)
    while i < n:
        style = char_styles[i]
        if style is None:
            ch = text[i]
            out.append(
                "<br>" if ch == "\n"
                else html.escape(ch)
            )
            i += 1
        else:
            j = i
            while j < n and char_styles[j] == style:
                j += 1
            bg, fg, title = style
            segment = html.escape(
                text[i:j]
            ).replace("\n", "<br>")
            out.append(
                f'<mark style="background-color: {bg}; color: {fg}; '
                f'padding: 2px 4px; border-radius: 4px; '
                f'font-weight: bold;" title="{title}">{segment}</mark>'
            )
            i = j
    final_html = "".join(out)
    return f"""
    <div style="background-color: #f8f9fa; padding: 16px;
    border-radius: 8px; border: 1px solid #dee2e6;
    line-height: 2.0; font-size: 16px; color: #212529;">
        {final_html}
    </div>
    """

def generate_feedback_report(res, reader_states):
    t_score = res["total_vulnerability_score"]
    v_score = res["text_vulnerability_score"]
    bonus = res["reader_bonus"]
    if t_score >= 70:
        level_desc = "非常に高く、無批判に信じ込みやすい危険な状態"
        stance = (
            "文章側の強い説得力演出に加え、読み手側の心理状態も重なることで、"
            "情報の真偽を冷静に検証しにくくなっています。"
        )
    elif t_score >= 40:
        level_desc = "中程度"
        stance = (
            "一定の説得力や読みやすさを備えていますが、"
            "一部に主観的な強調や根拠の不足が見られるため、"
            "立ち止まって確認すべき内容です。"
        )
    else:
        level_desc = "低く、比較的冷静に判断できる状態"
        stance = (
            "過度な断定や煽り表現は少ないものの、"
            "情報の前提や出典が正しいかどうかは別途確認が必要です。"
        )
    bonus_text = (
        f"（文章自体のリスク {v_score}点 ＋ "
        f"あなたの心理状態による補正 +{bonus}点）"
        if bonus > 0
        else "（心理状態による追加補正なし）"
    )
    overview = (
        f"この文章は全{res['sentence_count']}文"
        f"（{res['total_chars']}文字）で構成されており、"
        f"総合的な「信じ込みやすさリスク」は "
        f"**{t_score}点（{level_desc}）** です"
        f"{bonus_text}。{stance}"
    )
    good_points = []
    if res["bullet_ratio"] >= 0.3:
        good_points.append(
            f"箇条書き（全体の{int(res['bullet_ratio']*100)}%）が活用されており、"
            "要点が視覚的に整理されている"
        )
    if res["fluency_score"] >= 60:
        good_points.append(
            f"文章構造が整っており、読み手にとって理解しやすい"
            f"（視覚的読みやすさ：{res['fluency_score']}点）"
        )
    if res["number_count"] > 0:
        nums_str = "、".join(res["numbers_found"][:5])
        good_points.append(
            f"具体的な数値・権威表現（{nums_str} など"
            f"計{res['number_count']}箇所）が示されており、"
            "話の具体性が高い"
        )
    if res["speculative_count"] > 0:
        good_points.append(
            f"推量・留保表現が{res['speculative_count']}回使われており、"
            "断定を避ける慎重さが見られる"
        )
    if not good_points:
        good_points.append(
            "過度な装飾や極端な煽り表現が少なく、"
            "落ち着いたトーンで記述されている"
        )
    warning_points = []
    if reader_states["confirmation"]:
        warning_points.append(
            "【心理要因：確証バイアス】"
            "あなた自身の元々の考えと一致しているため、"
            "根拠の甘さを見落としやすくなっています"
        )
    if reader_states["urgency"]:
        warning_points.append(
            "【心理要因：感情・行動衝動】"
            "「今すぐ行動・拡散したい」という気持ちが高まっており、"
            "冷静な検証がスキップされやすい状態です"
        )
    if reader_states["fatigue"]:
        warning_points.append(
            "【心理要因：認知的負荷】"
            "疲労や時間不足により、読みやすい情報を"
            "そのまま事実と錯覚しやすくなっています"
        )
    if res["assertive_count"] > 0:
        warning_points.append(
            f"断定表現が{res['assertive_count']}回使われており、"
            "不確実な事柄も事実であるかのように強く印象づけている"
        )
    if res["emphasis_count"] > 0:
        warning_points.append(
            f"強調表現が{res['emphasis_count']}箇所含まれており、"
            f"感情的な納得感を高めている"
        )
    if res["number_count"] > 0:
        warning_points.append(
            "数値や調査結果が提示されているものの、"
            "そのデータの調査元・母数・算出根拠が"
            "文章内で裏付けられていない可能性がある"
        )
    if not warning_points:
        warning_points.append(
            "言語上の強いバイアス演出は少ないものの、"
            "事実関係の正確性までは保証されていない"
        )
    advices = []
    if bonus > 0:
        advices.append(
            "現在、心理的に情報を受け入れやすい状態になっています。"
            "拡散や購入などの行動に移す前に、"
            "最低でも数分〜1日置いてから見直してください。"
        )
    if res["number_count"] > 0:
        advices.append(
            "黄色くハイライトされた数字や権威表現について、"
            "一次情報が存在するか検索して確認してください。"
        )
    if res["assertive_count"] > 0 or res["emphasis_count"] > 0:
        advices.append(
            "強い断定・強調表現について、"
            "反対の意見や例外ケースがないか確認してください。"
        )
    if not advices:
        advices.append(
            "執筆者の立場や情報発信の目的を確認し、"
            "複数の独立した情報源と照合してください。"
        )
    return overview, good_points, warning_points, advices

def programmatic_extract(text, selected_fields, custom_keywords=None):
    sentences = [
        s.strip()
        for s in re.split(r'(?<=[。！？])|\n', text)
        if s.strip()
    ]
    patterns = {
        "いつ": r'(20\d{2}年|今年|昨年|先月|今月|昨日|今日|明日|\d{1,2}月\d{1,2}日|\d{1,2}月)',
        "どこで": r'(日本|東京都|大阪府|愛知県|北海道|海外|国内|市|県|大学|会社|地域|現場)',
        "誰が": r'(政府|警察|大学|企業|会社|研究者|専門家|消費者|利用者|東京商工リサーチ|[一-龠]{2,}(?:大学|社|庁|省))',
        "何を": r'(発表|開発|調査|研究|販売|導入|増加|減少|倒産|開始|実施|発生|公開)',
        "なぜ": r'(ため|理由|原因|背景|ことから|によって|影響で)',
        "どのように": r'(方法|仕組み|活用|導入|組み合わせ|取り組み|実施)',
        "結果・影響": r'(結果|影響|増加|減少|改善|悪化|記録|過去最多|期待)',
        "情報源・根拠": r'(によると|発表した|公表した|調査|研究|報告|資料|論文|公式)',
        "商品・サービス名": r'(商品|サービス|製品|アプリ|ソフト|システム|ブランド)',
        "価格": r'(\d[\d,]*(?:円|ドル|万円)|無料|有料|価格|料金)',
        "主な特徴": r'(特徴|機能|性能|搭載|対応|サービス)',
        "メリット": r'(利点|メリット|便利|向上|効率|改善|簡単)',
        "デメリット・注意点": r'(欠点|デメリット|注意|リスク|課題|問題|危険)',
        "対象者": r'(対象|利用者|消費者|学生|企業|高齢者|人向け)',
        "販売元・情報源": r'(販売|提供|運営|公式|メーカー|企業)',
        "研究目的": r'(目的|明らかにする|解明|検証|目指す)',
        "研究方法": r'(方法|実験|調査|分析|比較|アンケート)',
        "研究対象": r'(対象|参加者|被験者|学生|利用者|人を対象)',
        "実施時期・場所": r'(20\d{2}年|\d{1,2}月|大学|研究所|地域)',
        "研究結果": r'(結果|判明|示された|確認された|明らかになった)',
        "結論": r'(結論|考えられる|示唆|有効|必要)',
        "限界・注意点": r'(限界|課題|制約|今後|一方で|ただし)',
        "論文・情報源": r'(論文|掲載|学会|研究機関|大学|DOI|出典)',
        "概要": r'(発表|発生|開始|実施|増加|減少|開発|導入|調査|研究)',
        "重要な事実": r'(発表|決定|記録|開始|終了|変更|導入|増加|減少)',
        "日時・数値": r'(\d|今年|昨年|先月|今月|昨日|今日)',
        "関係者・対象": r'(政府|企業|会社|大学|研究者|利用者|消費者|学生|住民)',
        "理由・背景": r'(ため|理由|原因|背景|影響|ことから)',
        "根拠・情報源": r'(によると|発表|公表|調査|研究|報告|資料|論文|公式)',
        "注意点・不明点": r'(注意|課題|問題|可能性|不明|未確認|一方で|ただし)'
    }
    results = {}
    for field in selected_fields:
        pattern = patterns.get(field)
        matched = [
            s for s in sentences
            if pattern and re.search(pattern, s)
        ]
        results[field] = matched[:3]

    custom_results = {}
    if custom_keywords:
        for kw in custom_keywords:
            matched = [
                s for s in sentences
                if re.search(re.escape(kw), s, re.IGNORECASE)
            ]
            custom_results[kw] = matched

    return results, custom_results

def ai_information_review(
    text,
    purpose,
    selected_fields,
    custom_keywords,
    program_results,
    custom_results
):
    client = get_gemini_client()
    if client is None:
        return None, (
            "Gemini APIキーを読み込めません。\n"
            "卒研/.streamlit/secrets.toml の保存場所と"
            "GEMINI_API_KEY の設定を確認してください。"
        )
    all_fields = list(selected_fields) + list(custom_keywords)
    combined_detection = {
        **program_results,
        **{f"【自由記述】{k}": v for k, v in custom_results.items()}
    }
    prompt = f"""
あなたは文章の情報整理を支援するアシスタントです。

以下の文章に書かれている内容だけを根拠に、
情報を整理してください。

書かれていない情報を推測で補わないでください。
不明な場合は「記載なし」としてください。

文章の真偽を断定せず、
情報が記載されているかどうかを判定してください。

用途: {purpose}

確認項目（自由記述で追加されたキーワードも含む）:
{json.dumps(all_fields, ensure_ascii=False)}

プログラムによるキーワード検出結果:
{json.dumps(combined_detection, ensure_ascii=False)}

入力文章:
{text}

次のJSON形式だけで回答してください。

{{
    "summary": "文章全体の短い要約",
    "items": [
        {{
            "field": "確認項目名または自由記述キーワード名",
            "status": "確認できた または 不足",
            "content": "文章に記載された内容やそのキーワードに関する説明。なければ記載なし",
            "reason": "判断理由"
        }}
    ],
    "missing_summary": [
        "不足している情報と、確認するとよい内容"
    ]
}}

確認項目（自由記述キーワード含む）はすべて漏れなく出力してください。
"""
    candidate_models = [
        "gemini-2.5-flash",
        "gemini-2.5-flash-lite",
        "gemini-3.1-flash-lite"
    ]

    last_error = None

    for model_name in candidate_models:
        try:
            response = client.models.generate_content(
                model=model_name,
                contents=prompt,
                config={
                    "response_mime_type": "application/json"
                }
            )
            if not response.text:
                last_error = "Geminiから空の回答が返されました。"
                continue

            data = json.loads(response.text)
            return data, None

        except Exception as e:
            last_error = e
            continue

    return None, f"AI分析でエラーが発生しました（全モデル混雑または失敗）: {last_error}"

st.title("認知バイアス・レントゲン（信じ込みやすさリスク分析）")
st.caption(
    "行いたい分析モードを先に選び、条件を設定してから文章を入力してください。"
)

sample_text = """・最新の調査では利用者の92%が効果を実感している！
・この方法を取り入れるだけで、誰でも確実に結果が出るに違いない。
・今すぐ始めるべきである。"""

if "input_text" not in st.session_state:
    st.session_state.input_text = sample_text

def clear_text():
    st.session_state.input_text = ""
    st.session_state.xray_text_area = ""
    st.session_state.info_text_area = ""

def sync_from_xray():
    val = st.session_state.xray_text_area
    st.session_state.input_text = val
    st.session_state.info_text_area = val

def sync_from_info():
    val = st.session_state.info_text_area
    st.session_state.input_text = val
    st.session_state.xray_text_area = val

st.subheader("1. 分析モードを選択（タブ切り替え）")
tab_xray, tab_info = st.tabs([
    "🩻 認知バイアス・レントゲン分析",
    "📋 情報整理・不足情報チェック"
])

with tab_xray:
    st.markdown("#### ステップ1：今のあなたの状態をチェック（該当するもの）")
    col_c1, col_c2, col_c3 = st.columns(3)
    with col_c1:
        state_confirmation = st.checkbox(
            "自分の考えと一致してスッキリした",
            help="確証バイアス：自分にとって都合の良い情報を信じやすくなります",
            key="chk_confirmation"
        )
    with col_c2:
        state_urgency = st.checkbox(
            "今すぐ行動・誰かに拡散したいと思った",
            help="感情ヒューリスティック：強い感情が動くと批判的思考が低下します",
            key="chk_urgency"
        )
    with col_c3:
        state_fatigue = st.checkbox(
            "今、疲れている・急いでいる",
            help="処理流暢性バイアス：読みやすい文章を無批判に信じやすくなります",
            key="chk_fatigue"
        )

    st.markdown("#### ステップ2：分析したい文章を入力")
    st.session_state.xray_text_area = st.session_state.input_text

    xray_input_text = st.text_area(
        "SNSの投稿、ニュース記事、広告文などを貼り付けてください",
        height=160,
        key="xray_text_area",
        on_change=sync_from_xray
    )

    col_btn_x1, col_btn_x2 = st.columns([3, 1])
    with col_btn_x1:
        submitted = st.button(
            "🩻 レントゲン分析を実行",
            use_container_width=True,
            type="primary"
        )
    with col_btn_x2:
        st.button(
            "🗑️ 文章を消去",
            on_click=clear_text,
            use_container_width=True,
            key="clear_xray"
        )

    if submitted:
        st.session_state.input_text = xray_input_text
        st.session_state.info_text_area = xray_input_text
        if st.session_state.input_text.strip():
            reader_states = {
                "confirmation": state_confirmation,
                "urgency": state_urgency,
                "fatigue": state_fatigue
            }
            result = analyze_text_advanced(
                st.session_state.input_text,
                reader_states
            )
            overview, good_points, warning_points, advices = (
                generate_feedback_report(
                    result,
                    reader_states
                )
            )
            st.divider()
            st.subheader("📊 信じ込みやすさリスク診断")
            col1, col2, col3, col4 = st.columns(4)
            col1.metric(
                "総合リスク（掛け合わせ）",
                f"{result['total_vulnerability_score']} / 100",
                delta=(
                    f"心理補正 +{result['reader_bonus']}点"
                    if result['reader_bonus'] > 0
                    else "補正なし"
                ),
                delta_color="inverse"
            )
            col2.metric(
                "文章単体のリスク",
                f"{result['text_vulnerability_score']} / 100"
            )
            col3.metric(
                "視覚的読みやすさ",
                f"{result['fluency_score']} / 100"
            )
            col4.metric(
                "説得力演出度",
                f"{result['authority_score']} / 100"
            )
            st.subheader(
                "🩻 認知バイアス・レントゲン（仕掛けの可視化）"
            )
            st.markdown(
                """
                <div style="font-size: 13px; margin-bottom: 8px;">
                    凡例：
                    <span style="background-color: #bbdefb; color: #0d47a1; padding: 2px 6px; border-radius: 4px; font-weight: bold;">青：構造化（流暢性）</span>
                    <span style="background-color: #fff9c4; color: #f57f17; padding: 2px 6px; border-radius: 4px; font-weight: bold;">黄：数字・権威（具体性）</span>
                    <span style="background-color: #ffe0b2; color: #e65100; padding: 2px 6px; border-radius: 4px; font-weight: bold;">橙：強調・煽り（感情）</span>
                    <span style="background-color: #ffcdd2; color: #b71c1c; padding: 2px 6px; border-radius: 4px; font-weight: bold;">赤：断定表現（確信）</span>
                </div>
                """,
                unsafe_allow_html=True
            )
            xray_html = render_bias_xray(st.session_state.input_text)
            st.markdown(
                xray_html,
                unsafe_allow_html=True
            )
            st.divider()
            st.markdown("### 💡 全体解説")
            st.write(overview)
            st.markdown("### ✅ 良い点・評価できる点")
            for point in good_points:
                st.markdown(f"- {point}")
            st.markdown("### ⚠️ 疑わしい点・不確実な点")
            for point in warning_points:
                st.markdown(f"- {point}")
            st.markdown("### 📌 ファクトチェックのアドバイス")
            for advice in advices:
                st.info(advice)
        else:
            st.warning(
                "文章を入力してからボタンを押してください。"
            )

with tab_info:
    st.markdown("#### ステップ1：文章の用途と確認したい項目・キーワードを設定")
    purpose = st.selectbox(
        "文章の用途を選択",
        list(PURPOSE_FIELDS.keys()),
        key="info_purpose"
    )

    selected_fields = st.multiselect(
        "確認したい項目を選択（複数選択可）",
        options=PURPOSE_FIELDS[purpose],
        default=PURPOSE_FIELDS[purpose],
        key=f"fields_{purpose}"
    )

    custom_keywords_input = st.text_input(
        "追加で確認したいキーワード（自由記述・複数ある場合は「、」や「,」で区切る）",
        placeholder="例：副作用、返金保証、対象年齢、調査人数",
        key="custom_keywords_input"
    )

    st.markdown("#### ステップ2：分析したい文章を入力")
    st.session_state.info_text_area = st.session_state.input_text

    info_input_text = st.text_area(
        "整理・不足チェックを行いたい文章を貼り付けてください",
        height=160,
        key="info_text_area",
        on_change=sync_from_info
    )

    col_btn_i1, col_btn_i2 = st.columns([3, 1])
    with col_btn_i1:
        info_submitted = st.button(
            "📋 情報整理・不足情報を分析",
            use_container_width=True,
            type="primary"
        )
    with col_btn_i2:
        st.button(
            "🗑️ 文章を消去",
            on_click=clear_text,
            use_container_width=True,
            key="clear_info"
        )

    if info_submitted:
        st.session_state.input_text = info_input_text
        st.session_state.xray_text_area = info_input_text
        current_text = st.session_state.input_text.strip()
        custom_keywords = [
            kw.strip()
            for kw in re.split(r'[,、，\s]+', custom_keywords_input)
            if kw.strip()
        ]
        if not current_text:
            st.warning("先に分析したい文章を入力してください。")
        elif not selected_fields and not custom_keywords:
            st.warning("確認したい項目を1つ以上選択するか、キーワードを入力してください。")
        else:
            with st.spinner("文章を整理しています..."):
                program_results, custom_results = programmatic_extract(
                    current_text,
                    selected_fields,
                    custom_keywords
                )
                ai_result, ai_error = ai_information_review(
                    current_text,
                    purpose,
                    selected_fields,
                    custom_keywords,
                    program_results,
                    custom_results
                )

            st.divider()
            st.subheader("① プログラムによるキーワード検出")
            if program_results:
                kw_cols = st.columns(4)
                for idx, (field, matches) in enumerate(program_results.items()):
                    with kw_cols[idx % 4]:
                        label = f"{field} ({len(matches)}件)" if matches else f"{field} (0件)"
                        with st.popover(label, use_container_width=True):
                            st.markdown(f"**{field}**")
                            if matches:
                                for sentence in matches:
                                    st.write(f"・{sentence}")
                            else:
                                st.caption("関連するキーワードは検出されませんでした。")

            if custom_results:
                st.markdown("##### 🔎 自由記述キーワードの検出結果（有無チェック）")
                ckw_cols = st.columns(4)
                for idx, (kw, matches) in enumerate(custom_results.items()):
                    with ckw_cols[idx % 4]:
                        status_mark = f"あり ({len(matches)}件)" if matches else "なし (0件)"
                        with st.popover(f"「{kw}」: {status_mark}", use_container_width=True):
                            st.markdown(f"**キーワード：{kw}**")
                            if matches:
                                st.success(f"文章内に「{kw}」が含まれています（{len(matches)}文）")
                                for sentence in matches:
                                    st.write(f"・{sentence}")
                            else:
                                st.warning(f"文章内に「{kw}」は見つかりませんでした。")

            if ai_error:
                st.error(ai_error)
            if ai_result:
                st.subheader("② AIによる情報整理")
                st.write(
                    ai_result.get(
                        "summary",
                        "要約はありません。"
                    )
                )
                st.subheader("③ 項目・キーワードごとの確認結果（説明）")
                items = ai_result.get("items", [])
                for item in items:
                    status = item.get("status", "不明")
                    field_name = item.get("field", "")
                    is_custom = field_name in custom_keywords
                    display_title = f"【自由記述】{field_name}" if is_custom else field_name
                    if status == "確認できた":
                        st.success(
                            f"✓ {display_title}"
                        )
                    else:
                        st.warning(
                            f"不足：{display_title}"
                        )
                    st.write(
                        item.get("content", "記載なし")
                    )
                    if item.get("reason"):
                        st.caption(item["reason"])
                st.subheader("④ 最後に不足している情報")
                missing = ai_result.get("missing_summary", [])
                if missing:
                    for item in missing:
                        st.write(f"・{item}")
                else:
                    st.success(
                        "選択した項目について、"
                        "明確な不足情報は検出されませんでした。"
                    )
                st.caption(
                    "※AIの判定は文章内の記載状況を整理するもので、"
                    "情報の真偽や正確性を保証するものではありません。"
                )
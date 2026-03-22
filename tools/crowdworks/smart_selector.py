"""
スマートセレクタ — CSSセレクタが壊れた場合にAIフォールバックで要素を特定

通常のCSSセレクタで要素が見つからない場合、ページのHTMLをClaudeに渡して
適切なセレクタを推定させる。これにより、CrowdWorksのHTML構造が変わっても
自動的に適応できる。
"""

import os
import json
from anthropic import Anthropic

MODEL = os.environ.get("SMART_SELECTOR_MODEL", "claude-sonnet-4-6")

# セレクタキャッシュ（セッション内で同じ推定を繰り返さないように）
_selector_cache = {}


async def smart_find(page, selectors, purpose, timeout=5000):
    """
    複数のCSSセレクタを試し、どれも見つからなければAIで推定する。

    Args:
        page: Playwrightのページオブジェクト
        selectors: 試すCSSセレクタのリスト（優先順）
        purpose: この要素の目的（例: "ログインボタン", "提案文入力欄"）
        timeout: 各セレクタの待機時間(ms)

    Returns:
        見つかったLocator、またはNone
    """
    # 1. 既知のセレクタを順に試す
    for selector in selectors:
        try:
            locator = page.locator(selector)
            count = await locator.count()
            if count > 0:
                return locator.first
        except Exception:
            continue

    # 2. キャッシュに推定済みセレクタがあればそれを試す
    cache_key = purpose
    if cache_key in _selector_cache:
        cached = _selector_cache[cache_key]
        try:
            locator = page.locator(cached)
            if await locator.count() > 0:
                return locator.first
        except Exception:
            pass

    # 3. AIフォールバック：ページのHTMLからセレクタを推定
    print(f"  ⚠️ セレクタ未ヒット [{purpose}] → AI推定を試行...")
    ai_selector = await _ai_infer_selector(page, purpose)

    if ai_selector:
        try:
            locator = page.locator(ai_selector)
            if await locator.count() > 0:
                _selector_cache[cache_key] = ai_selector
                print(f"  ✅ AI推定成功: {ai_selector}")
                return locator.first
        except Exception:
            pass

    print(f"  ❌ [{purpose}] の要素が見つかりません")
    return None


async def _ai_infer_selector(page, purpose):
    """ページのHTML構造からAIがCSSセレクタを推定"""
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        return None

    try:
        # ページのHTML（bodyのみ、サイズ制限）を取得
        html_snippet = await page.evaluate("""
            () => {
                const body = document.body;
                if (!body) return '';

                // フォーム要素・ボタン・リンク・入力欄を中心に抽出
                const important = body.querySelectorAll(
                    'form, button, input, textarea, a[href], select, [role="button"], ' +
                    '[type="submit"], .btn, [class*="button"], [class*="submit"], ' +
                    '[class*="login"], [class*="message"], [class*="proposal"], ' +
                    '[class*="apply"], [class*="thread"]'
                );

                const snippets = [];
                for (const el of important) {
                    // outerHTMLを短縮（子要素は省略）
                    const clone = el.cloneNode(false);
                    let html = clone.outerHTML;
                    if (html.length > 300) {
                        html = html.substring(0, 300) + '...>';
                    }
                    snippets.push(html);
                }
                return snippets.join('\\n');
            }
        """)

        if not html_snippet or len(html_snippet) < 10:
            return None

        # トークン節約のためHTMLを10000文字に制限
        if len(html_snippet) > 10000:
            html_snippet = html_snippet[:10000]

        client = Anthropic()
        response = client.messages.create(
            model=MODEL,
            max_tokens=150,
            messages=[{
                "role": "user",
                "content": (
                    f"以下はWebページのHTML要素の抜粋です。\n"
                    f"「{purpose}」に該当する要素のCSSセレクタを1つだけ返してください。\n"
                    f"セレクタのみを返してください（説明不要）。\n"
                    f"該当する要素がなければ「NONE」と返してください。\n\n"
                    f"```html\n{html_snippet}\n```"
                ),
            }],
        )

        result = response.content[0].text.strip()

        # 余分な記号を除去
        result = result.strip("`").strip('"').strip("'").strip()

        if result == "NONE" or not result or len(result) > 200:
            return None

        return result

    except Exception as e:
        print(f"  → AI推定エラー: {e}")
        return None


def clear_cache():
    """セレクタキャッシュをクリア"""
    global _selector_cache
    _selector_cache = {}

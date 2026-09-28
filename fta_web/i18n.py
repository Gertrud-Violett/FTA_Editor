"""
Server-side message localization for the fta_web API.

Scope, deliberately bounded
---------------------------
Only the error messages a user *reads in a toast* are translated here -- the
capability and permission failures (``AI_NOT_CONFIGURED``, ``PATH_REJECTED``,
``RENDERER_UNAVAILABLE`` ...). Field-validation messages that interpolate
context ("Parent node 'root_5' not found") are left in English: they carry a
node id or a path that is the actionable part, they are developer-facing, and
templating each of ~60 call sites 1:1 would be a large, risky change this late
for little user-facing gain.

How it is applied
-----------------
Route code keeps raising English ``ApiError``. Every ``ApiError`` handler --
the app-level one in ``app.py`` and the per-blueprint ones in ``routes/*`` --
goes through :func:`errors.api_error_response`, which calls
:func:`localize_error` with :func:`request_language`: if the request asks for
Japanese *and* the error's ``code`` has a Japanese entry below, the ``message``
is swapped. The ``code`` and ``detail`` fields are never touched -- ``code`` is
machine-readable, and ``detail`` holds the ids and paths a user needs verbatim.

Language selection
------------------
``?lang=ja`` wins if present; otherwise the first language tag in
``Accept-Language`` that we support; otherwise English.
"""
from __future__ import annotations

from typing import Dict, Optional

try:  # normal package import
    from . import config
except ImportError:  # fallback: fta_web/ itself on sys.path
    import config  # type: ignore[no-redef]


#: code -> {lang -> message}. A code absent here, or present without the
#: requested language, falls through to whatever the route raised (English).
_MESSAGES: Dict[str, Dict[str, str]] = {
    "AI_NOT_CONFIGURED": {
        "ja": "AIアシスタントが設定されていません。AI設定でプロバイダーとAPIキーを追加してください。",
    },
    "RENDERER_UNAVAILABLE": {
        "ja": (
            "この操作にはシステムにインストールされたGraphvizが必要です。"
            "graphviz.org からインストールして再起動すると、自動的に使用されます。"
            "図はブラウザ内でも描画されているため、画面表示には影響ありません。"
        ),
    },
    "EXPORT_UNAVAILABLE": {
        "ja": (
            "Excelエクスポートには 'openpyxl' パッケージが必要ですが、"
            "このマシンにはインストールされていません。"
            "'pip install openpyxl' を実行してエディターを再起動してください。"
            "JSONとXMLのエクスポートには必要ありません。"
        ),
    },
    # Keyed "<code>:<detail.format>" -- consulted before the bare code, so one
    # error code can carry a format-specific message (see localize_error).
    "EXPORT_UNAVAILABLE:docx": {
        "ja": (
            "DOCXレポートには 'python-docx' パッケージが必要ですが、"
            "このマシンにはインストールされていません。"
            "'uv sync --extra report' を実行してエディターを再起動してください。"
        ),
    },
    # "<code>:<detail.format>:<detail.feature>" -- the FMEA import reads .xlsx
    # through openpyxl too, but it is not an Excel *export*.
    "EXPORT_UNAVAILABLE:xlsx:fmea": {
        "ja": (
            ".xlsx形式のFMEAシートの読み込みには 'openpyxl' パッケージが必要ですが、"
            "このマシンにはインストールされていません。"
            "'pip install openpyxl' を実行してエディターを再起動するか、"
            "シートを .csv で保存してそちらを取り込んでください。"
        ),
    },
    "MODE_UNSUPPORTED": {
        "ja": "この解析はFTAモードでのみ使用できます。ETAモードでは利用できません。",
    },
    "BUSY": {
        "ja": "不確かさ解析はすでに実行中です。完了してから再度実行してください。",
    },
    "ANALYSIS_TOO_LARGE": {
        "ja": "解析対象が大きすぎるため計算を中止しました。カットセットの上限を下げるか、ツリーを簡略化してください。",
    },
    # "<code>:<detail.reason>"
    "ANALYSIS_TOO_LARGE:kofn": {
        "ja": (
            "投票ゲート（k/n）の組み合わせが多すぎて展開できません。"
            "入力数を減らすか、ゲートを分割してください。"
        ),
    },
    "ANALYSIS_TOO_LARGE:time": {
        "ja": (
            "カットセット計算が制限時間を超えました。"
            "最大次数や最大件数を下げるか、カットオフを大きくしてください。"
        ),
    },
    "NOT_IMPLEMENTED": {
        "ja": "この機能はまだ実装されていません。",
    },
    "PATH_REJECTED": {
        "ja": "指定されたパスは許可されたフォルダーの外にあるか、無効です。",
    },
    "NO_CURRENT_PATH": {
        "ja": "この分析はまだ保存されていません。「名前を付けて保存」を使用してください。",
    },
    "UNSAVED_CHANGES": {
        "ja": "保存されていない変更があります。続行すると失われます。",
    },
    "ROOT_PROTECTED": {
        "ja": "ルートノードは削除・移動できません。",
    },
    "CYCLE_REJECTED": {
        "ja": "その移動はツリーに循環を作成するため実行できません。",
    },
    "NOTHING_TO_UNDO": {
        "ja": "元に戻す操作はありません。",
    },
    "NOTHING_TO_REDO": {
        "ja": "やり直す操作はありません。",
    },
    "FORBIDDEN": {
        "ja": "セッショントークンがないか無効です。ターミナルからアプリを再起動してください。",
    },
    "NOT_FOUND": {
        "ja": "そのエンドポイントは存在しません。",
    },
    "METHOD_NOT_ALLOWED": {
        "ja": "このエンドポイントでは許可されていないメソッドです。",
    },
    "PAYLOAD_TOO_LARGE": {
        "ja": "リクエスト本文がサイズ上限を超えています。",
    },
    "INTERNAL_ERROR": {
        "ja": "サーバー内部エラーが発生しました。サーバーログを確認してください。",
    },
}


def _parse_accept_language(header: str) -> list:
    """Ordered list of language tags from an Accept-Language header, best first.

    Quality values are honoured for ordering; malformed parts are skipped
    rather than raising -- this runs in an error path and must not add a
    second failure.
    """
    parsed = []
    for part in header.split(","):
        part = part.strip()
        if not part:
            continue
        tag, _, params = part.partition(";")
        q = 1.0
        if params.strip().startswith("q="):
            try:
                q = float(params.strip()[2:])
            except ValueError:
                q = 0.0
        tag = tag.strip().lower()
        if tag:
            parsed.append((q, tag))
    parsed.sort(key=lambda t: t[0], reverse=True)
    return [tag for _q, tag in parsed]


def resolve_language(
    lang_param: Optional[str], accept_language: Optional[str]
) -> str:
    """Pick a supported language. ``?lang=`` wins, then Accept-Language, then en."""
    supported = set(config.SUPPORTED_LANGUAGES)

    if lang_param:
        candidate = lang_param.strip().lower()
        if candidate in supported:
            return candidate
        # "ja-JP" -> "ja"
        if candidate.split("-")[0] in supported:
            return candidate.split("-")[0]

    for tag in _parse_accept_language(accept_language or ""):
        if tag in supported:
            return tag
        if tag.split("-")[0] in supported:
            return tag.split("-")[0]

    return config.DEFAULT_LANGUAGE


def request_language() -> str:
    """The language to answer the current request's errors in. Never raises.

    Safe to call outside a request context too (it then answers the default):
    this runs in error paths, which must not add a second failure.
    """
    try:
        from flask import request

        return resolve_language(
            request.args.get("lang"), request.headers.get("Accept-Language")
        )
    except Exception:
        return config.DEFAULT_LANGUAGE


def localize_message(code: str, message: str, language: str) -> str:
    """Swap ``message`` for its localized form when one exists; else unchanged."""
    if language == config.DEFAULT_LANGUAGE:
        return message
    return _MESSAGES.get(code, {}).get(language, message)


def localize_error(payload: dict, language: str) -> dict:
    """Localize the ``message`` inside an ``{"ok": false, "error": {...}}`` body.

    Returns a new dict; the input is not mutated. ``code`` and ``detail`` are
    passed through untouched.
    """
    error = payload.get("error")
    if not isinstance(error, dict) or "code" not in error:
        return payload
    localized = dict(error)
    code = error["code"]
    detail = error.get("detail")
    if isinstance(detail, dict) and language != config.DEFAULT_LANGUAGE:
        # Most specific first: code:format:feature, code:format, code:reason.
        fmt = detail.get("format")
        feature = detail.get("feature")
        reason = detail.get("reason")
        candidates = []
        if isinstance(fmt, str) and isinstance(feature, str):
            candidates.append("%s:%s:%s" % (code, fmt, feature))
        if isinstance(fmt, str):
            candidates.append("%s:%s" % (code, fmt))
        if isinstance(reason, str) and reason:
            candidates.append("%s:%s" % (code, reason))
        for specific in candidates:
            if language in _MESSAGES.get(specific, {}):
                code = specific
                break
    localized["message"] = localize_message(
        code, error.get("message", ""), language
    )
    out = dict(payload)
    out["error"] = localized
    return out

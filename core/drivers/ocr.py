"""
图片文字识别（OCR）驱动
==========================
基于 RapidOCR（PaddleOCR 的 ONNX 轻量版，模型自带、离线、中文友好）。

懒加载：首次调用才初始化模型；未安装时抛出带安装提示的 RuntimeError，
不影响截图保存等其它功能。
"""
from __future__ import annotations

from typing import Any, Dict, List

try:
    from rapidocr import RapidOCR                        # v2：PP-OCRv6 模型，精度更高
    _ENGINE_VER = 2
    HAS_OCR = True
    IMPORT_ERROR = ""
except Exception:                                        # pragma: no cover
    try:
        from rapidocr_onnxruntime import RapidOCR       # 旧包回退
        _ENGINE_VER = 1
        HAS_OCR = True
        IMPORT_ERROR = ""
    except Exception as exc:                             # pragma: no cover
        RapidOCR = None
        _ENGINE_VER = 0
        HAS_OCR = False
        IMPORT_ERROR = str(exc)

INSTALL_HINT = "提取图片内容需要 OCR 组件，请先安装：pip install rapidocr"


def install_hint() -> str:
    """给用户的安装提示；导入失败时附带真实原因，方便定位环境问题。"""
    if IMPORT_ERROR:
        return f"{INSTALL_HINT}（导入失败原因：{IMPORT_ERROR}）"
    return INSTALL_HINT

_engine = None                                               # 懒加载单例


def _get_engine():
    global _engine
    if not HAS_OCR:
        raise RuntimeError(INSTALL_HINT)
    if _engine is None:
        if _ENGINE_VER == 2:
            # unclip_ratio 调小：检测框不再过度外扩，相邻数字不再粘成一个框
            # （"8.8  0.01" 曾被识别成 "8.80.01"）；关方向分类：屏幕文字不会倒置，省时间
            _engine = RapidOCR(params={
                "Det.unclip_ratio": 0.9,
                "Global.use_cls": False,
                "Global.log_level": "error",
            })
        else:
            _engine = RapidOCR()
    return _engine


def _preprocess(img):
    """识别前预处理：放大 2 倍 + 灰度对比度增强。

    小字号文字（尤其是小数点、逗号这类标点）在原分辨率下经常丢笔画，
    放大后识别率显著提升；返回 BGR numpy 数组（坐标为放大后的，仅用于
    排序/聚类，无需换算回原图）。
    """
    import cv2
    import numpy as np

    if isinstance(img, str):
        arr = cv2.imread(img)
    else:
        arr = np.array(img)
        if arr.ndim == 2:
            arr = cv2.cvtColor(arr, cv2.COLOR_GRAY2BGR)
        elif arr.shape[2] == 4:
            arr = cv2.cvtColor(arr, cv2.COLOR_RGBA2BGR)
        elif arr.shape[2] == 3 and arr.dtype != np.uint8:
            arr = arr.astype(np.uint8)
    if arr is None:
        raise RuntimeError("无法读取图片，OCR 提取失败")
    h, w = arr.shape[:2]
    # 缩放统一在这里做：
    # - 小图放大到最短边 736：小字放大后识别率显著提升（原检测模型的默认行为）
    # - 超大图（>3000）缩到 3000，控制检测耗时
    if min(h, w) < 736:
        s = 736.0 / min(h, w)
        arr = cv2.resize(arr, None, fx=s, fy=s, interpolation=cv2.INTER_CUBIC)
    elif max(h, w) > 3000:
        s = 3000.0 / max(h, w)
        arr = cv2.resize(arr, None, fx=s, fy=s, interpolation=cv2.INTER_AREA)
    gray = cv2.cvtColor(arr, cv2.COLOR_BGR2GRAY)
    gray = cv2.normalize(gray, None, 0, 255, cv2.NORM_MINMAX)
    return cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)


def _engine_regions(arr) -> List[Dict[str, Any]]:
    """对预处理后的图像跑引擎，返回 [{'text', 'box', 'score'}]。"""
    result = _get_engine()(arr)
    out = []
    if _ENGINE_VER == 2:                                 # v2：RapidOCROutput 对象
        boxes = result.boxes if getattr(result, "boxes", None) is not None else []
        txts = result.txts if getattr(result, "txts", None) is not None else []
        scores = result.scores if getattr(result, "scores", None) is not None else []
        items = [(b, t, s) for b, t, s in zip(boxes, txts, scores)
                 if b is not None and t is not None]
    else:                                                # v1：[(box, text, score), ...]
        items = result[0] or []
    for box, text, score in items:
        out.append({
            "text": str(text).strip(),
            "box": [(float(x), float(y)) for x, y in box],
            "score": float(score),
        })
    return [r for r in out if r["text"]]


def ocr_regions(img) -> List[Dict[str, Any]]:
    """识别图片，返回 [{'text', 'box', 'score'}]，box 为四个角点 [(x, y), ...]。"""
    return _engine_regions(_preprocess(img))


# ------------------------------------------------------------------ 表格行分隔线检测
def _row_bands(arr):
    """按文字投影 + 细横线归并出逻辑行带 [(y0, y1), ...]。

    单元格内容换行时，一个逻辑行在屏幕上占多条可视行。折行碎片之间没有
    分隔线，按垂直空隙（小于约 1.2 个字高）并成一带；检测到细横线（真行
    分隔线）则强制断带。表头灰底、斑马纹行带是厚块，不算细线——传统
    "检测横线"做法会把它们误判为线，把两行表头拆散。
    """
    import cv2
    import numpy as np

    gray = cv2.cvtColor(arr, cv2.COLOR_BGR2GRAY)
    h, w = gray.shape
    if h < 40 or w < 80:
        return []
    dark = (gray < 200).mean(axis=1) > 0.01
    text_ys = np.where(dark)[0]
    if len(text_ys) < 2:
        return []
    # 连续文字行聚成可视行（允许 3px 内的断裂）
    lines = []
    start = prev = int(text_ys[0])
    for y in text_ys[1:]:
        y = int(y)
        if y - prev <= 3:
            prev = y
        else:
            lines.append((start, prev))
            start = prev = y
    lines.append((start, prev))
    heights = sorted(e - s + 1 for s, e in lines)
    lh = max(8.0, float(heights[len(heights) // 2]))   # 典型字高

    # 细横线位置：低方差非白行聚簇，只保留 ≤4px 高的细簇（厚块=底色/斑马纹）
    cand = ((gray < 248).mean(axis=1) > 0.8) & (gray.std(axis=1) < 12) & (~dark)
    sep_ys = []
    ys = np.where(cand)[0]
    if len(ys):
        start = prev = int(ys[0])
        for y in ys[1:]:
            y = int(y)
            if y - prev <= 2:
                prev = y
            else:
                if prev - start + 1 <= 4:
                    sep_ys.append((start + prev) // 2)
                start = prev = y
        if prev - start + 1 <= 4:
            sep_ys.append((start + prev) // 2)

    # 并带：碎片间无细线且空隙小 → 同单元格折行；有细线或空隙大 → 断带
    thr = 1.2 * lh if sep_ys else 0.8 * lh
    bands = []
    for s, e in lines:
        if bands:
            g0, g1 = bands[-1][1], s
            forced = any(g0 < sy < g1 for sy in sep_ys)
            if forced:
                bands.append((s, e))
            elif g1 - g0 <= thr + 1:
                bands[-1] = (bands[-1][0], e)
            else:
                bands.append((s, e))
        else:
            bands.append((s, e))
    bands = [(max(0, y0 - 4), min(h, y1 + 5)) for y0, y1 in bands]
    return bands if len(bands) >= 2 else []


def _is_cjk(ch: str) -> bool:
    return "一" <= ch <= "鿿"


def _join_cell(a: str, b: str) -> str:
    """拼接同一单元格内换行的文字碎片。

    换行折点不可见，按规则还原：前一片以 -/_/ . 结尾（kimi- / chatcmpl- /
    2026-09-）或是中文（项目名/称）时直接相连；否则按词折行，补一个空格。
    """
    if not a:
        return b
    if not b:
        return a
    if a.endswith(("-", "_", ".")) or _is_cjk(a[-1]) or _is_cjk(b[0]):
        return a + b
    return a + " " + b


# ------------------------------------------------------------------ 阅读顺序分行
def _top(r) -> float:
    return min(p[1] for p in r["box"])


def _bottom(r) -> float:
    return max(p[1] for p in r["box"])


def _left(r) -> float:
    return min(p[0] for p in r["box"])


def _reading_lines(regions: List[Dict[str, Any]]) -> List[List[Dict[str, Any]]]:
    """按阅读顺序把识别块分行：从上到下，同一水平带内从左到右。"""
    if not regions:
        return []
    ordered = sorted(regions, key=lambda r: (_top(r), _left(r)))
    bands: List[Dict[str, Any]] = []
    for r in ordered:
        rt, rb = _top(r), _bottom(r)
        for band in bands:
            # 与带内已有块垂直重叠即视为同一行
            if any(rt < _bottom(o) and _top(o) < rb for o in band):
                band.append(r)
                break
        else:
            bands.append([r])
    bands.sort(key=lambda b: _top(b[0]))
    return [sorted(b, key=_left) for b in bands]


def image_to_text(img) -> str:
    """提取图片中的全部文字，按行拼接。"""
    lines = _reading_lines(ocr_regions(img))
    return "\n".join(" ".join(r["text"] for r in line) for line in lines)


def image_to_table(img) -> List[Dict[str, Any]]:
    """把图片中的表格提取成表格变量（list[dict]，首行为列名）。

    做法：OCR 拿到每个单元格的文字和位置 → 按行分隔横线归并出逻辑行
    （单元格换行的碎片拼回一个单元格；无分隔线时退化为一条可视行=一行）
    → 按水平中心点聚成列 → 首行作为列名，其余为数据行。
    """
    arr = _preprocess(img)
    regions = _engine_regions(arr)
    if not regions:
        return []

    bands = _row_bands(arr)
    if bands:
        lines = []
        for y0, y1 in bands:
            rs = [r for r in regions
                  if y0 <= (_top(r) + _bottom(r)) / 2.0 < y1]
            if rs:
                lines.append(sorted(rs, key=_left))
        # 落在分隔线缝隙里的碎片（中心点不在任何带内）并入最近的行带，避免丢字
        assigned = {id(r) for line in lines for r in line}
        for r in regions:
            if id(r) in assigned:
                continue
            c = (_top(r) + _bottom(r)) / 2.0
            bi = min(range(len(bands)),
                     key=lambda i: min(abs(c - bands[i][0]), abs(c - bands[i][1])))
            y0, y1 = bands[bi]
            if min(abs(c - y0), abs(c - y1)) <= 20.0:
                while len(lines) <= bi:                 # 理论上带都有内容，兜底
                    lines.append([])
                lines[bi].append(r)
        lines = [sorted(line, key=_left) for line in lines if line]
    else:
        lines = _reading_lines(regions)
    if not lines:
        return []

    # ---- 列聚类：左边缘为主，中心、右边缘为辅
    # 折行碎片宽度差异大（chatcmpl- vs 6ab7d0bab8e...），中心点会跑偏被拆成
    # 两列。左对齐碎片左边缘重合、右对齐碎片右边缘重合、居中碎片中心重合，
    # 三个指标取最近距离归列，覆盖所有对齐方式。
    def x0(r) -> float:
        return _left(r)

    def cx(r) -> float:
        return sum(p[0] for p in r["box"]) / 4.0

    def x1(r) -> float:
        return max(p[0] for p in r["box"])

    box_w = sorted(max(8.0, x1(r) - _left(r))
                   for line in lines for r in line)
    thr = max(24.0, 0.4 * box_w[len(box_w) // 2]) if box_w else 24.0

    cols: List[List[float]] = []                         # [x0_avg, cx_avg, x1_avg, n]
    for line in lines:
        for r in line:
            x, c, e = x0(r), cx(r), x1(r)
            best, best_d = -1, None
            for i, col in enumerate(cols):
                d = min(abs(x - col[0]), abs(c - col[1]), abs(e - col[2]))
                if d <= thr and (best_d is None or d < best_d):
                    best, best_d = i, d
            if best < 0:
                cols.append([x, c, e, 1.0])
            else:
                col = cols[best]
                n = col[3]
                cols[best] = [(col[0] * n + x) / (n + 1),
                              (col[1] * n + c) / (n + 1),
                              (col[2] * n + e) / (n + 1),
                              n + 1]
    cols.sort(key=lambda t: t[0])

    def col_of(r) -> int:
        x, c, e = x0(r), cx(r), x1(r)
        return min(range(len(cols)),
                   key=lambda i: min(abs(x - cols[i][0]),
                                     abs(c - cols[i][1]),
                                     abs(e - cols[i][2])))

    # ---- 组装矩阵（同带同列的碎片按垂直位置自上而下拼接，折行碎片拼回一个单元格）
    matrix: List[List[str]] = []
    for line in lines:
        cols_map: Dict[int, List[Dict[str, Any]]] = {}
        for r in line:
            cols_map.setdefault(col_of(r), []).append(r)
        row: Dict[int, str] = {}
        for c, rs in cols_map.items():
            text = ""
            for r in sorted(rs, key=_top):
                text = _join_cell(text, r["text"])
            row[c] = text
        matrix.append([row.get(c, "") for c in range(len(cols))])

    # ---- 首行列名：去空白、去重，空名/重名补后缀
    headers: List[str] = []
    seen: Dict[str, int] = {}
    for i, cell in enumerate(matrix[0]):
        name = cell.strip() or f"列{i + 1}"
        if name in seen:
            seen[name] += 1
            name = f"{name}_{seen[name]}"
        else:
            seen[name] = 1
        headers.append(name)
    return [dict(zip(headers, row)) for row in matrix[1:]]

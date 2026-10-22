const pptxgen = require("pptxgenjs");
const React = require("react");
const ReactDOMServer = require("react-dom/server");
const sharp = require("sharp");
const {
  FaBrain,
  FaUser,
  FaRobot,
  FaExclamationTriangle,
  FaChartLine,
  FaCogs,
  FaCheckCircle,
  FaSearch,
  FaBolt,
  FaEye,
  FaBalanceScale,
  FaRocket,
  FaHandshake,
  FaClock,
  FaLayerGroup,
  FaSyncAlt,
  FaDatabase,
  FaShieldAlt,
} = require("react-icons/fa");

// ── Palette: Financial Terminal ──
// Deep ocean tones evoke Bloomberg/Reuters terminals, trust, and precision.
// Teal accent for data highlights; amber for warnings; emerald for positive.
const C = {
  navy:      "0B1929",
  deepNavy:  "060F1A",
  slate:     "152238",
  accent:    "0EA5E9",
  accentLt:  "38BDF8",
  gold:      "F59E0B",
  green:     "34D399",
  red:       "F87171",
  ice:       "E0F2FE",
  white:     "FFFFFF",
  gray:      "94A3B8",
  grayDk:    "64748B",
  grayLt:    "CBD5E1",
  text:      "E2E8F0",
  muted:     "7B8FA3",
  cardBg:    "0F2035",
  cardBdr:   "1A3550",
};

const FONT = { head: "Songti SC", body: "PingFang SC", mono: "Consolas" };

// ── Icon helper ──
function renderIconSvg(IconComponent, color, size = 256) {
  return ReactDOMServer.renderToStaticMarkup(
    React.createElement(IconComponent, { color, size: String(size) })
  );
}
async function iconToBase64(IconComponent, color, size = 256) {
  const svg = renderIconSvg(IconComponent, color, size);
  const buf = await sharp(Buffer.from(svg)).png().toBuffer();
  return "image/png;base64," + buf.toString("base64");
}

// ── Reusable factories (never reuse option objects!) ──
const shadow = () => ({ type: "outer", blur: 8, offset: 3, angle: 135, color: "000000", opacity: 0.25 });
const cardShadow = () => ({ type: "outer", blur: 6, offset: 2, angle: 135, color: "000000", opacity: 0.2 });

function addPageNum(slide, num) {
  slide.addText(String(num), {
    x: 9.2, y: 5.2, w: 0.6, h: 0.3,
    fontSize: 9, fontFace: FONT.body, color: C.grayDk, align: "right",
  });
}

function addSectionTag(slide, tag) {
  const tw = tag.length * 0.09 + 0.35;
  slide.addShape("rect", {
    x: 0.5, y: 0.35, w: tw, h: 0.26,
    fill: { color: C.accent, transparency: 50 },
    line: { color: C.accent, width: 0.5 },
  });
  slide.addText(tag.toUpperCase(), {
    x: 0.5, y: 0.35, w: tw, h: 0.26,
    fontSize: 8, fontFace: FONT.body, color: C.white,
    bold: true, align: "center", valign: "middle", charSpacing: 3, margin: 0,
  });
}

function addSlideTitle(slide, title, opts = {}) {
  const y = opts.y || 0.68;
  slide.addText(title, {
    x: 0.5, y, w: 9, h: 0.55,
    fontSize: opts.fontSize || 28, fontFace: FONT.head,
    color: C.white, bold: true, margin: 0,
  });
}

function darkBg(slide) {
  slide.background = { color: C.navy };
}

function addCard(slide, x, y, w, h) {
  slide.addShape("rect", {
    x, y, w, h,
    fill: { color: C.cardBg }, shadow: cardShadow(),
    line: { color: C.cardBdr, width: 0.5 },
  });
}

// ── Main ──
async function main() {
  const pres = new pptxgen();
  pres.layout = "LAYOUT_16x9";
  pres.author = "MarketStream Team";
  pres.title = "MarketStream Progress Report — May 2026";

  // Pre-render icons
  const icons = {};
  const iconList = [
    ["brain", FaBrain, C.accentLt],
    ["user", FaUser, C.accentLt],
    ["robot", FaRobot, C.white],
    ["warn", FaExclamationTriangle, C.gold],
    ["chart", FaChartLine, C.green],
    ["cogs", FaCogs, C.white],
    ["check", FaCheckCircle, C.green],
    ["search", FaSearch, C.white],
    ["bolt", FaBolt, C.accentLt],
    ["eye", FaEye, C.white],
    ["balance", FaBalanceScale, C.white],
    ["rocket", FaRocket, C.accentLt],
    ["handshake", FaHandshake, C.green],
    ["clock", FaClock, C.white],
    ["layers", FaLayerGroup, C.white],
    ["sync", FaSyncAlt, C.green],
    ["db", FaDatabase, C.white],
    ["shield", FaShieldAlt, C.white],
  ];
  for (const [k, Ico, col] of iconList) {
    icons[k] = await iconToBase64(Ico, `#${col}`);
  }

  // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  // SLIDE 1 — Title
  // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  {
    const s = pres.addSlide();
    s.background = { color: C.deepNavy };
    s.addShape("rect", { x: 0, y: 0, w: 10, h: 0.06, fill: { color: C.accent } });
    s.addShape("rect", { x: 0, y: 5.565, w: 10, h: 0.06, fill: { color: C.accent } });

    s.addText("MarketStream", {
      x: 0.8, y: 1.1, w: 8.4, h: 0.8,
      fontSize: 44, fontFace: FONT.head, color: C.white, bold: true, margin: 0,
    });
    s.addText("多源流式金融趋势与异常检测分析平台", {
      x: 0.8, y: 1.95, w: 8.4, h: 0.55,
      fontSize: 20, fontFace: FONT.body, color: C.grayLt, margin: 0,
    });
    s.addShape("rect", { x: 0.8, y: 2.7, w: 2, h: 0.03, fill: { color: C.accent } });
    s.addText("阶段汇报  —  2026年5月", {
      x: 0.8, y: 2.9, w: 5, h: 0.4,
      fontSize: 14, fontFace: FONT.body, color: C.accentLt, margin: 0,
    });
    s.addText("南洋理工大学 毕业设计", {
      x: 0.8, y: 3.4, w: 5, h: 0.35,
      fontSize: 12, fontFace: FONT.body, color: C.gray, margin: 0,
    });
  }

  // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  // SLIDE 2 — Problem Statement
  // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  {
    const s = pres.addSlide();
    darkBg(s);
    addSectionTag(s, "动机");
    addSlideTitle(s, "问题陈述");
    addPageNum(s, 2);

    const bullets = [
      ["金融市场持续产生高速数据流——价格、成交量、新闻情绪", icons.chart],
      ["异常事件（闪崩、拉高出货）若未及时检测，会造成严重损失", icons.warn],
      ["批处理分析存在危险的延迟——等分析出结果时，事件已经过去", icons.clock],
    ];
    bullets.forEach(([txt, ico], i) => {
      const yBase = 1.5 + i * 0.85;
      addCard(s, 0.5, yBase, 9, 0.72);
      s.addImage({ data: ico, x: 0.7, y: yBase + 0.15, w: 0.4, h: 0.4 });
      s.addText(txt, {
        x: 1.25, y: yBase + 0.05, w: 7.9, h: 0.62,
        fontSize: 13, fontFace: FONT.body, color: C.text, valign: "middle", margin: 0,
      });
    });

    // Research question
    addCard(s, 0.5, 4.15, 9, 0.95);
    s.addShape("rect", { x: 0.5, y: 4.15, w: 0.06, h: 0.95, fill: { color: C.accent } });
    s.addText("研究问题", {
      x: 0.8, y: 4.2, w: 3, h: 0.3,
      fontSize: 10, fontFace: FONT.body, color: C.accentLt, bold: true, margin: 0,
    });
    s.addText("异构流式集成检测器能否在实时环境下检测金融异常，并适应市场环境的变化？", {
      x: 0.8, y: 4.5, w: 8.4, h: 0.5,
      fontSize: 13, fontFace: FONT.body, color: C.white, italic: true, margin: 0,
    });
  }

  // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  // SLIDE 3 — System Architecture
  // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  {
    const s = pres.addSlide();
    darkBg(s);
    addSectionTag(s, "架构");
    addSlideTitle(s, "系统架构");
    addPageNum(s, 3);

    // Architecture image — 3262x1158 → aspect ~2.82:1
    const imgH = 2.2;
    const imgW = imgH * (3262 / 1158);
    const imgX = (10 - imgW) / 2;
    s.addImage({
      path: "/Users/ywx/Documents/NTU/capstone_project/docs/figures/Architecture.png",
      x: imgX, y: 1.35, w: imgW, h: imgH,
    });

    // Design rationale cards — 2x2 grid
    const rationale = [
      ["Kappa 优于 Lambda", "单一处理路径——无需维护双套代码"],
      ["Kafka KRaft", "无需 Zookeeper；持久化、可重放的事件日志"],
      ["Quix Streams", "Python 原生；与 ML 代码无跨语言边界"],
      ["TimescaleDB", "标准 SQL + JSON + 超表时序分区"],
    ];
    rationale.forEach(([title, desc], i) => {
      const col = i % 2;
      const row = Math.floor(i / 2);
      const cx = 0.5 + col * 4.6;
      const cy = 3.75 + row * 0.82;
      addCard(s, cx, cy, 4.4, 0.7);
      s.addShape("rect", { x: cx, y: cy, w: 0.05, h: 0.7, fill: { color: C.accent } });
      s.addText(title, {
        x: cx + 0.2, y: cy + 0.05, w: 4, h: 0.25,
        fontSize: 11, fontFace: FONT.body, color: C.accentLt, bold: true, margin: 0,
      });
      s.addText(desc, {
        x: cx + 0.2, y: cy + 0.32, w: 4, h: 0.3,
        fontSize: 10, fontFace: FONT.body, color: C.grayLt, margin: 0,
      });
    });
  }

  // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  // SLIDE 4 — Four-Detector Ensemble
  // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  {
    const s = pres.addSlide();
    darkBg(s);
    addSectionTag(s, "集成");
    addSlideTitle(s, "集成设计：互补检测");
    addPageNum(s, 4);

    const detectors = [
      { name: "EWMA", weight: "0.40", strength: "捕捉突然的单特征尖峰", adaptive: "Yes", color: C.accent, ico: icons.chart },
      { name: "半空间树", weight: "0.05", strength: "捕捉多变量交互异常", adaptive: "Yes", color: C.green, ico: icons.layers },
      { name: "孤立森林", weight: "0.45", strength: "从历史中发现全局离群点", adaptive: "No", color: C.accentLt, ico: icons.search },
      { name: "LSTM 自编码器", weight: "0.10", strength: "捕捉时间序列模式", adaptive: "No", color: "7DD3FC", ico: icons.brain },
    ];

    detectors.forEach((d, i) => {
      const cx = 0.35 + i * 2.4;
      addCard(s, cx, 1.45, 2.15, 2.8);
      // color bar top
      s.addShape("rect", { x: cx, y: 1.45, w: 2.1, h: 0.05, fill: { color: d.color } });
      s.addImage({ data: d.ico, x: cx + 0.75, y: 1.65, w: 0.55, h: 0.55 });
      s.addText(d.name, {
        x: cx + 0.1, y: 2.3, w: 1.9, h: 0.35,
        fontSize: 12, fontFace: FONT.body, color: C.white, bold: true, align: "center", margin: 0,
      });
      s.addText([
        { text: "Weight: ", options: { bold: true, color: C.grayLt } },
        { text: d.weight, options: { color: d.color, bold: true } },
      ], {
        x: cx + 0.1, y: 2.65, w: 1.9, h: 0.25,
        fontSize: 10, fontFace: FONT.body, align: "center", margin: 0,
      });
      s.addText(d.strength, {
        x: cx + 0.15, y: 2.95, w: 1.8, h: 0.55,
        fontSize: 9.5, fontFace: FONT.body, color: C.grayLt, align: "center", margin: 0,
      });
      s.addText(d.adaptive === "Yes" ? "自适应" : "批处理", {
        x: cx + 0.55, y: 3.6, w: 1.0, h: 0.22,
        fontSize: 8, fontFace: FONT.body,
        color: d.adaptive === "Yes" ? C.green : C.gold,
        align: "center", valign: "middle", margin: 0,
      });
    });

    // Bottom insight
    addCard(s, 0.5, 4.55, 9, 0.65);
    s.addShape("rect", { x: 0.5, y: 4.55, w: 0.05, h: 0.65, fill: { color: C.accent } });
    s.addText("没有任何单一检测器能覆盖所有异常类型。分数归一化至 [-1, 0]；阈值 = -0.28", {
      x: 0.75, y: 4.55, w: 8.5, h: 0.65,
      fontSize: 11, fontFace: FONT.body, color: C.text, valign: "middle", margin: 0,
    });
  }

  // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  // SLIDE 5 — Score Normalization Challenge
  // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  {
    const s = pres.addSlide();
    darkBg(s);
    addSectionTag(s, "挑战");
    addSlideTitle(s, "关键挑战：分数不兼容");
    addPageNum(s, 5);

    // Left: raw score ranges
    addCard(s, 0.5, 1.4, 4.3, 2.5);
    s.addText("归一化前", {
      x: 0.7, y: 1.5, w: 3.5, h: 0.3,
      fontSize: 12, fontFace: FONT.body, color: C.red, bold: true, margin: 0,
    });
    const rawScores = [
      ["EWMA", "[-40, 0]", "无界 z-score"],
      ["LSTM", "[-100, 0]", "原始 MSE"],
      ["孤立森林", "[+0.1, +0.2]", "决策函数"],
      ["HST", "[-0.3, 0]", "树分数"],
    ];
    rawScores.forEach(([name, range, note], i) => {
      const yy = 1.9 + i * 0.45;
      s.addText(name, {
        x: 0.7, y: yy, w: 1.6, h: 0.25,
        fontSize: 10, fontFace: FONT.body, color: C.white, bold: true, margin: 0,
      });
      s.addText(range, {
        x: 2.3, y: yy, w: 1.0, h: 0.25,
        fontSize: 10, fontFace: "Consolas", color: C.gold, margin: 0,
      });
      s.addText(note, {
        x: 3.3, y: yy, w: 1.3, h: 0.25,
        fontSize: 9, fontFace: FONT.body, color: C.muted, margin: 0,
      });
    });

    // Right: result
    addCard(s, 5.0, 1.4, 4.5, 2.5);
    s.addText("结果", {
      x: 5.2, y: 1.5, w: 3, h: 0.3,
      fontSize: 12, fontFace: FONT.body, color: C.red, bold: true, margin: 0,
    });
    s.addText("62%", {
      x: 5.2, y: 1.85, w: 2.0, h: 0.6,
      fontSize: 40, fontFace: FONT.head, color: C.red, bold: true, align: "center", margin: 0,
    });
    s.addText("误报率", {
      x: 5.2, y: 2.45, w: 2.0, h: 0.25,
      fontSize: 10, fontFace: FONT.body, color: C.grayLt, align: "center", margin: 0,
    });
    s.addText("8.35%", {
      x: 7.3, y: 1.85, w: 2.0, h: 0.6,
      fontSize: 40, fontFace: FONT.head, color: C.gold, bold: true, align: "center", margin: 0,
    });
    s.addText("精确率", {
      x: 7.3, y: 2.45, w: 2.0, h: 0.25,
      fontSize: 10, fontFace: FONT.body, color: C.grayLt, align: "center", margin: 0,
    });
    s.addText("EWMA 的无界 z-score 主导了集成加权平均", {
      x: 5.2, y: 3.05, w: 4.1, h: 0.5,
      fontSize: 10, fontFace: FONT.body, color: C.text, margin: 0,
    });

    // Bottom: solution
    addCard(s, 0.5, 4.15, 9, 1.0);
    s.addShape("rect", { x: 0.5, y: 4.15, w: 0.05, h: 1.0, fill: { color: C.green } });
    s.addText("解决方案", {
      x: 0.75, y: 4.2, w: 2, h: 0.25,
      fontSize: 11, fontFace: FONT.body, color: C.green, bold: true, margin: 0,
    });
    s.addText("将所有检测器归一化至 [-1, 0] 范围。根据单独性能重新分配权重。集成学习文献 (Zimek et al. 2014) 警告过分数不兼容问题，但未提供领域特定的解决方案——需要经验性诊断。", {
      x: 0.75, y: 4.5, w: 8.5, h: 0.55,
      fontSize: 10, fontFace: FONT.body, color: C.text, margin: 0,
    });
  }

  // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  // SLIDE 6 — Backtest Results Before vs After
  // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  {
    const s = pres.addSlide();
    darkBg(s);
    addSectionTag(s, "结果");
    addSlideTitle(s, "回测结果：优化前后对比");
    addPageNum(s, 6);

    // Metrics comparison — big stat callouts
    const metrics = [
      { label: "精确率", before: "8.35%", after: "46.38%", gain: "5.5×", color: C.accent },
      { label: "F1 分数", before: "0.154", after: "0.561", gain: "3.6×", color: C.green },
      { label: "误报率", before: "62.0%", after: "4.64%", gain: "13.4× ↓", color: C.accentLt },
      { label: "Cohen's d", before: "0.51", after: "1.78", gain: "3.5×", color: "7DD3FC" },
    ];
    metrics.forEach((m, i) => {
      const cx = 0.35 + i * 2.4;
      addCard(s, cx, 1.4, 2.2, 2.0);
      s.addShape("rect", { x: cx, y: 1.4, w: 2.2, h: 0.04, fill: { color: m.color } });
      s.addText(m.label, {
        x: cx + 0.05, y: 1.55, w: 2.1, h: 0.25,
        fontSize: 10, fontFace: FONT.body, color: C.grayLt, align: "center", margin: 0,
      });
      s.addText(`${m.before}  →  ${m.after}`, {
        x: cx + 0.05, y: 1.85, w: 2.1, h: 0.4,
        fontSize: 16, fontFace: FONT.head, color: C.white, align: "center", margin: 0,
      });
      s.addText(m.gain, {
        x: cx + 0.05, y: 2.35, w: 2.1, h: 0.35,
        fontSize: 16, fontFace: FONT.body, color: m.color, bold: true, align: "center", margin: 0,
      });
      s.addText(i === 2 ? "降低" : "提升", {
        x: cx + 0.05, y: 2.7, w: 2.1, h: 0.2,
        fontSize: 8, fontFace: FONT.body, color: C.muted, align: "center", margin: 0,
      });
    });

    // Per-type recall bar
    addCard(s, 0.5, 3.6, 9, 1.55);
    s.addText("按异常类型的召回率", {
      x: 0.7, y: 3.7, w: 4, h: 0.25,
      fontSize: 11, fontFace: FONT.body, color: C.accentLt, bold: true, margin: 0,
    });
    const types = [
      ["情绪崩溃", 1.0],
      ["成交量激增", 0.7963],
      ["多特征异常", 0.6757],
      ["价格尖峰", 0.5493],
      ["微妙漂移", 0.3333],
    ];
    types.forEach(([name, val], i) => {
      const yy = 4.05 + i * 0.2;
      s.addText(name, {
        x: 0.7, y: yy, w: 1.6, h: 0.18,
        fontSize: 8.5, fontFace: FONT.body, color: C.grayLt, margin: 0,
      });
      // bar bg
      s.addShape("rect", { x: 2.4, y: yy + 0.02, w: 6.5, h: 0.14, fill: { color: C.slate } });
      // bar fill
      const barColor = val >= 0.7 ? C.green : val >= 0.5 ? C.accent : C.red;
      s.addShape("rect", { x: 2.4, y: yy + 0.02, w: 6.5 * val, h: 0.14, fill: { color: barColor } });
      s.addText(`${(val * 100).toFixed(0)}%`, {
        x: 2.4 + 6.5 * val + 0.1, y: yy - 0.01, w: 0.5, h: 0.18,
        fontSize: 8, fontFace: FONT.body, color: C.white, bold: true, margin: 0,
      });
    });
  }

  // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  // SLIDE 7 — Per-Detector Analysis
  // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  {
    const s = pres.addSlide();
    darkBg(s);
    addSectionTag(s, "分析");
    addSlideTitle(s, "为何集成 > 任何单一检测器");
    addPageNum(s, 7);

    // Table
    const headerRow = [
      { text: "检测器", options: { bold: true, color: C.white, fill: { color: C.slate }, fontSize: 10, fontFace: FONT.body } },
      { text: "精确率", options: { bold: true, color: C.white, fill: { color: C.slate }, fontSize: 10, fontFace: FONT.body } },
      { text: "召回率", options: { bold: true, color: C.white, fill: { color: C.slate }, fontSize: 10, fontFace: FONT.body } },
      { text: "F1", options: { bold: true, color: C.white, fill: { color: C.slate }, fontSize: 10, fontFace: FONT.body } },
      { text: "检测数", options: { bold: true, color: C.white, fill: { color: C.slate }, fontSize: 10, fontFace: FONT.body } },
    ];
    const cellOpts = (highlight) => ({
      fontSize: 10, fontFace: FONT.body,
      color: highlight ? C.white : C.grayLt,
      fill: { color: highlight ? C.accent : C.cardBg },
      bold: highlight,
    });
    const rows = [
      ["EWMA", "23.1%", "82.7%", "0.36", "804"],
      ["半空间树", "4.2%", "30.7%", "0.07", "1,650"],
      ["孤立森林", "49.3%", "47.1%", "0.48", "215"],
      ["LSTM", "5.6%", "36.4%", "0.10", "1,469"],
      ["集成", "46.4%", "71.1%", "0.56", "345"],
    ];
    const tableData = [headerRow];
    rows.forEach((row, ri) => {
      const isEnsemble = ri === 4;
      tableData.push(row.map(t => ({ text: t, options: cellOpts(isEnsemble) })));
    });
    s.addTable(tableData, {
      x: 0.5, y: 1.4, w: 9, colW: [2.2, 1.5, 1.5, 1.3, 1.5],
      border: { pt: 0.5, color: C.cardBdr },
      rowH: [0.35, 0.32, 0.32, 0.32, 0.32, 0.38],
    });

    // Insight cards below
    const insights = [
      { label: "EWMA", desc: "高召回率哨兵——能抓到大多数事件，但误报多", color: C.accent, ico: icons.chart },
      { label: "孤立森林", desc: "高精确率确认者——保守，验证明确的离群值", color: C.accentLt, ico: icons.search },
      { label: "集成", desc: "精确率优于任何单一检测器 + 召回率高于孤立森林", color: C.green, ico: icons.handshake },
    ];
    insights.forEach((ins, i) => {
      const cx = 0.5 + i * 3.1;
      addCard(s, cx, 3.85, 2.9, 1.2);
      s.addImage({ data: ins.ico, x: cx + 0.15, y: 3.95, w: 0.35, h: 0.35 });
      s.addText(ins.label, {
        x: cx + 0.6, y: 3.95, w: 2.1, h: 0.3,
        fontSize: 11, fontFace: FONT.body, color: ins.color, bold: true, margin: 0,
      });
      s.addText(ins.desc, {
        x: cx + 0.15, y: 4.35, w: 2.6, h: 0.55,
        fontSize: 9, fontFace: FONT.body, color: C.grayLt, margin: 0,
      });
    });
  }

  // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  // SLIDE 8 — Concept Drift
  // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  {
    const s = pres.addSlide();
    darkBg(s);
    addSectionTag(s, "MLOps");
    addSlideTitle(s, "适应非平稳市场");
    addPageNum(s, 8);

    // Drift stats
    const stats = [
      { val: "37", label: "检测到的\n漂移事件", color: C.accentLt },
      { val: "88", label: "窗口延迟\n（成交量）", color: C.accentLt },
      { val: "182", label: "窗口延迟\n（情绪）", color: C.accent },
    ];
    stats.forEach((st, i) => {
      const cx = 0.5 + i * 2.0;
      addCard(s, cx, 1.4, 1.8, 1.1);
      s.addText(st.val, {
        x: cx + 0.1, y: 1.45, w: 1.6, h: 0.5,
        fontSize: 32, fontFace: FONT.head, color: st.color, bold: true, align: "center", margin: 0,
      });
      s.addText(st.label, {
        x: cx + 0.1, y: 1.95, w: 1.6, h: 0.45,
        fontSize: 8.5, fontFace: FONT.body, color: C.grayLt, align: "center", margin: 0,
      });
    });

    // Layered adaptation - right side
    addCard(s, 6.3, 1.4, 3.2, 1.1);
    s.addText("四层自适应策略", {
      x: 6.45, y: 1.45, w: 3, h: 0.25,
      fontSize: 10, fontFace: FONT.body, color: C.green, bold: true, margin: 0,
    });
    const layers = [
      ["即时", "EWMA 指数衰减"],
      ["短期", "HST 滑动窗口"],
      ["中期", "ADWIN 统计检验"],
      ["长期", "孤立森林重训 + 版本管理"],
    ];
    layers.forEach(([t, d], i) => {
      const yy = 1.72 + i * 0.18;
      s.addText([
        { text: `${t}: `, options: { bold: true, color: C.accentLt, fontSize: 8 } },
        { text: d, options: { color: C.grayLt, fontSize: 8 } },
      ], { x: 6.45, y: yy, w: 3, h: 0.16, fontFace: FONT.body, margin: 0 });
    });

    // Dashboard screenshot — model health
    s.addImage({
      path: "/Users/ywx/Documents/NTU/capstone_project/Figure/dashboard_model_health.png",
      x: 0.5, y: 2.75, w: 9, h: 2.55,
      sizing: { type: "contain", w: 9, h: 2.55 },
    });
  }

  // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  // SLIDE 9 — Human vs AI: Where Humans Excel
  // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  {
    const s = pres.addSlide();
    darkBg(s);
    addSectionTag(s, "人 vs AI");
    addSlideTitle(s, "人类的优势", { fontSize: 26 });
    addPageNum(s, 9);

    const items = [
      {
        title: "上下文解读",
        desc: "AI 标记「分数 = -0.45」；人类知道 TSLA 下跌是因为 CEO 推文还是财报不及预期——不同原因需要不同应对",
        ico: icons.brain,
        color: C.accentLt,
      },
      {
        title: "误报裁决",
        desc: "精确率 46%，超过一半的警报是误报。人类立即能识别「这是正常的季末调仓」",
        ico: icons.eye,
        color: C.accent,
      },
      {
        title: "真值定义",
        desc: "「异常」取决于角色——风控经理（尾部事件）、合规官（可疑模式）、交易员（机会）",
        ico: icons.balance,
        color: C.green,
      },
      {
        title: "特征与分类体系设计",
        desc: "选择 sentiment_shift 作为特征，需要领域知识理解新闻如何随时间影响市场",
        ico: icons.cogs,
        color: "7DD3FC",
      },
      {
        title: "因果推理",
        desc: "AI 检测统计相关性；人类理解因果机制和市场微观结构",
        ico: icons.user,
        color: C.accentLt,
      },
    ];

    items.forEach((item, i) => {
      const yy = 1.3 + i * 0.84;
      addCard(s, 0.5, yy, 9, 0.72);
      s.addShape("rect", { x: 0.5, y: yy, w: 0.05, h: 0.72, fill: { color: item.color } });
      s.addImage({ data: item.ico, x: 0.7, y: yy + 0.16, w: 0.38, h: 0.38 });
      s.addText(item.title, {
        x: 1.25, y: yy + 0.06, w: 3, h: 0.25,
        fontSize: 12, fontFace: FONT.body, color: item.color, bold: true, margin: 0,
      });
      s.addText(item.desc, {
        x: 1.25, y: yy + 0.34, w: 8, h: 0.32,
        fontSize: 9.5, fontFace: FONT.body, color: C.text, margin: 0,
      });
    });
  }

  // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  // SLIDE 10 — Human vs AI: Where AI Adds Value
  // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  {
    const s = pres.addSlide();
    darkBg(s);
    addSectionTag(s, "人 vs AI");
    addSlideTitle(s, "AI 的价值", { fontSize: 26 });
    addPageNum(s, 10);

    const items = [
      {
        title: "持续关注",
        desc: "7×24 监控 3 只股票，每小时每只 12 个特征窗口。人的注意力会衰退，系统不会。",
        ico: icons.clock, color: C.accent,
      },
      {
        title: "多维模式识别",
        desc: "同时考虑价格 + 成交量 + 情绪 + 交叉特征交互，人类只能依次处理。",
        ico: icons.layers, color: C.green,
      },
      {
        title: "客观性",
        desc: "对每个数据点应用相同评分标准。没有锚定偏差、近因效应或疲劳。",
        ico: icons.shield, color: C.accentLt,
      },
      {
        title: "适应速度",
        desc: "EWMA 和 HST 在窗口参数内适应新的市场环境，比人类更新心智模型更快。",
        ico: icons.bolt, color: "7DD3FC",
      },
    ];

    items.forEach((item, i) => {
      const cx = i < 2 ? 0.5 : 5.0;
      const cy = i % 2 === 0 ? 1.4 : 2.75;
      addCard(s, cx, cy, 4.3, 1.15);
      s.addImage({ data: item.ico, x: cx + 0.2, y: cy + 0.15, w: 0.45, h: 0.45 });
      s.addText(item.title, {
        x: cx + 0.8, y: cy + 0.1, w: 3.2, h: 0.3,
        fontSize: 13, fontFace: FONT.body, color: item.color, bold: true, margin: 0,
      });
      s.addText(item.desc, {
        x: cx + 0.8, y: cy + 0.43, w: 3.3, h: 0.6,
        fontSize: 9.5, fontFace: FONT.body, color: C.text, margin: 0,
      });
    });

    // Key message banner
    addCard(s, 0.5, 4.2, 9, 0.95);
    s.addShape("rect", { x: 0.5, y: 4.2, w: 9, h: 0.05, fill: { color: C.green } });
    s.addImage({ data: icons.handshake, x: 1.0, y: 4.4, w: 0.5, h: 0.5 });
    s.addText("人 + AI  >  仅人  >  仅 AI", {
      x: 1.7, y: 4.35, w: 6, h: 0.4,
      fontSize: 20, fontFace: FONT.head, color: C.green, bold: true, margin: 0,
    });
    s.addText("系统是增强工具，不是自主代理", {
      x: 1.7, y: 4.75, w: 6, h: 0.25,
      fontSize: 10, fontFace: FONT.body, color: C.grayLt, margin: 0,
    });
  }

  // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  // SLIDE 11 — Dashboard / Human-in-the-Loop
  // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  {
    const s = pres.addSlide();
    darkBg(s);
    addSectionTag(s, "仪表盘");
    addSlideTitle(s, "为人类解读而设计");
    addPageNum(s, 11);

    // Two screenshots side by side
    // dashboard_home: 1352x630 → aspect 2.146:1
    // dashboard_anomaly_alerts: 1352x630 → aspect 2.146:1
    const dH = 1.8;
    const dW = dH * (1352 / 630);
    s.addImage({
      path: "/Users/ywx/Documents/NTU/capstone_project/Figure/dashboard_home.png",
      x: 0.3, y: 1.4, w: dW, h: dH,
      shadow: cardShadow(),
    });
    s.addImage({
      path: "/Users/ywx/Documents/NTU/capstone_project/Figure/dashboard_anomaly_alerts.png",
      x: 5.1, y: 1.4, w: dW, h: dH,
      shadow: cardShadow(),
    });

    // Design choices
    const choices = [
      ["逐检测器分数分解", "查看哪些检测器一致（强信号）还是不一致（不确定）"],
      ["人类可读的异常原因", "「价格变动 3.12%，情绪偏移 -0.41」"],
      ["漂移事件时间线", "实时识别市场环境变化"],
      ["5-10秒自动刷新", "无需手动轮询的实时监控"],
    ];
    choices.forEach(([title, desc], i) => {
      const cx = i < 2 ? 0.5 : 5.0;
      const cy = i % 2 === 0 ? 3.5 : 4.25;
      s.addShape("rect", { x: cx, y: cy + 0.05, w: 0.05, h: 0.5, fill: { color: C.accent } });
      s.addText(title, {
        x: cx + 0.2, y: cy, w: 4.2, h: 0.25,
        fontSize: 10, fontFace: FONT.body, color: C.accentLt, bold: true, margin: 0,
      });
      s.addText(desc, {
        x: cx + 0.2, y: cy + 0.25, w: 4.2, h: 0.35,
        fontSize: 9, fontFace: FONT.body, color: C.grayLt, margin: 0,
      });
    });
  }

  // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  // SLIDE 12 — Honest Limitations
  // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  {
    const s = pres.addSlide();
    darkBg(s);
    addSectionTag(s, "局限性");
    addSlideTitle(s, "当前局限性");
    addPageNum(s, 12);

    const limits = [
      {
        title: "仅合成数据验证",
        desc: "所有评估使用注入的异常，未对真实历史事件（财报、闪崩）进行测试",
      },
      {
        title: "单独检测器较弱",
        desc: "HST（4.2% 精确率）和 LSTM（5.6% 精确率）——其集成贡献尚未通过消融实验正式量化",
      },
      {
        title: "微妙漂移检测不足",
        desc: "渐进分布变化的召回率仅 33%——系统错过大部分缓慢变化",
      },
      {
        title: "合成情绪数据",
        desc: "回测情绪使用随机正态分布，非真实历史标题——NLP 价值未得到证明",
      },
      {
        title: "无延迟基准",
        desc: "「实时」声明尚未通过端到端计时测量进行量化验证",
      },
    ];
    limits.forEach((lim, i) => {
      const yy = 1.35 + i * 0.8;
      addCard(s, 0.5, yy, 9, 0.68);
      s.addShape("rect", { x: 0.5, y: yy, w: 0.05, h: 0.68, fill: { color: C.accentLt } });
      s.addText(`${i + 1}`, {
        x: 0.7, y: yy + 0.1, w: 0.35, h: 0.35,
        fontSize: 16, fontFace: FONT.head, color: C.accentLt, bold: true, align: "center", valign: "middle", margin: 0,
      });
      s.addText(lim.title, {
        x: 1.2, y: yy + 0.05, w: 8, h: 0.25,
        fontSize: 12, fontFace: FONT.body, color: C.white, bold: true, margin: 0,
      });
      s.addText(lim.desc, {
        x: 1.2, y: yy + 0.32, w: 8, h: 0.3,
        fontSize: 10, fontFace: FONT.body, color: C.grayLt, margin: 0,
      });
    });
  }

  // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  // SLIDE 13 — Pathway Phase 3
  // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  {
    const s = pres.addSlide();
    darkBg(s);
    addSectionTag(s, "路线图");
    addSlideTitle(s, "下一步（六至七月）", { fontSize: 26 });
    addPageNum(s, 13);

    const tasks = [
      { task: "历史事件验证", deliver: "对 TSLA 财报、NVDA 暴涨、2025年3月回调进行测试", why: "真实世界证据", ico: icons.search },
      { task: "消融实验", deliver: "15 种检测器组合（4+6+4+1）", why: "证明复杂度的必要性", ico: icons.cogs },
      { task: "情绪影响分析", deliver: "对比有/无 FinBERT 特征的检测效果", why: "量化 NLP 价值", ico: icons.brain },
      { task: "阈值敏感性", deliver: "精确率-召回率曲线 [-0.15 至 -0.50]", why: "优化权衡", ico: icons.chart },
      { task: "延迟基准测试", deliver: "端到端计时：数据到达 → 仪表盘警报", why: "证明实时性", ico: icons.clock },
      { task: "漂移恢复测试", deliver: "模型重训前后的检测性能对比", why: "验证 MLOps", ico: icons.sync },
    ];
    tasks.forEach((t, i) => {
      const col = i % 2;
      const row = Math.floor(i / 2);
      const cx = 0.5 + col * 4.6;
      const cy = 1.4 + row * 1.3;
      addCard(s, cx, cy, 4.4, 1.1);
      s.addImage({ data: t.ico, x: cx + 0.15, y: cy + 0.15, w: 0.35, h: 0.35 });
      s.addText(t.task, {
        x: cx + 0.6, y: cy + 0.1, w: 3.5, h: 0.25,
        fontSize: 11, fontFace: FONT.body, color: C.white, bold: true, margin: 0,
      });
      s.addText(t.deliver, {
        x: cx + 0.6, y: cy + 0.4, w: 3.6, h: 0.35,
        fontSize: 9, fontFace: FONT.body, color: C.grayLt, margin: 0,
      });
      s.addText(t.why, {
        x: cx + 0.6, y: cy + 0.78, w: 3.5, h: 0.2,
        fontSize: 9, fontFace: FONT.body, color: C.accent, italic: true, margin: 0,
      });
    });
  }

  // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  // SLIDE 14 — Timeline
  // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  {
    const s = pres.addSlide();
    darkBg(s);
    addSectionTag(s, "路线图");
    addSlideTitle(s, "完成路线图");
    addPageNum(s, 14);

    // Timeline bar
    const tlY = 1.8;
    const tlX = 0.8;
    const tlW = 8.4;
    s.addShape("rect", { x: tlX, y: tlY + 0.28, w: tlW, h: 0.06, fill: { color: C.slate } });

    const phases = [
      { label: "第一阶段\n基础设施", period: "1–3月", pct: 0, status: "done", w: 0.25 },
      { label: "第二阶段\n集成检测", period: "4–5月", pct: 0.3, status: "done", w: 0.25 },
      { label: "第三阶段\n评估验证", period: "6–7月", pct: 0.55, status: "current", w: 0.25 },
      { label: "第四阶段\n论文撰写", period: "8–9月", pct: 0.78, status: "future", w: 0.22 },
      { label: "截止日期", period: "2026年11月", pct: 1.0, status: "deadline", w: 0 },
    ];
    phases.forEach(p => {
      const px = tlX + tlW * p.pct;
      let dotColor, dotR;
      if (p.status === "done") { dotColor = C.green; dotR = 0.15; }
      else if (p.status === "current") { dotColor = C.gold; dotR = 0.18; }
      else if (p.status === "deadline") { dotColor = C.red; dotR = 0.13; }
      else { dotColor = C.grayDk; dotR = 0.13; }

      s.addShape("oval", {
        x: px - dotR, y: tlY + 0.31 - dotR, w: dotR * 2, h: dotR * 2,
        fill: { color: dotColor },
      });
      if (p.status === "done") {
        // fill the bar segment up to this point with green
      }
      s.addText(p.label, {
        x: px - 0.6, y: tlY - 0.65, w: 1.2, h: 0.6,
        fontSize: 9, fontFace: FONT.body, color: p.status === "current" ? C.gold : C.grayLt,
        bold: p.status === "current", align: "center", margin: 0,
      });
      s.addText(p.period, {
        x: px - 0.5, y: tlY + 0.6, w: 1.0, h: 0.25,
        fontSize: 8, fontFace: FONT.body, color: C.muted, align: "center", margin: 0,
      });
    });

    // Fill completed portion
    s.addShape("rect", { x: tlX, y: tlY + 0.26, w: tlW * 0.45, h: 0.1, fill: { color: C.green } });
    // Current segment
    s.addShape("rect", { x: tlX + tlW * 0.45, y: tlY + 0.26, w: tlW * 0.1, h: 0.1, fill: { color: C.gold } });

    // "WE ARE HERE" arrow
    const arrowX = tlX + tlW * 0.55;
    s.addText("▲ 当前位置", {
      x: arrowX - 0.6, y: tlY + 0.9, w: 1.2, h: 0.25,
      fontSize: 8, fontFace: FONT.body, color: C.gold, bold: true, align: "center", margin: 0,
    });

    // Already complete checklist
    addCard(s, 0.5, 3.0, 4.3, 2.1);
    s.addText("已完成", {
      x: 0.7, y: 3.1, w: 3, h: 0.25,
      fontSize: 12, fontFace: FONT.body, color: C.green, bold: true, margin: 0,
    });
    const done = [
      "流式管道（Kafka + Quix）",
      "4 检测器集成 + 加权投票",
      "FinBERT 情绪集成",
      "ADWIN 漂移检测 + 重训",
      "6 页 Streamlit 仪表盘",
      "62 个单元测试（全部通过）",
      "文献综述（40+ 篇参考文献）",
    ];
    done.forEach((item, i) => {
      s.addText([
        { text: "✓  ", options: { color: C.green, bold: true } },
        { text: item, options: { color: C.grayLt } },
      ], {
        x: 0.7, y: 3.4 + i * 0.22, w: 3.8, h: 0.2,
        fontSize: 9, fontFace: FONT.body, margin: 0,
      });
    });

    // Remaining
    addCard(s, 5.2, 3.0, 4.3, 2.1);
    s.addText("待完成", {
      x: 5.4, y: 3.1, w: 3, h: 0.25,
      fontSize: 12, fontFace: FONT.body, color: C.gold, bold: true, margin: 0,
    });
    const todo = [
      "历史事件验证",
      "消融实验（15 种组合）",
      "情绪影响分析",
      "阈值敏感性曲线",
      "端到端延迟基准",
      "毕业论文 + 答辩",
      "现场演示优化",
    ];
    todo.forEach((item, i) => {
      s.addText([
        { text: "○  ", options: { color: C.gold } },
        { text: item, options: { color: C.grayLt } },
      ], {
        x: 5.4, y: 3.4 + i * 0.22, w: 3.8, h: 0.2,
        fontSize: 9, fontFace: FONT.body, margin: 0,
      });
    });
  }

  // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  // SLIDE 15 — Summary & Questions
  // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  {
    const s = pres.addSlide();
    s.background = { color: C.deepNavy };
    s.addShape("rect", { x: 0, y: 0, w: 10, h: 0.06, fill: { color: C.accent } });
    s.addShape("rect", { x: 0, y: 5.565, w: 10, h: 0.06, fill: { color: C.accent } });

    s.addText("总结", {
      x: 0.8, y: 0.6, w: 8.4, h: 0.6,
      fontSize: 36, fontFace: FONT.head, color: C.white, bold: true, margin: 0,
    });

    const summaryItems = [
      { text: "可运行的流式集成系统，具有量化结果", metric: "F1 = 0.56，误报率 = 4.6%", color: C.green },
      { text: "研究贡献：流式环境中异构检测器的集成方法", metric: "4 检测器 + 漂移自适应", color: C.accent },
      { text: "人机互补：通过仪表盘设计实现", metric: "增强工具，非自主替代", color: "7DD3FC" },
      { text: "明确的路线图与具体交付物", metric: "距提交还有 4 个月", color: C.accentLt },
    ];
    summaryItems.forEach((item, i) => {
      const yy = 1.5 + i * 0.85;
      addCard(s, 0.8, yy, 8.4, 0.72);
      s.addShape("rect", { x: 0.8, y: yy, w: 0.05, h: 0.72, fill: { color: item.color } });
      s.addText(item.text, {
        x: 1.1, y: yy + 0.07, w: 7.8, h: 0.3,
        fontSize: 13, fontFace: FONT.body, color: C.white, bold: true, margin: 0,
      });
      s.addText(item.metric, {
        x: 1.1, y: yy + 0.38, w: 7.8, h: 0.25,
        fontSize: 11, fontFace: FONT.body, color: item.color, margin: 0,
      });
    });

    s.addText("谢谢  /  提问环节", {
      x: 0.8, y: 4.8, w: 8.4, h: 0.5,
      fontSize: 22, fontFace: FONT.head, color: C.grayLt, align: "center", margin: 0,
    });
  }

  // ── Write file ──
  await pres.writeFile({ fileName: "/Users/ywx/Documents/NTU/capstone_project/docs/presentation.pptx" });
  console.log("✅ Presentation saved to docs/presentation.pptx");
}

main().catch(e => { console.error(e); process.exit(1); });

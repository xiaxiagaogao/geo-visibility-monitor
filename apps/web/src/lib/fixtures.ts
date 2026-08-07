/**
 * 固定数据 —— 这一轮只搭框架与风格，还没接 API。
 *
 * ⚠️ 这里**不是编的**：全部是 2026-08-02 安踏监测集的真实数字（docs/27 §6），
 *    35 条 answer_status=ok 样本，逐格与 v2 设计稿核对过。
 *    接 API 时整份文件删掉，`lib/api/*` 返回同样的类型即可，组件不用改。
 *
 * 自洽校验（见 fixtures.test.ts）：
 *   Σ 每行样本数 = 35；安踏逐行命中求和 = 21；八个品牌命中求和 = 137
 */
import type { Brand, PlatformOption, Prompt, RawResponse } from './types'

export const OWN_BRAND_ID = 34

/** 顶栏「更新于」用。接 API 后取最新一条 response 的 created_at */
export const LAST_COLLECTED_AT = '08-02 10:41'

export const BRANDS: Brand[] = [
  {
    id: 34,
    workspace_id: 1,
    name: '安踏',
    name_en: 'ANTA',
    industry: '运动鞋服',
    aliases: ['安踏', 'ANTA', 'anta'],
    // 列顺序的唯一依据 —— 与 v2 稿矩阵列序一致
    competitor_ids: [35, 36, 37, 38, 39, 40, 41],
    created_at: '2026-08-01T00:00:00Z',
  },
]

export const BRAND_NAMES: Record<number, string> = {
  34: '安踏',
  35: '李宁',
  36: '耐克',
  37: '阿迪达斯',
  38: '特步',
  39: '361度',
  40: '鸿星尔克',
  41: '亚瑟士',
}

/** docs/23 §2：无数据的平台必须灰显「未接入」，不能给假选项 */
export const PLATFORMS: PlatformOption[] = [
  { id: 'deepseek', label: 'DeepSeek', connected: true },
  { id: 'doubao', label: '豆包', connected: false },
  { id: 'kimi', label: 'Kimi', connected: false },
  { id: 'tongyi', label: '千问', connected: false },
]

export const PROMPTS: Prompt[] = [
  { id: 101, text: '国产运动鞋品牌有哪些值得买的？', category: 'unprompted' },
  { id: 102, text: '500元左右的运动鞋推荐', category: 'unprompted' },
  { id: 103, text: '学生党性价比高的运动鞋', category: 'unprompted' },
  { id: 104, text: '打篮球穿什么牌子的鞋？', category: 'scenario' },
  { id: 105, text: '运动鞋品牌排行榜前十', category: 'unprompted' },
  { id: 106, text: '适合跑步新手的鞋怎么选？', category: 'scenario' },
  { id: 107, text: '大体重跑者穿什么跑鞋？', category: 'scenario' },
  { id: 108, text: '马拉松比赛穿什么跑鞋？', category: 'scenario' },
  { id: 109, text: '2026年跑步鞋哪个品牌好？', category: 'unprompted' },
  { id: 110, text: '健身房训练穿什么鞋合适？', category: 'scenario' },
].map((p) => ({
  ...p,
  brand_id: OWN_BRAND_ID,
  tags: [],
  is_active: true,
  created_at: '2026-08-02T00:00:00Z',
}))

/** 矩阵一格：某提问下某品牌的命中数。`null` = 该品牌在这条提问里一次都没出现 */
export interface MatrixCell {
  brandId: number
  m: number | null
}

export interface MatrixRow {
  promptId: number
  /** 该提问的有效样本数，即这一行所有格子的公共分母 */
  n: number
  cells: MatrixCell[]
}

const COLUMN_ORDER = [34, 35, 36, 37, 38, 39, 40, 41]

function row(promptId: number, n: number, ms: (number | null)[]): MatrixRow {
  return {
    promptId,
    n,
    cells: COLUMN_ORDER.map((brandId, i) => ({ brandId, m: ms[i] })),
  }
}

/**
 * 提问 × 品牌命中矩阵（真实数据）。
 * 列序：安踏 李宁 耐克 阿迪达斯 特步 361度 鸿星尔克 亚瑟士
 */
export const MATRIX: MatrixRow[] = [
  row(101, 5, [5, 5, null, null, 5, 5, 5, null]),
  row(102, 4, [4, 4, null, 3, null, null, null, 4]),
  row(103, 3, [3, 3, 1, null, 3, 3, null, null]),
  row(104, 3, [3, 3, 3, 3, null, 3, null, 1]),
  row(105, 3, [3, 3, 3, 3, 2, 2, null, 3]),
  row(106, 3, [1, 1, 3, 2, 1, 1, null, 3]),
  row(107, 3, [1, 1, null, null, null, 3, null, 3]),
  row(108, 3, [1, null, 3, 3, null, null, null, 3]),
  row(109, 5, [0, null, 5, 5, null, null, null, 5]),
  row(110, 3, [0, null, 3, 1, null, null, null, null]),
]

export const MATRIX_COLUMNS = COLUMN_ORDER

/** 总览用的整体计数 */
export const TOTALS = {
  nValid: 35,
  nTotalResponses: 35,
  brand: { mMentioned: 21, mHead: 15 },
  /** 按 competitor_ids 顺序 */
  competitors: [
    { brandId: 35, mMentioned: 20 },
    { brandId: 36, mMentioned: 21 },
    { brandId: 37, mMentioned: 20 },
    { brandId: 38, mMentioned: 11 },
    { brandId: 39, mMentioned: 17 },
    { brandId: 40, mMentioned: 5 },
    { brandId: 41, mMentioned: 22 },
  ],
}

/**
 * 采集批次 —— 批次就是**一天**（docs/29 拍板 ⑦）。
 * 我们的 CrawlJob 是一条样本（35 条样本 = 35 个 job），没有「批次」这个实体，
 * 按 `group_by=day` 分组是零后端改动的做法。
 */
export interface Batch {
  date: string
  label: string
  note: string
  /** 该批是否还有明细可展开；false 表示 fixture 里只留了摘要 */
  expanded: boolean
  rows: { promptId: number; samples: number; status: 'success' | 'failed'; m: number }[]
}

export const BATCHES: Batch[] = [
  {
    date: '2026-08-02',
    label: '安踏监测集',
    note: '10 条提问 × 3–5 样本 = 35 条 · 全部成功',
    expanded: true,
    rows: MATRIX.map((r) => ({
      promptId: r.promptId,
      samples: r.n,
      status: 'success' as const,
      m: r.cells[0].m ?? 0,
    })),
  },
  {
    date: '2026-07-31',
    label: '装修行业监测集',
    note: '15 条样本 · 13 成功 2 无效 · 本品提及率 0.0% · 0/13 —— 零状态的真实用例',
    expanded: false,
    rows: [],
  },
]

/**
 * 证据模态的样例回答（v2 稿 2c 用的就是这条）。
 *
 * `mentions` 里**没有 offset** —— mentions 表根本没这两列（docs/28 §2.4），
 * 所以全文内联高亮这一轮做不了，留接口不留假实现。
 */
export const SAMPLE_RESPONSE: RawResponse = {
  id: 29,
  job_id: 129,
  platform: 'deepseek',
  prompt_text: '国产运动鞋品牌有哪些值得买的？',
  full_text: [
    '现在国产运动鞋的选择确实很丰富，不再只是"平替"，而是在各自的专业领域站稳了脚跟，甚至引领了技术方向。除了我们熟悉的安踏、李宁，特步、361° 等品牌也很有特色。',
    '',
    '我把几个主流品牌的核心特点整理了一下，方便你快速找到适合自己的那双……',
  ].join('\n'),
  html_path: null,
  screenshot_path: '/data/screenshots/resp_29.png',
  raw_json: { source: 'deepseek_web' },
  latency_ms: 18420,
  answer_status: 'ok',
  annotator_version: 'l1-v1',
  created_at: '2026-08-02T10:12:00Z',
  citations: [],
  /**
   * ⚠️ `position_rank` 全部为 null，不是偷懒 —— 这是**库里的真实状态**：
   * annotate.py 每写一条 mention 都硬编码 `position_rank=None`（列存在但从没算过）。
   * 填上 #1 #2 #3 就是在编数据，也会让「首位提及率」的降级态显得自相矛盾。
   * 后端按 offset 升序回填之后，这里换成真实序号，UI 自动从降级态恢复。
   *
   * `sentiment` 同理，annotate.py 也是写死 None，等后端接 LLM。
   */
  mentions: [
    { id: 1, brand_id: 34, mentioned: true, mention_type: 'body', position_bucket: 'head', position_rank: null, evidence_snippet: null },
    { id: 2, brand_id: 35, mentioned: true, mention_type: 'body', position_bucket: 'head', position_rank: null, evidence_snippet: null },
    { id: 3, brand_id: 38, mentioned: true, mention_type: 'body', position_bucket: 'head', position_rank: null, evidence_snippet: null },
    { id: 4, brand_id: 39, mentioned: true, mention_type: 'body', position_bucket: 'middle', position_rank: null, evidence_snippet: null },
    { id: 5, brand_id: 40, mentioned: true, mention_type: 'body', position_bucket: 'tail', position_rank: null, evidence_snippet: null },
  ],
}

export const PROMPT_BY_ID = new Map(PROMPTS.map((p) => [p.id, p]))

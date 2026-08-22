/**
 * L3 纯函数 —— 联网标注的三态（P2-37，口径见 `docs/API.md` §7 与 `PHASE2.md` §4.0.1）。
 *
 * 铁律同 `rates.ts` / `platforms.ts`：不碰 fetch、不碰 React。
 *
 * ## 为什么要单独一个模块
 *
 * `search_used` 是 `true | false | null`，而**这三个必须在界面上分得开**：
 *
 * - `true`  —— 这次联网了
 * - `false` —— **确认**没联网。§4.0.1 拍板：「无搜索输出是结果，不是废样本」，
 *              所以它是一条结论，**不是缺陷**，不能标红
 * - `null`  —— **我们不知道**：P2-37 上线之前的全部样本、别的平台、解析失败
 *
 * 把 `null` 并进 `false` 就是在界面上凭空断言一件我们没测过的事 ——
 * 而库里现在正躺着 55 条 `null` 的历史样本（run 296–299）等着被这样误读。
 * 这和证据页那条「不做 indexOf 兜底」是同一条纪律：**宁可显示降级，
 * 不可显示一个看起来正常的错误。**
 */
import type { BadgeTone } from '@/components/ui'

export interface SearchUsedLabel {
  text: string
  tone: BadgeTone
  /** 是不是降级态（= 我们不知道）。真值时界面该用 `Degraded` 而不是 `Badge` */
  degraded: boolean
  /** 鼠标悬停解释，避免用户把三态读成两态 */
  hint: string
}

export function searchUsedLabel(value: boolean | null | undefined): SearchUsedLabel {
  if (value === true) {
    return {
      text: '已联网',
      tone: 'ok',
      degraded: false,
      hint: '这次回答检索了网页来源（来源数与链接见下方「引用来源」）',
    }
  }
  if (value === false) {
    return {
      text: '未联网',
      // **刻意不用 danger。** 未联网是结果不是故障 —— 标红等于在界面上
      // 说这条样本有问题，而学术侧明确反对丢弃未联网样本（选择偏差）
      tone: 'neutral',
      degraded: false,
      hint: '这次回答没有检索网页，靠模型自身知识作答 —— 这是结果，不是废样本',
    }
  }
  return {
    text: '联网情况未记录',
    tone: 'neutral',
    degraded: true,
    hint: '这条样本采集时还没有联网标注（P2-37 之前），所以「有没有联网」是未知，不是「没有」',
  }
}

/** 「这条样本为什么没有引用」的四种答案。界面必须分得开。 */
export type CitationState =
  /** 有引用 */
  | 'has'
  /** 确认没联网 → 没引用是应然结果 */
  | 'none-no-search'
  /** 不知道有没有联网 → 降级，不是结论 */
  | 'unknown'
  /** **联网了却一条都没抽到 → 这是异常**，多半是流解析坏了或平台改了结构 */
  | 'none-despite-search'

export function citationState(
  citationCount: number,
  searchUsed: boolean | null | undefined,
): CitationState {
  if (citationCount > 0) return 'has'
  if (searchUsed === true) return 'none-despite-search'
  if (searchUsed === false) return 'none-no-search'
  return 'unknown'
}

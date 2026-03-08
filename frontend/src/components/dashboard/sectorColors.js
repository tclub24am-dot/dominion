/**
 * S-GLOBAL DOMINION — Sector Color Palette
 * VERSHINA v200.29.2 Protocol
 *
 * Цветовая матрица 12 секторов — уникальный цвет для каждого:
 * FL  cyan-500    — Таксопарк (неоновый аквамарин)
 * LG  green-400   — Логистика (зелёный поток)
 * IT  purple-500  — IT/Консалтинг (фиолетовый интеллект)
 * WH  orange-500  — Автосервис (огненный металл)
 * AI  cyan-600    — AI Аналитик (глубокий циан)
 * FN  violet-600  — Финансы (королевский пурпур) ← «деньги в кошельке»
 * GP  cyan-400    — GPS (светлый циан)
 * TS  amber-500   — Задачи/Отчёты (янтарь)
 * MR  red-500     — Гарнизон Почёта (алый)
 * IV  emerald-500 — Инвестиции (изумруд роста) ← «деньги в росте»
 * FP  yellow-600  — Партнёры/Выплаты (золото)
 * AC  pink-500    — Академия (розовый)
 */
export const SECTOR_COLORS = {
  FL: { glow: '#00f5ff', glowRgb: '0, 245, 255',   accent: '#00f5ff', gradient: 'from-cyan-500/20 to-cyan-500/5' },
  LG: { glow: '#00ff88', glowRgb: '0, 255, 136',   accent: '#00ff88', gradient: 'from-emerald-500/20 to-emerald-500/5' },
  IT: { glow: '#a855f7', glowRgb: '168, 85, 247',  accent: '#a855f7', gradient: 'from-purple-500/20 to-purple-500/5' },
  WH: { glow: '#f97316', glowRgb: '249, 115, 22',  accent: '#f97316', gradient: 'from-orange-500/20 to-orange-500/5' },
  AI: { glow: '#06b6d4', glowRgb: '6, 182, 212',   accent: '#06b6d4', gradient: 'from-cyan-600/20 to-cyan-600/5' },
  FN: { glow: '#7c3aed', glowRgb: '124, 58, 237',  accent: '#7c3aed', gradient: 'from-violet-600/20 to-violet-600/5' },
  GP: { glow: '#22d3ee', glowRgb: '34, 211, 238',  accent: '#22d3ee', gradient: 'from-cyan-400/20 to-cyan-400/5' },
  TS: { glow: '#f59e0b', glowRgb: '245, 158, 11',  accent: '#f59e0b', gradient: 'from-amber-500/20 to-amber-500/5' },
  MR: { glow: '#ef4444', glowRgb: '239, 68, 68',   accent: '#ef4444', gradient: 'from-red-500/20 to-red-500/5' },
  IV: { glow: '#10b981', glowRgb: '16, 185, 129',  accent: '#10b981', gradient: 'from-emerald-500/20 to-emerald-500/5' },
  FP: { glow: '#d4a843', glowRgb: '212, 168, 67',  accent: '#d4a843', gradient: 'from-yellow-600/20 to-yellow-600/5' },
  AC: { glow: '#ec4899', glowRgb: '236, 72, 153',  accent: '#ec4899', gradient: 'from-pink-500/20 to-pink-500/5' },
}

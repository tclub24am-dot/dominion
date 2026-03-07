import React from 'react'
// motion удалён — все одноразовые анимации заменены на CSS @keyframes

/**
 * S-GLOBAL DOMINION — World Map Background v8.0 CITADEL
 * ======================================================
 * Реалистичные контуры материков (проекция Меркатора).
 * Приглушённый неон: stroke rgba(0, 255, 242, 0.2).
 * Пульсация ТОЛЬКО для ключевых узлов (точек присутствия Империи).
 * Карта статична и узнаваема как Земля.
 * VERSHINA v200.11 Protocol — РЕСТАВРАЦИЯ ЦИТАДЕЛИ v52.1
 */

// ===== РЕАЛИСТИЧНЫЕ SVG-КОНТУРЫ МАТЕРИКОВ (Меркатор) =====
// viewBox 0 0 1000 500, масштаб приближен к реальной географии

const CONTINENTS = [
  {
    name: 'North America',
    path: 'M 55 120 L 60 105 L 70 92 L 85 80 L 100 72 L 118 65 L 135 60 L 150 58 L 165 55 L 178 53 L 190 55 L 200 60 L 208 68 L 215 78 L 220 90 L 222 100 L 220 110 L 215 118 L 208 125 L 200 132 L 192 138 L 185 145 L 178 152 L 172 158 L 165 162 L 158 168 L 150 172 L 142 175 L 135 178 L 128 180 L 120 178 L 112 175 L 105 170 L 98 165 L 92 158 L 85 150 L 78 142 L 72 135 L 65 128 L 58 122 Z M 130 170 L 138 175 L 145 182 L 150 190 L 148 198 L 142 205 L 135 210 L 128 208 L 122 202 L 118 195 L 120 185 L 125 178 Z',
  },
  {
    name: 'South America',
    path: 'M 195 210 L 202 205 L 210 202 L 218 205 L 225 210 L 230 218 L 235 228 L 238 240 L 240 252 L 240 265 L 238 278 L 235 290 L 230 302 L 225 312 L 220 322 L 215 330 L 210 338 L 205 345 L 200 350 L 195 355 L 190 352 L 185 345 L 180 335 L 178 325 L 175 315 L 173 305 L 172 295 L 172 285 L 173 275 L 175 265 L 178 255 L 180 245 L 183 235 L 186 225 L 190 218 Z',
  },
  {
    name: 'Europe',
    path: 'M 440 60 L 448 55 L 458 52 L 468 50 L 478 52 L 488 55 L 495 60 L 502 65 L 508 72 L 512 80 L 510 88 L 506 95 L 500 100 L 492 105 L 485 108 L 478 110 L 470 108 L 462 105 L 455 100 L 448 95 L 442 88 L 438 80 L 436 70 Z M 420 62 L 428 58 L 434 62 L 434 70 L 428 75 L 420 72 L 418 66 Z',
  },
  {
    name: 'Africa',
    path: 'M 445 128 L 455 122 L 468 118 L 480 120 L 492 125 L 502 132 L 510 142 L 516 155 L 520 168 L 522 182 L 520 195 L 518 208 L 514 222 L 508 235 L 502 248 L 495 258 L 488 268 L 480 275 L 472 280 L 465 282 L 458 280 L 450 275 L 442 268 L 436 258 L 430 248 L 426 235 L 422 222 L 420 208 L 420 195 L 422 182 L 425 168 L 428 155 L 432 142 L 438 132 Z',
  },
  {
    name: 'Asia',
    path: 'M 515 48 L 530 42 L 548 38 L 568 35 L 588 33 L 608 32 L 628 33 L 648 36 L 668 40 L 685 45 L 700 52 L 712 60 L 722 70 L 728 80 L 732 92 L 732 102 L 728 112 L 722 122 L 712 130 L 700 138 L 688 142 L 675 145 L 662 142 L 648 140 L 635 138 L 622 135 L 608 132 L 595 128 L 582 125 L 568 120 L 555 115 L 542 110 L 530 105 L 520 98 L 514 88 L 512 78 L 512 65 L 514 55 Z M 530 108 L 540 112 L 548 118 L 555 128 L 558 138 L 555 148 L 548 155 L 540 158 L 532 155 L 525 148 L 522 138 L 525 128 L 528 118 Z',
  },
  {
    name: 'Australia',
    path: 'M 698 248 L 712 242 L 728 238 L 742 240 L 755 245 L 765 252 L 772 262 L 775 272 L 772 282 L 766 290 L 758 296 L 748 300 L 738 302 L 728 300 L 718 296 L 708 290 L 700 282 L 696 272 L 694 262 L 695 252 Z M 782 302 L 788 298 L 795 296 L 800 300 L 802 308 L 798 316 L 792 318 L 786 314 L 782 308 Z',
  },
  {
    name: 'Greenland',
    path: 'M 265 38 L 278 32 L 292 28 L 308 30 L 318 36 L 322 44 L 320 52 L 314 58 L 305 62 L 295 64 L 282 62 L 272 58 L 266 50 L 262 44 Z',
  },
  {
    name: 'Indonesia',
    path: 'M 672 200 L 685 196 L 698 194 L 712 196 L 725 200 L 735 206 L 740 214 L 736 220 L 728 225 L 718 228 L 705 228 L 692 225 L 682 220 L 675 212 L 672 206 Z',
  },
  {
    name: 'Japan',
    path: 'M 748 82 L 755 76 L 762 74 L 770 76 L 775 82 L 778 90 L 775 98 L 770 104 L 762 108 L 755 106 L 750 100 L 746 92 L 746 86 Z',
  },
  {
    name: 'Arabian Peninsula',
    path: 'M 520 135 L 530 130 L 540 132 L 548 138 L 552 148 L 548 158 L 540 165 L 530 168 L 522 162 L 518 152 L 518 142 Z',
  },
  {
    name: 'Madagascar',
    path: 'M 535 258 L 540 252 L 548 250 L 554 254 L 556 262 L 552 270 L 546 274 L 538 272 L 534 265 Z',
  },
]

// Ключевые узлы присутствия Империи — ТОЛЬКО они пульсируют
const NODES = [
  { x: 165, y: 100, label: 'NYC', delay: 0 },
  { x: 135, y: 135, label: 'MIA', delay: 0.2 },
  { x: 110, y: 85, label: 'CHI', delay: 0.15 },
  { x: 80, y: 110, label: 'LAX', delay: 0.1 },
  { x: 210, y: 250, label: 'SAO', delay: 0.4 },
  { x: 460, y: 78, label: 'LON', delay: 0.1 },
  { x: 480, y: 92, label: 'PAR', delay: 0.3 },
  { x: 500, y: 82, label: 'BER', delay: 0.25 },
  { x: 545, y: 65, label: 'MSK', delay: 0 },
  { x: 535, y: 148, label: 'DXB', delay: 0.3 },
  { x: 648, y: 90, label: 'BEJ', delay: 0.2 },
  { x: 680, y: 100, label: 'SHA', delay: 0.22 },
  { x: 762, y: 88, label: 'TKY', delay: 0.5 },
  { x: 735, y: 268, label: 'SYD', delay: 0.6 },
  { x: 600, y: 112, label: 'DEL', delay: 0.3 },
  { x: 462, y: 200, label: 'NBO', delay: 0.4 },
  { x: 625, y: 125, label: 'BKK', delay: 0.35 },
  { x: 700, y: 210, label: 'SIN', delay: 0.45 },
]

// Линии связи между узлами
const CONNECTIONS = [
  [0, 5], [0, 1], [1, 4], [0, 2], [2, 3],
  [5, 6], [6, 7], [5, 8], [8, 10], [8, 14],
  [10, 11], [11, 12], [10, 14], [14, 16],
  [16, 17], [17, 13], [12, 13],
  [5, 9], [9, 14],
  [9, 15], [4, 1],
  [7, 8], [11, 17],
]

// Координатная сетка
const GRID_LINES = {
  meridians: [100, 200, 300, 400, 500, 600, 700, 800, 900],
  parallels: [50, 100, 150, 200, 250, 300, 350, 400, 450],
}

const WorldMapBackground = React.memo(function WorldMapBackground() {
  return (
    <div
      style={{
        position: 'fixed',
        top: 0,
        left: 0,
        right: 0,
        bottom: 0,
        zIndex: 0,
        pointerEvents: 'none',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        overflow: 'hidden',
        opacity: 0.22,
      }}
    >
      <svg
        viewBox="0 0 1000 500"
        width="100%"
        height="100%"
        preserveAspectRatio="xMidYMid meet"
        style={{ maxWidth: '2200px' }}
      >
        <defs>
          {/* Приглушённый неоновый градиент — бирюзовый */}
          <linearGradient id="wmap-neonGrad" x1="0%" y1="0%" x2="100%" y2="100%">
            <stop offset="0%" stopColor="rgba(0,255,242,0.12)" />
            <stop offset="50%" stopColor="rgba(0,255,242,0.25)" />
            <stop offset="100%" stopColor="rgba(0,255,242,0.12)" />
          </linearGradient>

          {/* Заливка континентов — едва заметная */}
          <linearGradient id="wmap-fillGrad" x1="0%" y1="0%" x2="100%" y2="100%">
            <stop offset="0%" stopColor="rgba(0,255,242,0.02)" />
            <stop offset="50%" stopColor="rgba(0,255,242,0.04)" />
            <stop offset="100%" stopColor="rgba(0,255,242,0.02)" />
          </linearGradient>

          {/* Градиент линий связи */}
          <linearGradient id="wmap-linkGrad" x1="0%" y1="0%" x2="100%" y2="0%">
            <stop offset="0%" stopColor="rgba(0,255,242,0.05)" />
            <stop offset="50%" stopColor="rgba(0,255,242,0.2)" />
            <stop offset="100%" stopColor="rgba(0,255,242,0.05)" />
          </linearGradient>

          {/* Drop-shadow для контуров */}
          <filter id="wmap-neonGlow" x="-20%" y="-20%" width="140%" height="140%">
            <feDropShadow dx="0" dy="0" stdDeviation="2" floodColor="rgba(0,255,242,1)" floodOpacity="0.15" />
          </filter>

          {/* Glow для узлов */}
          <filter id="wmap-nodeGlow" x="-400%" y="-400%" width="900%" height="900%">
            <feGaussianBlur in="SourceGraphic" stdDeviation="4" result="blur1" />
            <feGaussianBlur in="SourceGraphic" stdDeviation="2" result="blur2" />
            <feMerge>
              <feMergeNode in="blur1" />
              <feMergeNode in="blur2" />
              <feMergeNode in="SourceGraphic" />
            </feMerge>
          </filter>

          {/* Glow для линий связи */}
          <filter id="wmap-lineGlow" x="-30%" y="-30%" width="160%" height="160%">
            <feDropShadow dx="0" dy="0" stdDeviation="1.5" floodColor="rgba(0,255,242,1)" floodOpacity="0.12" />
          </filter>
        </defs>

        {/* === Координатная сетка === */}
        <g opacity="0.3">
          {GRID_LINES.meridians.map((x, i) => (
            <line
              key={`m-${i}`}
              x1={x} y1="10" x2={x} y2="490"
              stroke="rgba(0,255,242,0.06)"
              strokeWidth="0.3"
              strokeDasharray="2 10"
            />
          ))}
          {GRID_LINES.parallels.map((y, i) => (
            <line
              key={`p-${i}`}
              x1="10" y1={y} x2="990" y2={y}
              stroke="rgba(0,255,242,0.06)"
              strokeWidth="0.3"
              strokeDasharray="2 10"
            />
          ))}
        </g>

        {/* === Контуры континентов — статичные, узнаваемые === */}
        {CONTINENTS.map((continent, i) => (
          <g key={`c-${i}`}>
            {/* Заливка */}
            <path
              d={continent.path}
              fill="url(#wmap-fillGrad)"
              stroke="none"
              className="wmap-continent-fill"
              style={{ animationDelay: `${0.3 + i * 0.1}s` }}
            />
            {/* Контур — приглушённый неон */}
            <path
              d={continent.path}
              fill="none"
              stroke="rgba(0,255,242,0.2)"
              strokeWidth="1.2"
              strokeLinejoin="round"
              strokeLinecap="round"
              filter="url(#wmap-neonGlow)"
              className="wmap-continent-stroke"
              style={{ animationDelay: `${0.2 + i * 0.1}s` }}
            />
          </g>
        ))}

        {/* === Линии связи — статичные === */}
        {CONNECTIONS.map(([from, to], i) => {
          const n1 = NODES[from]
          const n2 = NODES[to]
          if (!n1 || !n2) return null
          return (
            <line
              key={`l-${i}`}
              x1={n1.x} y1={n1.y}
              x2={n2.x} y2={n2.y}
              stroke="url(#wmap-linkGrad)"
              strokeWidth="0.6"
              strokeDasharray="4 6"
              filter="url(#wmap-lineGlow)"
              className="wmap-connection"
              style={{ animationDelay: `${1.5 + i * 0.05}s` }}
            />
          )
        })}

        {/* === Узлы — ТОЛЬКО они пульсируют (CSS keyframes) === */}
        {NODES.map((node, i) => (
          <g key={`n-${i}`} filter="url(#wmap-nodeGlow)">
            {/* Пульсирующий ореол — CSS @keyframes wmap-pulse-halo */}
            <circle
              cx={node.x}
              cy={node.y}
              r="5"
              fill="none"
              stroke="rgba(0,255,242,0.4)"
              strokeWidth="0.5"
              className="wmap-pulse-halo"
              style={{ animationDelay: `${node.delay + 2}s` }}
            />
            {/* Постоянный ореол — одноразовый fade-in через CSS */}
            <circle
              cx={node.x}
              cy={node.y}
              r="4"
              fill="rgba(0,255,242,0.08)"
              stroke="rgba(0,255,242,0.2)"
              strokeWidth="0.5"
              className="wmap-node-halo"
              style={{ animationDelay: `${1.5 + node.delay}s` }}
            />
            {/* Яркая точка — CSS @keyframes wmap-pulse-dot */}
            <circle
              cx={node.x}
              cy={node.y}
              r="2"
              fill="rgba(0,255,242,0.7)"
              className="wmap-pulse-dot"
              style={{ animationDelay: `${1.5 + node.delay}s` }}
            />
            {/* Метка города — одноразовый fade-in через CSS */}
            <text
              x={node.x}
              y={node.y - 9}
              textAnchor="middle"
              fill="rgba(0,255,242,0.35)"
              fontSize="6"
              fontFamily="'Orbitron', monospace"
              fontWeight="bold"
              letterSpacing="1"
              className="wmap-node-label"
              style={{ animationDelay: `${2 + node.delay}s` }}
            >
              {node.label}
            </text>
          </g>
        ))}
      </svg>
    </div>
  )
})

export default WorldMapBackground

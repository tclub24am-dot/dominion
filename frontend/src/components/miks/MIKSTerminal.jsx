import React, { useEffect, useRef, useState, useCallback } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import {
  Phone, PhoneOff, Send, Sparkles, Search, Circle,
  CheckCheck, Clock, AlertTriangle, Truck, DollarSign,
  X, Mic, MicOff, Volume2, VolumeX, Crown, User, Users
} from 'lucide-react'
import JsSIP from 'jssip'
import api from '../../api/client'

/**
 * S-GLOBAL DOMINION — MIKS Terminal v200.29.2
 * "WhatsApp Dominion Edition"
 * ============================================
 * Слева: список чатов (водители, логисты, партнёры)
 * Справа: окно переписки + кнопка "Позвонить" (WebRTC/Asterisk)
 * Стиль: Black/Gold — сообщения Мастера золотые, сотрудников — тёмно-серые
 * AI-теггинг: [СРОЧНО], [ЛОГИСТИКА], [ФИНАНСЫ]
 * Ollama: реальный запрос к 172.27.192.1:11434
 */

// ─── Константы ────────────────────────────────────────────────────────────────

const OLLAMA_URL = 'http://172.27.192.1:11434'
const OLLAMA_MODEL = 'llama3'

const TAG_COLORS = {
  СРОЧНО:    { bg: 'rgba(239,68,68,0.15)',   border: '#ef4444', text: '#fca5a5' },
  ЛОГИСТИКА: { bg: 'rgba(59,130,246,0.15)',  border: '#3b82f6', text: '#93c5fd' },
  ФИНАНСЫ:   { bg: 'rgba(212,168,67,0.15)',  border: '#d4a843', text: '#fcd34d' },
  ФЛОТ:      { bg: 'rgba(0,245,255,0.12)',   border: '#00f5ff', text: '#67e8f9' },
  ЗАДАЧА:    { bg: 'rgba(168,85,247,0.15)',  border: '#a855f7', text: '#d8b4fe' },
  ОБЩЕЕ:     { bg: 'rgba(255,255,255,0.06)', border: '#ffffff40', text: '#ffffff80' },
}

// ─── Fallback SIP конфигурация (если bootstrap недоступен) ────────────────────
const FALLBACK_SIP_CONFIG = {
  wss_url: 'wss://localhost:8089/ws',
  sip_uri: 'sip:miks@localhost',
  password: 'miks_secret',
  realm: 'localhost',
}

// Статические чаты (в реальном проекте — из API)
const STATIC_CHATS = [
  {
    id: 'mix-ai',
    name: 'Mix — AI Советник',
    role: 'ai',
    type: 'ai',
    avatar: '🤖',
    lastMsg: 'Готов помочь с логистикой и планированием рейсов',
    time: 'сейчас',
    unread: 0,
    online: true,
    isAI: true,
    systemPrompt: 'Ты — Mix, эксперт-советник S-GLOBAL DOMINION. Твоя цель — помогать сотрудникам планировать рейсы, проверять штрафы и давать советы по логистике. Отвечай кратко, по делу, на русском языке. Используй данные о тарифах ВкусВилл: ДС (7622/7985 ₽), Магазин (6795 ₽), Шмель (4483 ₽), Жук (2434 ₽).',
  },
  {
    id: 'ОБЩАЯ',
    name: 'Общий канал',
    role: 'channel',
    avatar: '🏛️',
    lastMsg: 'Добро пожаловать в DOMINION',
    time: '09:00',
    unread: 0,
    online: true,
  },
  {
    id: 'MASTER',
    name: 'Мастер Спартак',
    role: 'master',
    avatar: '👑',
    lastMsg: 'Система активирована',
    time: '09:15',
    unread: 0,
    online: true,
  },
  {
    id: 'ЛОГИСТИКА',
    name: 'Логистика ВКУСВИЛЛ',
    role: 'logistics',
    avatar: '🚚',
    lastMsg: 'Маршрут М4 подтверждён',
    time: '10:30',
    unread: 2,
    online: true,
  },
  {
    id: 'ФЛОТ',
    name: 'Флот T-CLUB24',
    role: 'fleet',
    avatar: '🚗',
    lastMsg: 'На линии 38 авто',
    time: '11:00',
    unread: 0,
    online: true,
  },
  {
    id: 'ФИНАНСЫ',
    name: 'Финансы & Казна',
    role: 'finance',
    avatar: '💰',
    lastMsg: 'Баланс обновлён',
    time: '11:45',
    unread: 1,
    online: false,
  },
  {
    id: 'ПАРТНЁРЫ',
    name: 'Партнёры',
    role: 'partners',
    avatar: '🤝',
    lastMsg: 'Новый контракт',
    time: 'Вчера',
    unread: 0,
    online: false,
  },
]

// ─── Вспомогательные компоненты ───────────────────────────────────────────────

function TagBadge({ tag }) {
  const style = TAG_COLORS[tag] || TAG_COLORS.ОБЩЕЕ
  return (
    <span
      className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-orbitron font-bold tracking-wider uppercase"
      style={{ background: style.bg, border: `1px solid ${style.border}`, color: style.text }}
    >
      {tag === 'СРОЧНО' && <AlertTriangle size={8} />}
      {tag === 'ЛОГИСТИКА' && <Truck size={8} />}
      {tag === 'ФИНАНСЫ' && <DollarSign size={8} />}
      {tag}
    </span>
  )
}

function MessageBubble({ msg, isMaster }) {
  const time = msg.created_at
    ? new Date(msg.created_at).toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' })
    : ''

  const isOracle = msg.role === 'assistant'

  return (
    <motion.div
      className={`flex ${isMaster ? 'justify-end' : 'justify-start'} mb-3`}
      initial={{ opacity: 0, y: 8, scale: 0.97 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      transition={{ duration: 0.25, ease: 'easeOut' }}
    >
      {/* Аватар (для входящих) */}
      {!isMaster && (
        <div
          className="w-7 h-7 rounded-full flex items-center justify-center text-xs mr-2 flex-shrink-0 mt-auto"
          style={{
            background: isOracle
              ? 'linear-gradient(135deg, #7c3aed, #4f46e5)'
              : 'linear-gradient(135deg, #1e293b, #334155)',
            border: isOracle ? '1px solid #7c3aed60' : '1px solid #ffffff15',
          }}
        >
          {isOracle ? '🤖' : '👤'}
        </div>
      )}

      <div className={`max-w-[72%] ${isMaster ? 'items-end' : 'items-start'} flex flex-col gap-1`}>
        {/* Имя отправителя */}
        {!isMaster && (
          <span className="text-[10px] font-montserrat px-1" style={{ color: isOracle ? '#a78bfa' : '#ffffff50' }}>
            {isOracle ? 'Oracle AI' : (msg.author || 'Сотрудник')}
          </span>
        )}

        {/* Пузырь сообщения */}
        <div
          className="relative px-4 py-2.5 rounded-2xl text-[13px] font-montserrat leading-relaxed"
          style={
            isMaster
              ? {
                  background: 'linear-gradient(135deg, #d4a843, #b8860b)',
                  color: '#0d0c0b',
                  borderRadius: '18px 18px 4px 18px',
                  boxShadow: '0 4px 16px rgba(212,168,67,0.25)',
                }
              : isOracle
              ? {
                  background: 'linear-gradient(135deg, #1e1b4b, #312e81)',
                  color: '#e0e7ff',
                  borderRadius: '18px 18px 18px 4px',
                  border: '1px solid #4f46e580',
                  boxShadow: '0 4px 16px rgba(79,70,229,0.15)',
                }
              : {
                  background: 'linear-gradient(135deg, #1a1f2e, #1e2436)',
                  color: '#e2e8f0',
                  borderRadius: '18px 18px 18px 4px',
                  border: '1px solid #ffffff10',
                  boxShadow: '0 2px 8px rgba(0,0,0,0.3)',
                }
          }
        >
          {msg.content}

          {/* AI-теги внутри пузыря */}
          {msg.tags && msg.tags.length > 0 && (
            <div className="flex flex-wrap gap-1 mt-2">
              {msg.tags.map((tag) => (
                <TagBadge key={tag} tag={tag} />
              ))}
            </div>
          )}
        </div>

        {/* Время + статус */}
        <div className={`flex items-center gap-1 px-1 ${isMaster ? 'justify-end' : 'justify-start'}`}>
          <span className="text-[10px] font-montserrat" style={{ color: '#ffffff30' }}>{time}</span>
          {isMaster && <CheckCheck size={11} style={{ color: '#d4a84380' }} />}
        </div>
      </div>

      {/* Аватар Мастера */}
      {isMaster && (
        <div
          className="w-7 h-7 rounded-full flex items-center justify-center text-xs ml-2 flex-shrink-0 mt-auto"
          style={{
            background: 'linear-gradient(135deg, #d4a843, #b8860b)',
            border: '1px solid #d4a84360',
          }}
        >
          <Crown size={12} style={{ color: '#0d0c0b' }} />
        </div>
      )}
    </motion.div>
  )
}

// ─── Главный компонент ────────────────────────────────────────────────────────

export default function MIKSTerminal() {
  const [chats] = useState(STATIC_CHATS)
  const [activeChat, setActiveChat] = useState(STATIC_CHATS[0])
  const [messages, setMessages] = useState([])
  const [inputText, setInputText] = useState('')
  const [searchQuery, setSearchQuery] = useState('')
  const [loading, setLoading] = useState(false)
  const [sending, setSending] = useState(false)

  // AI-теггинг
  const [taggingState, setTaggingState] = useState('idle') // idle | loading | done | error
  const [lastTags, setLastTags] = useState([])
  const [ollamaStatus, setOllamaStatus] = useState('unknown') // unknown | online | offline

  // WebRTC / Звонок
  const [callState, setCallState] = useState('idle') // idle | calling | active | ended
  const [callSession, setCallSession] = useState(null)
  const [bootstrap, setBootstrap] = useState(null)
  const [micMuted, setMicMuted] = useState(false)
  const [speakerMuted, setSpeakerMuted] = useState(false)
  const [uaRegistered, setUaRegistered] = useState(false)
  const uaRef = useRef(null)
  const remoteAudioRef = useRef(null)

  const messagesEndRef = useRef(null)
  const wsRef = useRef(null)
  const inputRef = useRef(null)

  // ── Загрузка bootstrap ──────────────────────────────────────────────────────
  useEffect(() => {
    api.get('/api/v1/miks/bootstrap')
      .then(({ data }) => setBootstrap(data))
      .catch(() => {})
  }, [])

  // ── Проверка Ollama ─────────────────────────────────────────────────────────
  useEffect(() => {
    fetch(`${OLLAMA_URL}/api/tags`, { signal: AbortSignal.timeout(3000) })
      .then((r) => setOllamaStatus(r.ok ? 'online' : 'offline'))
      .catch(() => setOllamaStatus('offline'))
  }, [])

  // ── Загрузка сообщений при смене чата ──────────────────────────────────────
  useEffect(() => {
    if (!activeChat) return
    setMessages([])

    // AI-чат Mix: показываем приветствие без запроса к API
    if (activeChat.isAI) {
      setMessages([{
        id: 'mix-welcome',
        role: 'assistant',
        content: '👋 Привет! Я Mix — AI советник S-GLOBAL DOMINION. Помогу с планированием рейсов, тарифами ВкусВилл и логистикой. Спрашивай!',
        created_at: new Date().toISOString(),
        author: 'Mix AI',
      }])
      return
    }

    setLoading(true)
    api.get('/api/v1/messenger/messages', { params: { channel: activeChat.id, limit: 50 } })
      .then(({ data }) => {
        setMessages(data.messages || [])
      })
      .catch(() => {
        // Показываем приветственное сообщение если API недоступен
        setMessages([{
          id: 'welcome',
          role: 'assistant',
          content: `Добро пожаловать в канал «${activeChat.name}». Система MIKS активна.`,
          created_at: new Date().toISOString(),
          author: 'Oracle AI',
        }])
      })
      .finally(() => setLoading(false))
  }, [activeChat])

  // ── WebSocket для real-time сообщений ──────────────────────────────────────
  useEffect(() => {
    // AI-чат не использует WebSocket
    if (!activeChat || activeChat.isAI) return
    const protocol = window.location.protocol === 'https:' ? 'wss' : 'ws'
    const wsUrl = `${protocol}://${window.location.host}/api/v1/ws/messenger?channel=${encodeURIComponent(activeChat.id)}`

    const ws = new WebSocket(wsUrl)
    wsRef.current = ws

    ws.onmessage = (event) => {
      try {
        const payload = JSON.parse(event.data)
        if (payload.type === 'message' && payload.message) {
          setMessages((prev) => [...prev, payload.message])
        }
      } catch {}
    }

    ws.onerror = () => {}
    ws.onclose = () => {}

    return () => {
      ws.close()
    }
  }, [activeChat])

  // ── Автоскролл ─────────────────────────────────────────────────────────────
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  // ── Инициализация JsSIP UA (ИЗМЕНЕНИЕ 3: register: true + fallback config) ──
  useEffect(() => {
    // Используем bootstrap данные или fallback конфигурацию
    const sipCfg = bootstrap?.webrtc?.wss_url
      ? bootstrap.webrtc
      : FALLBACK_SIP_CONFIG

    try {
      const socket = new JsSIP.WebSocketInterface(sipCfg.wss_url)
      const ua = new JsSIP.UA({
        sockets: [socket],
        uri: sipCfg.sip_uri,
        password: sipCfg.password || '',
        realm: sipCfg.realm,
        display_name: 'MIKS Terminal',
        register: true,
        register_expires: 300,
        session_timers: false,
      })

      ua.on('registered', () => {
        setUaRegistered(true)
      })
      ua.on('unregistered', () => {
        setUaRegistered(false)
      })
      ua.on('registrationFailed', () => {
        setUaRegistered(false)
      })

      ua.start()
      uaRef.current = ua
      return () => {
        ua.stop()
        uaRef.current = null
        setUaRegistered(false)
      }
    } catch {}
  }, [bootstrap])

  // ── Отправка сообщения (ИЗМЕНЕНИЕ 4: AI-чат Mix) ───────────────────────────
  const sendMessage = useCallback(async () => {
    const text = inputText.trim()
    if (!text || sending) return

    setSending(true)
    setInputText('')

    // Оптимистичное добавление
    const optimistic = {
      id: `opt-${Date.now()}`,
      role: 'user',
      content: text,
      created_at: new Date().toISOString(),
      _optimistic: true,
    }
    setMessages((prev) => [...prev, optimistic])

    // ── AI-чат Mix: запрос к /api/v1/miks/ai-chat ──────────────────────────
    if (activeChat?.isAI) {
      try {
        const { data } = await api.post('/api/v1/miks/ai-chat', {
          message: text,
          system_prompt: activeChat.systemPrompt,
          chat_id: activeChat.id,
        })
        // Заменяем оптимистичное сообщение реальным
        setMessages((prev) =>
          prev.map((m) => (m.id === optimistic.id ? { ...optimistic, _optimistic: false } : m))
        )
        // Добавляем ответ Mix AI
        setMessages((prev) => [...prev, {
          id: `mix-${Date.now()}`,
          role: 'assistant',
          content: data.reply,
          created_at: new Date().toISOString(),
          author: 'Mix AI',
        }])
      } catch {
        // Fallback: показываем ошибку в чате
        setMessages((prev) => [...prev, {
          id: `mix-err-${Date.now()}`,
          role: 'assistant',
          content: '⚠️ Mix AI временно недоступен. Проверьте подключение к серверу.',
          created_at: new Date().toISOString(),
          author: 'Mix AI',
        }])
      } finally {
        setSending(false)
        inputRef.current?.focus()
      }
      return
    }

    // ── Обычный чат: отправка через API ────────────────────────────────────
    try {
      const { data } = await api.post('/api/v1/messenger/messages', {
        channel: activeChat.id,
        content: text,
      })
      // Заменяем оптимистичное сообщение реальным
      setMessages((prev) =>
        prev.map((m) => (m.id === optimistic.id ? data.message : m))
      )
      // Добавляем ответ Oracle если есть
      if (data.oracle) {
        setMessages((prev) => [...prev, data.oracle])
      }
    } catch {
      // Оставляем оптимистичное сообщение
    } finally {
      setSending(false)
      inputRef.current?.focus()
    }
  }, [inputText, sending, activeChat])

  // ── AI-теггинг через /api/v1/miks/tag-message ──────────────────────────────
  const tagWithAI = useCallback(async () => {
    const text = inputText.trim()
    if (!text) return

    setTaggingState('loading')
    try {
      const { data } = await api.post('/api/v1/miks/tag-message', { message: text })
      setLastTags(data.tagging?.tags || [])
      setTaggingState('done')
    } catch {
      // Fallback: прямой запрос к Ollama
      try {
        const ollamaRes = await fetch(`${OLLAMA_URL}/api/generate`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            model: OLLAMA_MODEL,
            prompt: `Классифицируй сообщение. Ответь ТОЛЬКО тегами через запятую из списка: СРОЧНО, ЛОГИСТИКА, ФИНАНСЫ, ФЛОТ, ЗАДАЧА, ОБЩЕЕ.\nСообщение: "${text}"\nТеги:`,
            stream: false,
          }),
          signal: AbortSignal.timeout(10000),
        })
        const ollamaData = await ollamaRes.json()
        const rawTags = (ollamaData.response || 'ОБЩЕЕ')
          .split(',')
          .map((t) => t.trim().toUpperCase())
          .filter((t) => Object.keys(TAG_COLORS).includes(t))
        setLastTags(rawTags.length > 0 ? rawTags : ['ОБЩЕЕ'])
        setTaggingState('done')
      } catch {
        setLastTags(['ОБЩЕЕ'])
        setTaggingState('error')
      }
    }
  }, [inputText])

  // ── WebRTC Звонок (ИЗМЕНЕНИЕ 3: активация при uaRegistered) ────────────────
  const startCall = useCallback(() => {
    if (!uaRef.current || callState !== 'idle') return
    // Для AI-чата звонок не поддерживается
    if (activeChat?.isAI) return
    // Используем sip:system@localhost как внутренний номер логиста
    const realm = bootstrap?.webrtc?.realm || FALLBACK_SIP_CONFIG.realm
    const target = `sip:system@${realm}`
    setCallState('calling')

    try {
      const session = uaRef.current.call(target, {
        mediaConstraints: { audio: true, video: false },
        rtcOfferConstraints: { offerToReceiveAudio: true },
      })

      session.on('confirmed', () => setCallState('active'))
      session.on('ended', () => { setCallState('ended'); setTimeout(() => setCallState('idle'), 2000) })
      session.on('failed', () => { setCallState('ended'); setTimeout(() => setCallState('idle'), 2000) })

      session.connection?.addEventListener('track', (e) => {
        if (remoteAudioRef.current) {
          remoteAudioRef.current.srcObject = e.streams[0]
        }
      })

      setCallSession(session)
    } catch {
      setCallState('idle')
    }
  }, [callState, activeChat, bootstrap])

  const endCall = useCallback(() => {
    callSession?.terminate()
    setCallSession(null)
    setCallState('idle')
  }, [callSession])

  const toggleMic = useCallback(() => {
    if (!callSession) return
    const tracks = callSession.connection?.getSenders()
      ?.find((s) => s.track?.kind === 'audio')?.track
    if (tracks) {
      tracks.enabled = micMuted
      setMicMuted(!micMuted)
    }
  }, [callSession, micMuted])

  // ── Фильтрация чатов ────────────────────────────────────────────────────────
  const filteredChats = chats.filter((c) =>
    c.name.toLowerCase().includes(searchQuery.toLowerCase())
  )

  // ── Рендер ──────────────────────────────────────────────────────────────────
  return (
    <section className="flex flex-col h-full overflow-hidden">
      {/* Заголовок секции */}
      <div className="flex items-center gap-3 mb-4 px-4 pt-4 flex-shrink-0">
        <div className="h-px flex-1 max-w-8" style={{ background: 'linear-gradient(90deg, #d4a843, transparent)' }} />
        <span className="font-orbitron text-[10px] tracking-[0.4em] uppercase text-[#d4a843]/60">
          MIKS DOMINION MESSENGER
        </span>
        <div className="h-px flex-1 max-w-8" style={{ background: 'linear-gradient(90deg, transparent, #d4a843)' }} />
        {/* Статус Ollama */}
        <div className="flex items-center gap-1.5">
          <span
            className="w-2 h-2 rounded-full"
            style={{
              backgroundColor: ollamaStatus === 'online' ? '#00ff88' : ollamaStatus === 'offline' ? '#ef4444' : '#f59e0b',
              boxShadow: ollamaStatus === 'online' ? '0 0 6px #00ff8880' : 'none',
            }}
          />
          <span className="text-[9px] font-orbitron tracking-wider" style={{ color: '#ffffff30' }}>
            OLLAMA {ollamaStatus.toUpperCase()}
          </span>
        </div>
      </div>

      {/* Основной контейнер мессенджера */}
      <div
        className="flex-1 overflow-hidden border"
        style={{
          borderColor: '#d4a84320',
          background: 'linear-gradient(135deg, #0a0d14, #0d1020)',
          boxShadow: '0 24px 80px rgba(0,0,0,0.6), inset 0 1px 0 rgba(212,168,67,0.08)',
          display: 'flex',
          minHeight: 0,
        }}
      >
        {/* ═══ ЛЕВАЯ ПАНЕЛЬ: Список чатов ═══════════════════════════════════ */}
        <div
          className="flex flex-col border-r"
          style={{
            width: '280px',
            minWidth: '280px',
            borderColor: '#ffffff08',
            background: 'rgba(0,0,0,0.3)',
          }}
        >
          {/* Шапка */}
          <div
            className="px-4 py-3 border-b flex items-center justify-between"
            style={{ borderColor: '#ffffff08' }}
          >
            <div className="flex items-center gap-2">
              <div
                className="w-8 h-8 rounded-full flex items-center justify-center"
                style={{ background: 'linear-gradient(135deg, #d4a843, #b8860b)' }}
              >
                <Crown size={14} style={{ color: '#0d0c0b' }} />
              </div>
              <div>
                <div className="text-[11px] font-orbitron font-bold text-[#d4a843]">MIKS</div>
                <div className="text-[9px] font-montserrat text-white/30">Dominion Messenger</div>
              </div>
            </div>
            <div className="flex items-center gap-1">
              <span className="w-1.5 h-1.5 rounded-full bg-[#00ff88] animate-pulse" />
              <span className="text-[9px] font-montserrat text-white/30">LIVE</span>
            </div>
          </div>

          {/* Поиск */}
          <div className="px-3 py-2">
            <div
              className="flex items-center gap-2 px-3 py-2 rounded-xl"
              style={{ background: 'rgba(255,255,255,0.04)', border: '1px solid rgba(255,255,255,0.06)' }}
            >
              <Search size={12} style={{ color: '#ffffff40' }} />
              <input
                type="text"
                placeholder="Поиск чатов..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="flex-1 bg-transparent text-[12px] font-montserrat text-white/70 outline-none placeholder:text-white/25"
              />
            </div>
          </div>

          {/* Список чатов */}
          <div className="flex-1 overflow-y-auto custom-scrollbar">
            {filteredChats.map((chat) => (
              <button
                key={chat.id}
                onClick={() => setActiveChat(chat)}
                className="w-full px-3 py-3 flex items-center gap-3 transition-all duration-200 text-left"
                style={{
                  background: activeChat?.id === chat.id
                    ? 'linear-gradient(90deg, rgba(212,168,67,0.12), rgba(212,168,67,0.04))'
                    : 'transparent',
                  borderLeft: activeChat?.id === chat.id
                    ? '2px solid #d4a843'
                    : '2px solid transparent',
                }}
              >
                {/* Аватар */}
                <div className="relative flex-shrink-0">
                  <div
                    className="w-10 h-10 rounded-full flex items-center justify-center text-lg"
                    style={{
                      background: 'linear-gradient(135deg, #1a1f2e, #252b3b)',
                      border: activeChat?.id === chat.id ? '1px solid #d4a84340' : '1px solid #ffffff10',
                    }}
                  >
                    {chat.avatar}
                  </div>
                  {chat.online && (
                    <span
                      className="absolute bottom-0 right-0 w-2.5 h-2.5 rounded-full border-2"
                      style={{ backgroundColor: '#00ff88', borderColor: '#0a0d14' }}
                    />
                  )}
                </div>

                {/* Инфо */}
                <div className="flex-1 min-w-0">
                  <div className="flex items-center justify-between mb-0.5">
                    <span
                      className="text-[12px] font-montserrat font-semibold truncate"
                      style={{ color: activeChat?.id === chat.id ? '#d4a843' : '#e2e8f0' }}
                    >
                      {chat.name}
                    </span>
                    <span className="text-[9px] font-montserrat flex-shrink-0 ml-1" style={{ color: '#ffffff30' }}>
                      {chat.time}
                    </span>
                  </div>
                  <div className="flex items-center justify-between">
                    <span className="text-[11px] font-montserrat truncate" style={{ color: '#ffffff40' }}>
                      {chat.lastMsg}
                    </span>
                    {chat.unread > 0 && (
                      <span
                        className="flex-shrink-0 ml-1 w-4 h-4 rounded-full flex items-center justify-center text-[9px] font-bold"
                        style={{ background: '#d4a843', color: '#0d0c0b' }}
                      >
                        {chat.unread}
                      </span>
                    )}
                  </div>
                </div>
              </button>
            ))}
          </div>
        </div>

        {/* ═══ ПРАВАЯ ПАНЕЛЬ: Окно переписки ════════════════════════════════ */}
        <div className="flex-1 flex flex-col min-w-0">
          {/* Шапка чата */}
          <div
            className="px-5 py-3 border-b flex items-center justify-between flex-shrink-0"
            style={{ borderColor: '#ffffff08', background: 'rgba(0,0,0,0.2)' }}
          >
            <div className="flex items-center gap-3">
              <div
                className="w-9 h-9 rounded-full flex items-center justify-center text-base"
                style={{ background: 'linear-gradient(135deg, #1a1f2e, #252b3b)', border: '1px solid #d4a84320' }}
              >
                {activeChat?.avatar}
              </div>
              <div>
                <div className="text-[13px] font-montserrat font-semibold text-white/90">
                  {activeChat?.name}
                </div>
                <div className="text-[10px] font-montserrat" style={{ color: '#ffffff35' }}>
                  {activeChat?.online ? '● В сети' : '○ Не в сети'}
                </div>
              </div>
            </div>

            {/* Кнопки управления звонком */}
            <div className="flex items-center gap-2">
              {callState === 'idle' && !activeChat?.isAI && (
                <motion.button
                  onClick={startCall}
                  disabled={!uaRegistered}
                  title={uaRegistered ? 'Позвонить' : 'SIP не зарегистрирован'}
                  className="flex items-center gap-2 px-4 py-2 rounded-xl text-[11px] font-orbitron font-bold tracking-wider uppercase transition-all"
                  style={{
                    background: uaRegistered
                      ? 'linear-gradient(135deg, rgba(0,255,136,0.15), rgba(0,200,100,0.08))'
                      : 'rgba(255,255,255,0.04)',
                    border: `1px solid ${uaRegistered ? 'rgba(0,255,136,0.3)' : 'rgba(255,255,255,0.1)'}`,
                    color: uaRegistered ? '#00ff88' : '#ffffff30',
                    cursor: uaRegistered ? 'pointer' : 'not-allowed',
                    opacity: uaRegistered ? 1 : 0.5,
                  }}
                  whileHover={uaRegistered ? { scale: 1.03 } : {}}
                  whileTap={uaRegistered ? { scale: 0.97 } : {}}
                >
                  <Phone size={13} />
                  {uaRegistered ? 'Позвонить' : 'SIP...'}
                </motion.button>
              )}

              {(callState === 'calling' || callState === 'active') && (
                <div className="flex items-center gap-2">
                  {/* Статус звонка */}
                  <div
                    className="flex items-center gap-2 px-3 py-1.5 rounded-xl text-[11px] font-orbitron"
                    style={{
                      background: callState === 'active' ? 'rgba(0,255,136,0.1)' : 'rgba(212,168,67,0.1)',
                      border: `1px solid ${callState === 'active' ? '#00ff8840' : '#d4a84340'}`,
                      color: callState === 'active' ? '#00ff88' : '#d4a843',
                    }}
                  >
                    <span className="w-1.5 h-1.5 rounded-full animate-pulse" style={{ backgroundColor: 'currentColor' }} />
                    {callState === 'calling' ? 'ВЫЗОВ...' : 'АКТИВЕН'}
                  </div>

                  {/* Микрофон */}
                  <button
                    onClick={toggleMic}
                    className="w-8 h-8 rounded-full flex items-center justify-center transition-all"
                    style={{
                      background: micMuted ? 'rgba(239,68,68,0.2)' : 'rgba(255,255,255,0.06)',
                      border: `1px solid ${micMuted ? '#ef444440' : '#ffffff15'}`,
                    }}
                  >
                    {micMuted ? <MicOff size={13} style={{ color: '#ef4444' }} /> : <Mic size={13} style={{ color: '#ffffff60' }} />}
                  </button>

                  {/* Завершить */}
                  <motion.button
                    onClick={endCall}
                    className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-[11px] font-orbitron font-bold"
                    style={{
                      background: 'rgba(239,68,68,0.15)',
                      border: '1px solid rgba(239,68,68,0.3)',
                      color: '#ef4444',
                    }}
                    whileTap={{ scale: 0.95 }}
                  >
                    <PhoneOff size={12} />
                    Завершить
                  </motion.button>
                </div>
              )}

              {callState === 'ended' && (
                <span className="text-[11px] font-orbitron text-white/30">Звонок завершён</span>
              )}
            </div>
          </div>

          {/* Область сообщений */}
          <div className="flex-1 overflow-y-auto px-5 py-4 custom-scrollbar">
            {loading ? (
              <div className="flex items-center justify-center h-full">
                <motion.div
                  className="w-6 h-6 rounded-full border-2 border-[#d4a843]/20 border-t-[#d4a843]"
                  animate={{ rotate: 360 }}
                  transition={{ duration: 1, repeat: Infinity, ease: 'linear' }}
                />
              </div>
            ) : messages.length === 0 ? (
              <div className="flex flex-col items-center justify-center h-full gap-3">
                <div className="text-3xl opacity-30">💬</div>
                <span className="text-[12px] font-montserrat text-white/25">Нет сообщений. Начните переписку.</span>
              </div>
            ) : (
              <>
                {messages.map((msg) => (
                  <MessageBubble
                    key={msg.id}
                    msg={msg}
                    isMaster={msg.role === 'user'}
                  />
                ))}
                <div ref={messagesEndRef} />
              </>
            )}
          </div>

          {/* AI-теги результат */}
          <AnimatePresence>
            {taggingState === 'done' && lastTags.length > 0 && (
              <motion.div
                className="px-5 py-2 flex items-center gap-2 border-t"
                style={{ borderColor: '#ffffff06', background: 'rgba(0,0,0,0.2)' }}
                initial={{ opacity: 0, height: 0 }}
                animate={{ opacity: 1, height: 'auto' }}
                exit={{ opacity: 0, height: 0 }}
              >
                <Sparkles size={11} style={{ color: '#a855f7' }} />
                <span className="text-[10px] font-orbitron text-white/30 mr-1">AI:</span>
                {lastTags.map((tag) => <TagBadge key={tag} tag={tag} />)}
                <button
                  onClick={() => { setLastTags([]); setTaggingState('idle') }}
                  className="ml-auto"
                >
                  <X size={11} style={{ color: '#ffffff30' }} />
                </button>
              </motion.div>
            )}
          </AnimatePresence>

          {/* Поле ввода */}
          <div
            className="px-4 py-3 border-t flex items-end gap-3 flex-shrink-0"
            style={{ borderColor: '#ffffff08', background: 'rgba(0,0,0,0.3)' }}
          >
            {/* Textarea */}
            <div
              className="flex-1 rounded-2xl px-4 py-3 flex items-end gap-2"
              style={{
                background: 'rgba(255,255,255,0.04)',
                border: '1px solid rgba(255,255,255,0.08)',
              }}
            >
              <textarea
                ref={inputRef}
                value={inputText}
                onChange={(e) => setInputText(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' && !e.shiftKey) {
                    e.preventDefault()
                    sendMessage()
                  }
                }}
                placeholder="Написать сообщение..."
                rows={1}
                className="flex-1 bg-transparent text-[13px] font-montserrat text-white/85 outline-none resize-none placeholder:text-white/25 leading-relaxed"
                style={{ maxHeight: '100px', overflowY: 'auto' }}
              />
            </div>

            {/* Кнопка AI-теггинга */}
            <motion.button
              onClick={tagWithAI}
              disabled={!inputText.trim() || taggingState === 'loading'}
              className="w-10 h-10 rounded-xl flex items-center justify-center flex-shrink-0 transition-all"
              style={{
                background: taggingState === 'loading'
                  ? 'rgba(168,85,247,0.2)'
                  : 'rgba(168,85,247,0.12)',
                border: '1px solid rgba(168,85,247,0.3)',
                opacity: !inputText.trim() ? 0.4 : 1,
              }}
              whileHover={{ scale: 1.05 }}
              whileTap={{ scale: 0.95 }}
              title="Отправить в Ollama (AI-теггинг)"
            >
              {taggingState === 'loading' ? (
                <motion.div
                  className="w-4 h-4 rounded-full border-2 border-[#a855f7]/30 border-t-[#a855f7]"
                  animate={{ rotate: 360 }}
                  transition={{ duration: 0.8, repeat: Infinity, ease: 'linear' }}
                />
              ) : (
                <Sparkles size={15} style={{ color: '#a855f7' }} />
              )}
            </motion.button>

            {/* Кнопка отправки */}
            <motion.button
              onClick={sendMessage}
              disabled={!inputText.trim() || sending}
              className="w-10 h-10 rounded-xl flex items-center justify-center flex-shrink-0 transition-all"
              style={{
                background: inputText.trim()
                  ? 'linear-gradient(135deg, #d4a843, #b8860b)'
                  : 'rgba(212,168,67,0.1)',
                border: '1px solid rgba(212,168,67,0.3)',
                opacity: !inputText.trim() ? 0.4 : 1,
              }}
              whileHover={{ scale: 1.05 }}
              whileTap={{ scale: 0.95 }}
            >
              {sending ? (
                <motion.div
                  className="w-4 h-4 rounded-full border-2 border-[#0d0c0b]/30 border-t-[#0d0c0b]"
                  animate={{ rotate: 360 }}
                  transition={{ duration: 0.8, repeat: Infinity, ease: 'linear' }}
                />
              ) : (
                <Send size={15} style={{ color: inputText.trim() ? '#0d0c0b' : '#d4a84360' }} />
              )}
            </motion.button>
          </div>
        </div>
      </div>

      {/* Скрытый audio элемент для WebRTC */}
      <audio ref={remoteAudioRef} autoPlay style={{ display: 'none' }} />
    </section>
  )
}

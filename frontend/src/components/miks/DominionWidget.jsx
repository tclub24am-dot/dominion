import React, { useState, useEffect, useRef, useCallback } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import {
  X, Send, Phone, PhoneOff, PhoneCall,
  Mic, MicOff,
  Search, Crown, Hash, Bot,
  Truck, Wallet, Handshake, Car,
  CheckCheck,
  Delete, ChevronLeft,
  Archive
} from 'lucide-react'
import JsSIP from 'jssip'
import api from '../../api/client'

/**
 * S-GLOBAL DOMINION — Dominion Multi-Widget v2.0 (Chaty-style)
 * ================================================
 * Плавающая кнопка (нижний правый угол) → "веер" из 3 кнопок:
 *   💬 Чат MIKS (модальное окно 900×700)
 *   📞 Звонок (панель набора номера)
 *   ✨ ИИ Mix (прямой переход к советнику)
 * Модальное окно: backdrop-blur, WhatsApp-стиль
 * REC 🔴 индикатор при активном звонке
 * Архив звонков: /calls
 */

// ─── Конфигурация ─────────────────────────────────────────────────────────────

const FALLBACK_SIP = {
  wss_url: 'wss://localhost:8089/ws',
  sip_uri: 'sip:miks@localhost',
  password: '',
  realm: 'localhost',
}

const CHATS = [
  {
    id: 'mix-ai',
    name: 'Mix — ИИ Советник',
    role: 'ai',
    avatar: '🤖',
    avatarBg: 'linear-gradient(135deg, #7c3aed, #4f46e5)',
    lastMsg: 'Готов помочь с рейсами и планированием',
    time: 'сейчас',
    unread: 0,
    online: true,
    isAI: true,
    systemPrompt: 'Ты — Mix, эксперт-советник S-GLOBAL DOMINION. Помогай планировать рейсы, проверять штрафы и давать советы по логистике. Отвечай кратко, по делу, на русском языке. Тарифы ВкусВилл: ДС (7622/7985 ₽), Магазин (6795 ₽), Шмель (4483 ₽), Жук (2434 ₽).',
    icon: Bot,
  },
  {
    id: 'ОБЩАЯ',
    name: 'Общий канал',
    role: 'channel',
    avatar: '🏛️',
    avatarBg: 'linear-gradient(135deg, #1e293b, #334155)',
    lastMsg: 'Добро пожаловать в DOMINION',
    time: '09:00',
    unread: 0,
    online: true,
    icon: Hash,
  },
  {
    id: 'MASTER',
    name: 'Мастер Спартак',
    role: 'master',
    avatar: '👑',
    avatarBg: 'linear-gradient(135deg, #d4a843, #b8860b)',
    lastMsg: 'Система активирована',
    time: '09:15',
    unread: 0,
    online: true,
    icon: Crown,
  },
  {
    id: 'ЛОГИСТИКА',
    name: 'Логистика ВКУСВИЛЛ',
    role: 'logistics',
    avatar: '🚚',
    avatarBg: 'linear-gradient(135deg, #1d4ed8, #1e40af)',
    lastMsg: 'Маршрут М4 подтверждён',
    time: '10:30',
    unread: 2,
    online: true,
    icon: Truck,
  },
  {
    id: 'ФЛОТ',
    name: 'Флот T-CLUB24',
    role: 'fleet',
    avatar: '🚗',
    avatarBg: 'linear-gradient(135deg, #0891b2, #0e7490)',
    lastMsg: 'На линии 38 авто',
    time: '11:00',
    unread: 0,
    online: true,
    icon: Car,
  },
  {
    id: 'ФИНАНСЫ',
    name: 'Финансы & Казна',
    role: 'finance',
    avatar: '💰',
    avatarBg: 'linear-gradient(135deg, #15803d, #166534)',
    lastMsg: 'Баланс обновлён',
    time: '11:45',
    unread: 1,
    online: false,
    icon: Wallet,
  },
  {
    id: 'ПАРТНЁРЫ',
    name: 'Партнёры',
    role: 'partners',
    avatar: '🤝',
    avatarBg: 'linear-gradient(135deg, #7e22ce, #6b21a8)',
    lastMsg: 'Новый контракт',
    time: 'Вчера',
    unread: 0,
    online: false,
    icon: Handshake,
  },
]

// ─── Вспомогательные компоненты ───────────────────────────────────────────────

function Avatar({ chat, size = 40 }) {
  return (
    <div
      className="flex-shrink-0 flex items-center justify-center rounded-full text-lg relative"
      style={{
        width: size,
        height: size,
        background: chat.avatarBg,
        border: '1px solid rgba(255,255,255,0.1)',
        fontSize: size * 0.45,
      }}
    >
      {chat.avatar}
      {chat.online && (
        <span
          className="absolute bottom-0 right-0 w-2.5 h-2.5 rounded-full border-2"
          style={{
            backgroundColor: '#00ff88',
            borderColor: '#0d0c0b',
            boxShadow: '0 0 6px #00ff8880',
          }}
        />
      )}
    </div>
  )
}

function MessageBubble({ msg, isMaster }) {
  const time = msg.created_at
    ? new Date(msg.created_at).toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' })
    : ''
  const isAI = msg.role === 'assistant'

  return (
    <motion.div
      className={`flex ${isMaster ? 'justify-end' : 'justify-start'} mb-3 px-4`}
      initial={{ opacity: 0, y: 8, scale: 0.97 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      transition={{ duration: 0.22, ease: 'easeOut' }}
    >
      {!isMaster && (
        <div
          className="w-7 h-7 rounded-full flex items-center justify-center text-xs mr-2 flex-shrink-0 mt-auto"
          style={{
            background: isAI
              ? 'linear-gradient(135deg, #7c3aed, #4f46e5)'
              : 'linear-gradient(135deg, #1e293b, #334155)',
            border: isAI ? '1px solid #7c3aed60' : '1px solid #ffffff15',
            fontSize: '14px',
          }}
        >
          {isAI ? '🤖' : '👤'}
        </div>
      )}

      <div className={`max-w-[72%] flex flex-col gap-1 ${isMaster ? 'items-end' : 'items-start'}`}>
        {!isMaster && (
          <span className="text-[10px] font-montserrat px-1" style={{ color: isAI ? '#a78bfa' : '#ffffff50' }}>
            {isAI ? 'Mix ИИ' : (msg.author || 'Сотрудник')}
          </span>
        )}

        <div
          className="px-4 py-2.5 rounded-2xl text-[13px] font-montserrat leading-relaxed"
          style={
            isMaster
              ? {
                  background: 'linear-gradient(135deg, #d4a843, #b8860b)',
                  color: '#0d0c0b',
                  borderRadius: '18px 18px 4px 18px',
                  boxShadow: '0 4px 16px rgba(212,168,67,0.25)',
                  fontWeight: 600,
                }
              : isAI
              ? {
                  background: 'linear-gradient(135deg, #1e1b4b, #312e81)',
                  color: '#e0e7ff',
                  borderRadius: '18px 18px 18px 4px',
                  border: '1px solid #4f46e580',
                  boxShadow: '0 4px 16px rgba(79,70,229,0.15)',
                }
              : {
                  background: 'linear-gradient(135deg, #1a1f2e, #1e2436)',
                  color: '#E0E0E0',
                  borderRadius: '18px 18px 18px 4px',
                  border: '1px solid #ffffff10',
                  boxShadow: '0 2px 8px rgba(0,0,0,0.3)',
                }
          }
        >
          {msg.content}
        </div>

        <div className={`flex items-center gap-1 px-1 ${isMaster ? 'justify-end' : 'justify-start'}`}>
          <span className="text-[10px] font-montserrat" style={{ color: '#ffffff30' }}>{time}</span>
          {isMaster && <CheckCheck size={11} style={{ color: '#d4a84380' }} />}
        </div>
      </div>

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

// ─── Панель набора номера ─────────────────────────────────────────────────────

function DialPad({ onDial, onClose }) {
  const [number, setNumber] = useState('')

  const KEYS = [
    ['1', '2', '3'],
    ['4', '5', '6'],
    ['7', '8', '9'],
    ['*', '0', '#'],
  ]

  const press = (k) => setNumber((n) => n + k)
  const backspace = () => setNumber((n) => n.slice(0, -1))

  return (
    <motion.div
      className="absolute inset-0 flex flex-col items-center justify-center z-20"
      style={{ background: 'rgba(13,12,11,0.97)', backdropFilter: 'blur(20px)' }}
      initial={{ opacity: 0, scale: 0.95 }}
      animate={{ opacity: 1, scale: 1 }}
      exit={{ opacity: 0, scale: 0.95 }}
      transition={{ duration: 0.2 }}
    >
      <button
        onClick={onClose}
        className="absolute top-4 left-4 flex items-center gap-2 text-[12px] font-montserrat"
        style={{ color: '#ffffff50' }}
      >
        <ChevronLeft size={16} />
        Назад
      </button>

      <div className="text-[11px] font-orbitron tracking-[0.3em] uppercase mb-6" style={{ color: '#d4a843' }}>
        НАБОР НОМЕРА
      </div>

      <div
        className="w-64 h-12 rounded-xl flex items-center justify-between px-4 mb-6"
        style={{
          background: 'rgba(255,255,255,0.04)',
          border: '1px solid rgba(212,168,67,0.2)',
        }}
      >
        <span className="text-xl font-orbitron font-bold tracking-widest" style={{ color: '#E0E0E0' }}>
          {number || <span style={{ color: '#ffffff20' }}>_ _ _</span>}
        </span>
        {number && (
          <button onClick={backspace} style={{ color: '#ffffff40' }}>
            <Delete size={16} />
          </button>
        )}
      </div>

      <div className="grid grid-cols-3 gap-3 mb-6">
        {KEYS.flat().map((k) => (
          <motion.button
            key={k}
            onClick={() => press(k)}
            className="w-16 h-16 rounded-full flex items-center justify-center text-xl font-orbitron font-bold"
            style={{
              background: 'rgba(255,255,255,0.06)',
              border: '1px solid rgba(255,255,255,0.1)',
              color: '#E0E0E0',
            }}
            whileHover={{ background: 'rgba(212,168,67,0.15)', borderColor: 'rgba(212,168,67,0.4)' }}
            whileTap={{ scale: 0.92 }}
          >
            {k}
          </motion.button>
        ))}
      </div>

      <motion.button
        onClick={() => number && onDial(number)}
        className="w-16 h-16 rounded-full flex items-center justify-center"
        style={{
          background: number ? 'linear-gradient(135deg, #00c853, #00a040)' : 'rgba(255,255,255,0.06)',
          border: number ? '2px solid #00c85360' : '1px solid rgba(255,255,255,0.1)',
          boxShadow: number ? '0 0 20px rgba(0,200,83,0.3)' : 'none',
          cursor: number ? 'pointer' : 'not-allowed',
        }}
        whileHover={number ? { scale: 1.08 } : {}}
        whileTap={number ? { scale: 0.95 } : {}}
      >
        <Phone size={24} style={{ color: number ? '#fff' : '#ffffff30' }} />
      </motion.button>
    </motion.div>
  )
}

// ─── Веер кнопок (Chaty-style) ────────────────────────────────────────────────

function FanMenu({ onOpenChat, onOpenDialPad, onOpenMix, onClose }) {
  const items = [
    {
      id: 'mix',
      label: 'ИИ Mix',
      icon: '✨',
      color: 'linear-gradient(135deg, #7c3aed, #4f46e5)',
      border: 'rgba(124,58,237,0.5)',
      shadow: 'rgba(124,58,237,0.4)',
      onClick: onOpenMix,
    },
    {
      id: 'call',
      label: 'Звонок',
      icon: '📞',
      color: 'linear-gradient(135deg, #00c853, #00a040)',
      border: 'rgba(0,200,83,0.5)',
      shadow: 'rgba(0,200,83,0.4)',
      onClick: onOpenDialPad,
    },
    {
      id: 'chat',
      label: 'Чат MIKS',
      icon: '🟢',
      color: 'linear-gradient(135deg, #d4a843, #b8860b)',
      border: 'rgba(212,168,67,0.5)',
      shadow: 'rgba(212,168,67,0.4)',
      onClick: onOpenChat,
    },
  ]

  return (
    <motion.div
      className="fixed flex flex-col items-end gap-3"
      style={{ bottom: '100px', right: '28px', zIndex: 9998 }}
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
    >
      {items.map((item, i) => (
        <motion.div
          key={item.id}
          className="flex items-center gap-3"
          initial={{ opacity: 0, x: 20, scale: 0.8 }}
          animate={{ opacity: 1, x: 0, scale: 1 }}
          exit={{ opacity: 0, x: 20, scale: 0.8 }}
          transition={{ delay: i * 0.06, duration: 0.2, ease: 'easeOut' }}
        >
          {/* Лейбл */}
          <motion.div
            className="px-3 py-1.5 rounded-xl text-[12px] font-montserrat font-semibold whitespace-nowrap"
            style={{
              background: 'rgba(13,12,11,0.92)',
              border: `1px solid ${item.border}`,
              color: '#E0E0E0',
              backdropFilter: 'blur(12px)',
              boxShadow: `0 4px 16px rgba(0,0,0,0.5)`,
            }}
          >
            {item.label}
          </motion.div>

          {/* Кнопка */}
          <motion.button
            onClick={() => { item.onClick(); onClose() }}
            className="flex items-center justify-center rounded-full flex-shrink-0"
            style={{
              width: '48px',
              height: '48px',
              background: item.color,
              border: `2px solid ${item.border}`,
              boxShadow: `0 0 16px ${item.shadow}`,
              fontSize: '20px',
              cursor: 'pointer',
            }}
            whileHover={{ scale: 1.12 }}
            whileTap={{ scale: 0.92 }}
          >
            {item.icon}
          </motion.button>
        </motion.div>
      ))}
    </motion.div>
  )
}

// ─── Главный компонент ────────────────────────────────────────────────────────

export default function DominionWidget() {
  const [fanOpen, setFanOpen] = useState(false)
  const [isOpen, setIsOpen] = useState(false)
  const [activeChat, setActiveChat] = useState(CHATS[0])
  const [messages, setMessages] = useState([])
  const [inputText, setInputText] = useState('')
  const [sending, setSending] = useState(false)
  const [searchQuery, setSearchQuery] = useState('')
  const [showDialPad, setShowDialPad] = useState(false)
  const [showStandaloneDialPad, setShowStandaloneDialPad] = useState(false)
  const [currentUser, setCurrentUser] = useState(null)

  // Голосовой ввод (Web Speech API)
  const [voiceListening, setVoiceListening] = useState(false)
  const recognitionRef = useRef(null)

  // Телефония
  const [callState, setCallState] = useState('idle') // idle | calling | active | ended
  const [callSession, setCallSession] = useState(null)
  const [micMuted, setMicMuted] = useState(false)
  const [speakerMuted, setSpeakerMuted] = useState(false)
  const [uaRegistered, setUaRegistered] = useState(false)
  const [callDuration, setCallDuration] = useState(0)
  const [isRecording, setIsRecording] = useState(false)
  const [bootstrap, setBootstrap] = useState(null)
  const uaRef = useRef(null)
  const remoteAudioRef = useRef(null)

  const messagesEndRef = useRef(null)
  const inputRef = useRef(null)
  const wsRef = useRef(null)

  // ── Загрузка bootstrap + текущего пользователя ───────────────────────────
  useEffect(() => {
    api.get('/api/v1/miks/bootstrap')
      .then(({ data }) => setBootstrap(data))
      .catch(() => {})
    // Загружаем текущего пользователя для правильного отображения сообщений
    api.get('/api/v1/auth/me')
      .then(({ data }) => setCurrentUser(data))
      .catch(() => {})
  }, [])

  // ── Инициализация JsSIP ───────────────────────────────────────────────────
  useEffect(() => {
    const sipCfg = bootstrap?.webrtc?.wss_url ? bootstrap.webrtc : FALLBACK_SIP
    try {
      const socket = new JsSIP.WebSocketInterface(sipCfg.wss_url)
      const ua = new JsSIP.UA({
        sockets: [socket],
        uri: sipCfg.sip_uri,
        password: sipCfg.password || '',
        realm: sipCfg.realm,
        display_name: 'Dominion Widget',
        register: true,
        register_expires: 300,
        session_timers: false,
      })
      ua.on('registered', () => setUaRegistered(true))
      ua.on('unregistered', () => setUaRegistered(false))
      ua.on('registrationFailed', () => setUaRegistered(false))
      ua.start()
      uaRef.current = ua
      return () => { ua.stop(); uaRef.current = null; setUaRegistered(false) }
    } catch {}
  }, [bootstrap])

  // ── Таймер звонка + REC-индикатор ─────────────────────────────────────────
  useEffect(() => {
    if (callState === 'active') {
      setIsRecording(true)
      setCallDuration(0)
      const t = setInterval(() => setCallDuration((d) => d + 1), 1000)
      return () => { clearInterval(t); setIsRecording(false) }
    } else {
      setIsRecording(false)
      setCallDuration(0)
    }
  }, [callState])

  // ── Загрузка сообщений при смене чата ────────────────────────────────────
  useEffect(() => {
    if (!activeChat) return
    setMessages([])
    setShowDialPad(false)

    if (activeChat.isAI) {
      setMessages([{
        id: 'mix-welcome',
        role: 'assistant',
        content: 'Привет! Я Mix — ИИ советник S-GLOBAL DOMINION. Чем могу помочь?',
        created_at: new Date().toISOString(),
        author: 'Mix ИИ',
      }])
      return
    }

    api.get('/api/v1/messenger/messages', { params: { channel: activeChat.id, limit: 50 } })
      .then(({ data }) => setMessages(data.messages || []))
      .catch(() => {
        setMessages([{
          id: 'welcome',
          role: 'assistant',
          content: `Добро пожаловать в канал «${activeChat.name}». Система MIKS активна.`,
          created_at: new Date().toISOString(),
          author: 'Oracle AI',
        }])
      })
  }, [activeChat])

  // ── WebSocket ─────────────────────────────────────────────────────────────
  useEffect(() => {
    if (!activeChat || activeChat.isAI) return
    const protocol = window.location.protocol === 'https:' ? 'wss' : 'ws'
    const ws = new WebSocket(`${protocol}://${window.location.host}/api/v1/ws/messenger?channel=${encodeURIComponent(activeChat.id)}`)
    wsRef.current = ws
    ws.onmessage = (e) => {
      try {
        const p = JSON.parse(e.data)
        if (p.type === 'message' && p.message) setMessages((prev) => [...prev, p.message])
      } catch {}
    }
    ws.onerror = () => {}
    ws.onclose = () => {}
    return () => ws.close()
  }, [activeChat])

  // ── Автоскролл ────────────────────────────────────────────────────────────
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  // ── Отправка сообщения ────────────────────────────────────────────────────
  const sendMessage = useCallback(async () => {
    const text = inputText.trim()
    if (!text || sending) return
    setSending(true)
    setInputText('')

    const optimistic = {
      id: `opt-${Date.now()}`,
      role: 'user',
      content: text,
      created_at: new Date().toISOString(),
    }
    setMessages((prev) => [...prev, optimistic])

    if (activeChat?.isAI) {
      try {
        const { data } = await api.post('/api/v1/miks/ai-chat', {
          message: text,
          system_prompt: activeChat.systemPrompt,
          chat_id: activeChat.id,
        })
        setMessages((prev) => [...prev, {
          id: `mix-${Date.now()}`,
          role: 'assistant',
          content: data.reply,
          created_at: new Date().toISOString(),
          author: 'Mix ИИ',
        }])
      } catch {
        setMessages((prev) => [...prev, {
          id: `mix-err-${Date.now()}`,
          role: 'assistant',
          content: '⚠️ Mix ИИ временно недоступен. Проверьте подключение к серверу.',
          created_at: new Date().toISOString(),
          author: 'Mix ИИ',
        }])
      } finally {
        setSending(false)
        inputRef.current?.focus()
      }
      return
    }

    try {
      const { data } = await api.post('/api/v1/messenger/messages', {
        channel: activeChat.id,
        content: text,
      })
      setMessages((prev) => prev.map((m) => (m.id === optimistic.id ? data.message : m)))
      if (data.oracle) setMessages((prev) => [...prev, data.oracle])
    } catch {
      // оставляем оптимистичное
    } finally {
      setSending(false)
      inputRef.current?.focus()
    }
  }, [inputText, sending, activeChat])

  // ── Звонок ────────────────────────────────────────────────────────────────
  const startCall = useCallback((targetNumber = null) => {
    if (!uaRef.current || callState !== 'idle') return
    const realm = bootstrap?.webrtc?.realm || FALLBACK_SIP.realm
    const target = targetNumber
      ? `sip:${targetNumber}@${realm}`
      : `sip:system@${realm}`
    setCallState('calling')
    setShowDialPad(false)
    setShowStandaloneDialPad(false)
    try {
      const session = uaRef.current.call(target, {
        mediaConstraints: { audio: true, video: false },
        rtcOfferConstraints: { offerToReceiveAudio: true },
      })
      session.on('confirmed', () => setCallState('active'))
      session.on('ended', () => { setCallState('ended'); setTimeout(() => setCallState('idle'), 2000) })
      session.on('failed', () => { setCallState('ended'); setTimeout(() => setCallState('idle'), 2000) })
      session.connection?.addEventListener('track', (e) => {
        if (remoteAudioRef.current) remoteAudioRef.current.srcObject = e.streams[0]
      })
      setCallSession(session)
    } catch {
      setCallState('idle')
    }
  }, [callState, bootstrap])

  const endCall = useCallback(() => {
    callSession?.terminate()
    setCallSession(null)
    setCallState('idle')
  }, [callSession])

  const toggleMic = useCallback(() => {
    const track = callSession?.connection?.getSenders()?.find((s) => s.track?.kind === 'audio')?.track
    if (track) { track.enabled = micMuted; setMicMuted(!micMuted) }
  }, [callSession, micMuted])

  const formatDuration = (s) => `${String(Math.floor(s / 60)).padStart(2, '0')}:${String(s % 60).padStart(2, '0')}`

  const filteredChats = CHATS.filter((c) =>
    c.name.toLowerCase().includes(searchQuery.toLowerCase())
  )

  const totalUnread = CHATS.reduce((sum, c) => sum + c.unread, 0)

  // ── Голосовой ввод (Web Speech API) ──────────────────────────────────────
  const toggleVoice = useCallback(() => {
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition
    if (!SpeechRecognition) return

    if (voiceListening) {
      recognitionRef.current?.stop()
      setVoiceListening(false)
      return
    }

    const recognition = new SpeechRecognition()
    recognition.lang = 'ru-RU'
    recognition.continuous = false
    recognition.interimResults = false

    recognition.onresult = (e) => {
      const transcript = e.results[0]?.[0]?.transcript || ''
      if (transcript) {
        // Голосовой ввод → сразу отправляем как сообщение в БД
        const finalText = transcript.trim()
        if (finalText) {
          setInputText(finalText)
          // Небольшая задержка чтобы state обновился, затем отправляем
          setTimeout(() => {
            setSending(true)
            const optimistic = {
              id: `voice-${Date.now()}`,
              role: 'user',
              content: finalText,
              created_at: new Date().toISOString(),
              isVoice: true,
            }
            setMessages((prev) => [...prev, optimistic])
            setInputText('')

            if (activeChat?.isAI) {
              api.post('/api/v1/miks/ai-chat', {
                message: finalText,
                system_prompt: activeChat.systemPrompt,
                chat_id: activeChat.id,
              }).then(({ data }) => {
                setMessages((prev) => [...prev, {
                  id: `mix-voice-${Date.now()}`,
                  role: 'assistant',
                  content: data.reply,
                  created_at: new Date().toISOString(),
                  author: 'Mix ИИ',
                }])
              }).catch(() => {}).finally(() => setSending(false))
            } else {
              api.post('/api/v1/messenger/messages', {
                channel: activeChat?.id || 'ОБЩАЯ',
                content: finalText,
              }).then(({ data }) => {
                setMessages((prev) => prev.map((m) => (m.id === optimistic.id ? data.message : m)))
                if (data.oracle) setMessages((prev) => [...prev, data.oracle])
              }).catch(() => {}).finally(() => setSending(false))
            }
          }, 50)
        }
        inputRef.current?.focus()
      }
    }
    recognition.onend = () => setVoiceListening(false)
    recognition.onerror = () => setVoiceListening(false)

    recognition.start()
    recognitionRef.current = recognition
    setVoiceListening(true)
  }, [voiceListening])

  // ── Открыть чат с Mix напрямую ────────────────────────────────────────────
  const openMixChat = useCallback(() => {
    setActiveChat(CHATS[0]) // Mix — первый в списке
    setIsOpen(true)
  }, [])

  // ── Открыть панель набора номера (standalone) ─────────────────────────────
  const openStandaloneDialPad = useCallback(() => {
    setShowStandaloneDialPad(true)
  }, [])

  // ── Рендер ────────────────────────────────────────────────────────────────
  return (
    <>
      {/* Скрытый аудио-элемент для WebRTC */}
      <audio ref={remoteAudioRef} autoPlay style={{ display: 'none' }} />

      {/* ── REC-индикатор (глобальный, при активном звонке) ── */}
      <AnimatePresence>
        {isRecording && (
          <motion.div
            className="fixed flex items-center gap-2 px-3 py-1.5 rounded-full"
            style={{
              top: '16px',
              right: '16px',
              zIndex: 10000,
              background: 'rgba(13,12,11,0.92)',
              border: '1px solid rgba(239,68,68,0.5)',
              backdropFilter: 'blur(12px)',
              boxShadow: '0 0 20px rgba(239,68,68,0.3)',
            }}
            initial={{ opacity: 0, scale: 0.8, y: -10 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.8, y: -10 }}
          >
            <motion.span
              className="w-2 h-2 rounded-full"
              style={{ background: '#ef4444' }}
              animate={{ opacity: [1, 0.3, 1] }}
              transition={{ duration: 0.8, repeat: Infinity }}
            />
            <span className="text-[11px] font-orbitron tracking-wider" style={{ color: '#ef4444' }}>
              REC
            </span>
            <span className="text-[11px] font-orbitron" style={{ color: '#ffffff60' }}>
              {formatDuration(callDuration)}
            </span>
            <button
              onClick={endCall}
              className="ml-1 flex items-center justify-center w-5 h-5 rounded-full"
              style={{ background: 'rgba(239,68,68,0.2)', color: '#ef4444' }}
            >
              <PhoneOff size={10} />
            </button>
          </motion.div>
        )}
      </AnimatePresence>

      {/* ── Standalone панель набора номера ── */}
      <AnimatePresence>
        {showStandaloneDialPad && (
          <motion.div
            className="fixed inset-0 flex items-center justify-center"
            style={{ zIndex: 9997, background: 'rgba(0,0,0,0.75)', backdropFilter: 'blur(12px)' }}
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            onClick={(e) => e.target === e.currentTarget && setShowStandaloneDialPad(false)}
          >
            <motion.div
              className="relative overflow-hidden"
              style={{
                width: '360px',
                height: '520px',
                background: '#0D0C0B',
                border: '1px solid rgba(212,168,67,0.2)',
                borderRadius: '16px',
                boxShadow: '0 32px 80px rgba(0,0,0,0.9)',
              }}
              initial={{ opacity: 0, scale: 0.92, y: 20 }}
              animate={{ opacity: 1, scale: 1, y: 0 }}
              exit={{ opacity: 0, scale: 0.92, y: 20 }}
            >
              <DialPad
                onDial={(num) => startCall(num)}
                onClose={() => setShowStandaloneDialPad(false)}
              />
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* ── Веер кнопок (Chaty-style) ── */}
      <AnimatePresence>
        {fanOpen && !isOpen && (
          <>
            {/* Overlay для закрытия веера */}
            <motion.div
              className="fixed inset-0"
              style={{ zIndex: 9996 }}
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              onClick={() => setFanOpen(false)}
            />
            <FanMenu
              onOpenChat={() => { setIsOpen(true); setFanOpen(false) }}
              onOpenDialPad={() => { openStandaloneDialPad(); setFanOpen(false) }}
              onOpenMix={() => { openMixChat(); setFanOpen(false) }}
              onClose={() => setFanOpen(false)}
            />
          </>
        )}
      </AnimatePresence>

      {/* ── Плавающая кнопка (нижний правый угол) ── */}
      <motion.button
        onClick={() => {
          if (isOpen) {
            setIsOpen(false)
          } else {
            setFanOpen((v) => !v)
          }
        }}
        title="MIKS Dominion Messenger"
        className="fixed flex items-center justify-center"
        style={{
          bottom: '28px',
          right: '28px',
          zIndex: 9999,
          width: '60px',
          height: '60px',
          borderRadius: '50%',
          background: fanOpen || isOpen
            ? 'linear-gradient(135deg, #ef4444 0%, #dc2626 100%)'
            : 'linear-gradient(135deg, #7c3aed 0%, #d4a843 100%)',
          border: '2px solid rgba(212,168,67,0.5)',
          boxShadow: fanOpen || isOpen
            ? '0 0 24px rgba(239,68,68,0.5)'
            : '0 0 24px rgba(124,58,237,0.5), 0 0 48px rgba(212,168,67,0.2)',
          cursor: 'pointer',
        }}
        whileHover={{ scale: 1.1 }}
        whileTap={{ scale: 0.95 }}
        animate={fanOpen || isOpen ? {} : {
          boxShadow: [
            '0 0 24px rgba(124,58,237,0.5), 0 0 48px rgba(212,168,67,0.2)',
            '0 0 32px rgba(124,58,237,0.7), 0 0 64px rgba(212,168,67,0.35)',
            '0 0 24px rgba(124,58,237,0.5), 0 0 48px rgba(212,168,67,0.2)',
          ],
        }}
        transition={{ duration: 2.5, repeat: Infinity, ease: 'easeInOut' }}
      >
        <AnimatePresence mode="wait">
          {fanOpen || isOpen ? (
            <motion.span
              key="close"
              initial={{ rotate: -90, opacity: 0 }}
              animate={{ rotate: 0, opacity: 1 }}
              exit={{ rotate: 90, opacity: 0 }}
              transition={{ duration: 0.2 }}
            >
              <X size={24} style={{ color: '#fff' }} />
            </motion.span>
          ) : (
            <motion.span
              key="chat"
              initial={{ rotate: 90, opacity: 0 }}
              animate={{ rotate: 0, opacity: 1 }}
              exit={{ rotate: -90, opacity: 0 }}
              transition={{ duration: 0.2 }}
              style={{ fontSize: '26px' }}
            >
              💬
            </motion.span>
          )}
        </AnimatePresence>

        {/* Бейдж непрочитанных */}
        {totalUnread > 0 && !fanOpen && !isOpen && (
          <span
            className="absolute -top-1 -right-1 w-5 h-5 rounded-full flex items-center justify-center text-[10px] font-bold"
            style={{ background: '#ef4444', color: '#fff', border: '2px solid #0d0c0b' }}
          >
            {totalUnread}
          </span>
        )}
      </motion.button>

      {/* ── Модальное окно мессенджера ── */}
      <AnimatePresence>
        {isOpen && (
          <motion.div
            className="fixed inset-0 flex items-center justify-center"
            style={{ zIndex: 9998, background: 'rgba(0,0,0,0.75)', backdropFilter: 'blur(12px)' }}
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.2 }}
            onClick={(e) => e.target === e.currentTarget && setIsOpen(false)}
          >
            <motion.div
              className="relative flex overflow-hidden"
              style={{
                width: '900px',
                maxWidth: '95vw',
                height: '700px',
                maxHeight: '90vh',
                background: '#0D0C0B',
                border: '1px solid rgba(212,168,67,0.2)',
                borderRadius: '16px',
                boxShadow: '0 32px 80px rgba(0,0,0,0.9), 0 0 60px rgba(124,58,237,0.15)',
              }}
              initial={{ opacity: 0, scale: 0.92, y: 20 }}
              animate={{ opacity: 1, scale: 1, y: 0 }}
              exit={{ opacity: 0, scale: 0.92, y: 20 }}
              transition={{ duration: 0.3, ease: [0.16, 1, 0.3, 1] }}
            >
              {/* Верхняя золотая линия */}
              <div
                className="absolute top-0 left-0 right-0 h-px"
                style={{ background: 'linear-gradient(90deg, transparent, rgba(212,168,67,0.6), rgba(124,58,237,0.6), transparent)' }}
              />

              {/* ── Левая панель: список чатов ── */}
              <div
                className="flex flex-col flex-shrink-0"
                style={{
                  width: '280px',
                  borderRight: '1px solid rgba(255,255,255,0.06)',
                  background: 'rgba(0,0,0,0.3)',
                }}
              >
                {/* Заголовок */}
                <div
                  className="flex items-center justify-between px-4 py-4 flex-shrink-0"
                  style={{ borderBottom: '1px solid rgba(255,255,255,0.06)' }}
                >
                  <div>
                    <div className="text-[11px] font-orbitron tracking-[0.3em] uppercase" style={{ color: '#d4a843' }}>
                      MIKS DOMINION
                    </div>
                    <div className="text-[10px] font-montserrat mt-0.5" style={{ color: '#ffffff30' }}>
                      Мессенджер Империи
                    </div>
                  </div>
                  <button
                    onClick={() => setIsOpen(false)}
                    className="w-7 h-7 rounded-full flex items-center justify-center transition-colors"
                    style={{ background: 'rgba(255,255,255,0.06)', color: '#ffffff60' }}
                  >
                    <X size={14} />
                  </button>
                </div>

                {/* Поиск */}
                <div className="px-3 py-2 flex-shrink-0">
                  <div
                    className="flex items-center gap-2 px-3 py-2 rounded-xl"
                    style={{ background: 'rgba(255,255,255,0.04)', border: '1px solid rgba(255,255,255,0.06)' }}
                  >
                    <Search size={13} style={{ color: '#ffffff30' }} />
                    <input
                      type="text"
                      placeholder="Поиск чатов..."
                      value={searchQuery}
                      onChange={(e) => setSearchQuery(e.target.value)}
                      className="flex-1 bg-transparent text-[12px] font-montserrat outline-none"
                      style={{ color: '#E0E0E0' }}
                    />
                  </div>
                </div>

                {/* Список чатов */}
                <div className="flex-1 overflow-y-auto">
                  {filteredChats.map((chat) => {
                    const isActive = activeChat?.id === chat.id
                    return (
                      <motion.button
                        key={chat.id}
                        onClick={() => setActiveChat(chat)}
                        className="w-full flex items-center gap-3 px-3 py-3 text-left transition-colors"
                        style={{
                          background: isActive
                            ? 'rgba(212,168,67,0.08)'
                            : 'transparent',
                          borderLeft: isActive ? '2px solid #d4a843' : '2px solid transparent',
                        }}
                        whileHover={{ background: 'rgba(255,255,255,0.04)' }}
                      >
                        <Avatar chat={chat} size={40} />
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center justify-between">
                            <span
                              className="text-[13px] font-montserrat font-semibold truncate"
                              style={{ color: isActive ? '#d4a843' : '#E0E0E0' }}
                            >
                              {chat.name}
                            </span>
                            <span className="text-[10px] font-montserrat flex-shrink-0 ml-1" style={{ color: '#ffffff30' }}>
                              {chat.time}
                            </span>
                          </div>
                          <div className="flex items-center justify-between mt-0.5">
                            <span className="text-[11px] font-montserrat truncate" style={{ color: '#ffffff40' }}>
                              {chat.lastMsg}
                            </span>
                            {chat.unread > 0 && (
                              <span
                                className="ml-1 flex-shrink-0 w-4 h-4 rounded-full flex items-center justify-center text-[9px] font-bold"
                                style={{ background: '#d4a843', color: '#0d0c0b' }}
                              >
                                {chat.unread}
                              </span>
                            )}
                          </div>
                        </div>
                      </motion.button>
                    )
                  })}
                </div>

                {/* Статус SIP + Архив звонков */}
                <div
                  className="px-4 py-3 flex items-center justify-between flex-shrink-0"
                  style={{ borderTop: '1px solid rgba(255,255,255,0.06)' }}
                >
                  <div className="flex items-center gap-2">
                    <span
                      className="w-2 h-2 rounded-full"
                      style={{
                        backgroundColor: uaRegistered ? '#00ff88' : '#ef4444',
                        boxShadow: uaRegistered ? '0 0 6px #00ff8880' : 'none',
                      }}
                    />
                    <span className="text-[9px] font-orbitron tracking-wider" style={{ color: '#ffffff30' }}>
                      SIP {uaRegistered ? 'ЗАРЕГ.' : 'ОФЛАЙН'}
                    </span>
                  </div>
                  <a
                    href="/calls"
                    className="flex items-center gap-1 text-[9px] font-orbitron tracking-wider transition-colors"
                    style={{ color: '#d4a84360' }}
                    onMouseEnter={(e) => e.currentTarget.style.color = '#d4a843'}
                    onMouseLeave={(e) => e.currentTarget.style.color = '#d4a84360'}
                  >
                    <Archive size={10} />
                    АРХИВ
                  </a>
                </div>
              </div>

              {/* ── Правая панель: чат ── */}
              <div className="flex-1 flex flex-col relative overflow-hidden">
                {/* Панель набора номера (overlay) */}
                <AnimatePresence>
                  {showDialPad && (
                    <DialPad
                      onDial={(num) => startCall(num)}
                      onClose={() => setShowDialPad(false)}
                    />
                  )}
                </AnimatePresence>

                {/* Заголовок чата */}
                {activeChat && (
                  <div
                    className="flex items-center justify-between px-5 py-3 flex-shrink-0"
                    style={{ borderBottom: '1px solid rgba(255,255,255,0.06)', background: 'rgba(0,0,0,0.2)' }}
                  >
                    <div className="flex items-center gap-3">
                      <Avatar chat={activeChat} size={36} />
                      <div>
                        <div className="text-[14px] font-montserrat font-semibold" style={{ color: '#E0E0E0' }}>
                          {activeChat.name}
                        </div>
                        <div className="text-[10px] font-montserrat" style={{ color: activeChat.online ? '#00ff88' : '#ffffff30' }}>
                          {activeChat.online ? 'В сети' : 'Не в сети'}
                        </div>
                      </div>
                    </div>

                    {/* Кнопки телефонии */}
                    <div className="flex items-center gap-2">
                      {/* REC-индикатор внутри чата */}
                      {callState === 'active' && (
                        <motion.div
                          className="flex items-center gap-1.5 px-2 py-1 rounded-full"
                          style={{ background: 'rgba(239,68,68,0.12)', border: '1px solid rgba(239,68,68,0.3)' }}
                        >
                          <motion.span
                            className="w-1.5 h-1.5 rounded-full"
                            style={{ background: '#ef4444' }}
                            animate={{ opacity: [1, 0.3, 1] }}
                            transition={{ duration: 0.8, repeat: Infinity }}
                          />
                          <span className="text-[10px] font-orbitron" style={{ color: '#ef4444' }}>REC</span>
                        </motion.div>
                      )}

                      {/* Индикатор микрофона при звонке */}
                      {callState === 'active' && (
                        <motion.button
                          onClick={toggleMic}
                          className="w-8 h-8 rounded-full flex items-center justify-center"
                          style={{
                            background: micMuted ? 'rgba(239,68,68,0.2)' : 'rgba(0,255,136,0.15)',
                            border: micMuted ? '1px solid rgba(239,68,68,0.4)' : '1px solid rgba(0,255,136,0.3)',
                          }}
                          whileHover={{ scale: 1.1 }}
                          whileTap={{ scale: 0.95 }}
                          title={micMuted ? 'Включить микрофон' : 'Выключить микрофон'}
                        >
                          {micMuted
                            ? <MicOff size={14} style={{ color: '#ef4444' }} />
                            : <Mic size={14} style={{ color: '#00ff88' }} />
                          }
                        </motion.button>
                      )}

                      {/* Таймер звонка */}
                      {callState === 'active' && (
                        <motion.div
                          className="flex items-center gap-1.5 px-3 py-1 rounded-full"
                          style={{ background: 'rgba(0,200,83,0.12)', border: '1px solid rgba(0,200,83,0.3)' }}
                          animate={{ opacity: [1, 0.7, 1] }}
                          transition={{ duration: 1, repeat: Infinity }}
                        >
                          <span className="w-1.5 h-1.5 rounded-full" style={{ background: '#00c853' }} />
                          <span className="text-[11px] font-orbitron" style={{ color: '#00c853' }}>
                            {formatDuration(callDuration)}
                          </span>
                        </motion.div>
                      )}

                      {/* Кнопка "Позвонить" / "Завершить" */}
                      {callState === 'idle' && (
                        <>
                          <motion.button
                            onClick={() => setShowDialPad(true)}
                            className="flex items-center gap-2 px-3 py-1.5 rounded-xl text-[11px] font-montserrat font-semibold"
                            style={{
                              background: 'rgba(212,168,67,0.1)',
                              border: '1px solid rgba(212,168,67,0.3)',
                              color: '#d4a843',
                            }}
                            whileHover={{ background: 'rgba(212,168,67,0.2)' }}
                            whileTap={{ scale: 0.95 }}
                          >
                            <Phone size={13} />
                            Набрать
                          </motion.button>
                          {!activeChat.isAI && (
                            <motion.button
                              onClick={() => startCall()}
                              className="flex items-center gap-2 px-3 py-1.5 rounded-xl text-[11px] font-montserrat font-semibold"
                              style={{
                                background: 'rgba(0,200,83,0.12)',
                                border: '1px solid rgba(0,200,83,0.3)',
                                color: '#00c853',
                              }}
                              whileHover={{ background: 'rgba(0,200,83,0.2)' }}
                              whileTap={{ scale: 0.95 }}
                            >
                              <PhoneCall size={13} />
                              Позвонить
                            </motion.button>
                          )}
                        </>
                      )}

                      {callState === 'calling' && (
                        <motion.div
                          className="flex items-center gap-2 px-3 py-1.5 rounded-xl text-[11px] font-montserrat"
                          style={{ background: 'rgba(245,158,11,0.12)', border: '1px solid rgba(245,158,11,0.3)', color: '#f59e0b' }}
                          animate={{ opacity: [1, 0.6, 1] }}
                          transition={{ duration: 0.8, repeat: Infinity }}
                        >
                          <Phone size={13} />
                          Вызов...
                        </motion.div>
                      )}

                      {(callState === 'active' || callState === 'calling') && (
                        <motion.button
                          onClick={endCall}
                          className="flex items-center gap-2 px-3 py-1.5 rounded-xl text-[11px] font-montserrat font-semibold"
                          style={{
                            background: 'rgba(239,68,68,0.15)',
                            border: '1px solid rgba(239,68,68,0.4)',
                            color: '#ef4444',
                          }}
                          whileHover={{ background: 'rgba(239,68,68,0.25)' }}
                          whileTap={{ scale: 0.95 }}
                        >
                          <PhoneOff size={13} />
                          Завершить
                        </motion.button>
                      )}
                    </div>
                  </div>
                )}

                {/* Область сообщений */}
                <div className="flex-1 overflow-y-auto py-4">
                  {messages.map((msg) => (
                    <MessageBubble
                      key={msg.id}
                      msg={msg}
                      isMaster={
                        msg.role === 'user' &&
                        (currentUser ? msg.user_id === currentUser.id || msg.id?.toString().startsWith('opt-') || msg.id?.toString().startsWith('voice-') : msg.role === 'user')
                      }
                    />
                  ))}
                  {sending && (
                    <div className="flex justify-start px-4 mb-3">
                      <div
                        className="px-4 py-2.5 rounded-2xl text-[13px] font-montserrat"
                        style={{
                          background: 'linear-gradient(135deg, #1e1b4b, #312e81)',
                          color: '#a78bfa',
                          borderRadius: '18px 18px 18px 4px',
                          border: '1px solid #4f46e580',
                        }}
                      >
                        <motion.span
                          animate={{ opacity: [0.4, 1, 0.4] }}
                          transition={{ duration: 1.2, repeat: Infinity }}
                        >
                          Mix печатает...
                        </motion.span>
                      </div>
                    </div>
                  )}
                  <div ref={messagesEndRef} />
                </div>

                {/* Поле ввода */}
                <div
                  className="flex items-end gap-3 px-4 py-3 flex-shrink-0"
                  style={{ borderTop: '1px solid rgba(255,255,255,0.06)', background: 'rgba(0,0,0,0.2)' }}
                >
                  <div
                    className="flex-1 flex items-end rounded-2xl px-4 py-2.5"
                    style={{
                      background: 'rgba(255,255,255,0.04)',
                      border: '1px solid rgba(255,255,255,0.08)',
                      minHeight: '44px',
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
                      placeholder={activeChat?.isAI ? 'Спросите Mix...' : 'Написать сообщение...'}
                      rows={1}
                      className="w-full bg-transparent text-[13px] font-montserrat outline-none resize-none"
                      style={{
                        color: '#E0E0E0',
                        maxHeight: '120px',
                        lineHeight: '1.5',
                      }}
                    />
                  </div>

                  {/* Кнопка микрофона (Web Speech API) */}
                  <motion.button
                    onClick={toggleVoice}
                    className="w-10 h-10 rounded-full flex items-center justify-center flex-shrink-0"
                    style={{
                      background: voiceListening
                        ? 'linear-gradient(135deg, #ef4444, #dc2626)'
                        : 'rgba(255,255,255,0.06)',
                      border: voiceListening
                        ? '1px solid rgba(239,68,68,0.5)'
                        : '1px solid rgba(255,255,255,0.08)',
                      boxShadow: voiceListening ? '0 0 16px rgba(239,68,68,0.4)' : 'none',
                    }}
                    whileHover={{ scale: 1.08 }}
                    whileTap={{ scale: 0.95 }}
                    title={voiceListening ? 'Остановить запись' : 'Голосовой ввод'}
                  >
                    {voiceListening ? (
                      <motion.span
                        animate={{ opacity: [1, 0.4, 1] }}
                        transition={{ duration: 0.6, repeat: Infinity }}
                      >
                        <MicOff size={16} style={{ color: '#fff' }} />
                      </motion.span>
                    ) : (
                      <Mic size={16} style={{ color: '#ffffff50' }} />
                    )}
                  </motion.button>

                  {/* Кнопка отправки */}
                  <motion.button
                    onClick={sendMessage}
                    disabled={!inputText.trim() || sending}
                    className="w-10 h-10 rounded-full flex items-center justify-center flex-shrink-0"
                    style={{
                      background: inputText.trim()
                        ? 'linear-gradient(135deg, #d4a843, #b8860b)'
                        : 'rgba(255,255,255,0.06)',
                      border: inputText.trim()
                        ? '1px solid rgba(212,168,67,0.4)'
                        : '1px solid rgba(255,255,255,0.08)',
                      cursor: inputText.trim() ? 'pointer' : 'not-allowed',
                    }}
                    whileHover={inputText.trim() ? { scale: 1.08 } : {}}
                    whileTap={inputText.trim() ? { scale: 0.95 } : {}}
                  >
                    <Send size={16} style={{ color: inputText.trim() ? '#0d0c0b' : '#ffffff30' }} />
                  </motion.button>
                </div>
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </>
  )
}

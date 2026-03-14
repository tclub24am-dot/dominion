import React, { useState, useEffect, useRef, useCallback, useMemo } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import {
  Phone, PhoneIncoming, PhoneOutgoing, PhoneMissed,
  Play, Pause, Download, Search,
  Clock, Volume2, VolumeX, Mic, SkipBack, SkipForward,
  ArrowLeft
} from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import api from '../api/client'
import TopBar from '../components/dashboard/TopBar'

/**
 * S-GLOBAL DOMINION — Архив Звонков v1.0
 * =========================================
 * Страница для Мастера: просмотр и прослушивание записей разговоров
 * Фильтрация по дате, номеру, статусу
 * Встроенный аудиоплеер с прогресс-баром
 */

const CALL_STATUSES = {
  answered:    { label: 'Принят',      color: '#00c853', icon: PhoneIncoming, bg: 'rgba(0,200,83,0.12)',    border: 'rgba(0,200,83,0.3)' },
  outgoing:    { label: 'Исходящий',   color: '#3b82f6', icon: PhoneOutgoing, bg: 'rgba(59,130,246,0.12)', border: 'rgba(59,130,246,0.3)' },
  missed:      { label: 'Пропущен',    color: '#ef4444', icon: PhoneMissed,   bg: 'rgba(239,68,68,0.12)',  border: 'rgba(239,68,68,0.3)' },
  call_missed: { label: 'Пропущен',    color: '#ef4444', icon: PhoneMissed,   bg: 'rgba(239,68,68,0.12)',  border: 'rgba(239,68,68,0.3)' },
  call_ended:  { label: 'Завершён',    color: '#00c853', icon: PhoneIncoming, bg: 'rgba(0,200,83,0.12)',   border: 'rgba(0,200,83,0.3)' },
  new_call:    { label: 'Входящий',    color: '#3b82f6', icon: PhoneIncoming, bg: 'rgba(59,130,246,0.12)', border: 'rgba(59,130,246,0.3)' },
  unknown:     { label: 'Неизвестно',  color: '#ffffff40', icon: Phone,       bg: 'rgba(255,255,255,0.06)', border: 'rgba(255,255,255,0.1)' },
}

function formatDuration(seconds) {
  if (!seconds) return '—'
  const m = Math.floor(seconds / 60)
  const s = seconds % 60
  return `${m}:${String(s).padStart(2, '0')}`
}

function formatDate(dateStr) {
  if (!dateStr) return '—'
  try {
    return new Date(dateStr).toLocaleString('ru-RU', {
      day: '2-digit', month: '2-digit', year: 'numeric',
      hour: '2-digit', minute: '2-digit',
    })
  } catch {
    return dateStr
  }
}

// ─── Аудиоплеер ──────────────────────────────────────────────────────────────

function AudioPlayer({ src, callId, onClose }) {
  const audioRef = useRef(null)
  const [playing, setPlaying] = useState(false)
  const [currentTime, setCurrentTime] = useState(0)
  const [duration, setDuration] = useState(0)
  const [volume, setVolume] = useState(1)
  const [muted, setMuted] = useState(false)

  useEffect(() => {
    const audio = audioRef.current
    if (!audio) return
    const onTimeUpdate = () => setCurrentTime(audio.currentTime)
    const onDurationChange = () => setDuration(audio.duration || 0)
    const onEnded = () => setPlaying(false)
    audio.addEventListener('timeupdate', onTimeUpdate)
    audio.addEventListener('durationchange', onDurationChange)
    audio.addEventListener('ended', onEnded)
    return () => {
      audio.removeEventListener('timeupdate', onTimeUpdate)
      audio.removeEventListener('durationchange', onDurationChange)
      audio.removeEventListener('ended', onEnded)
    }
  }, [])

  const togglePlay = () => {
    const audio = audioRef.current
    if (!audio) return
    if (playing) { audio.pause(); setPlaying(false) }
    else { audio.play(); setPlaying(true) }
  }

  const seek = (e) => {
    const audio = audioRef.current
    if (!audio || !duration) return
    const rect = e.currentTarget.getBoundingClientRect()
    const ratio = (e.clientX - rect.left) / rect.width
    audio.currentTime = ratio * duration
  }

  const skip = (delta) => {
    const audio = audioRef.current
    if (!audio) return
    audio.currentTime = Math.max(0, Math.min(duration, audio.currentTime + delta))
  }

  const toggleMute = () => {
    const audio = audioRef.current
    if (!audio) return
    audio.muted = !muted
    setMuted(!muted)
  }

  const progress = duration > 0 ? (currentTime / duration) * 100 : 0

  return (
    <motion.div
      className="fixed inset-0 flex items-end justify-center pb-8"
      style={{ zIndex: 10001, background: 'rgba(0,0,0,0.6)', backdropFilter: 'blur(8px)' }}
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      onClick={(e) => e.target === e.currentTarget && onClose()}
    >
      <motion.div
        className="w-full max-w-lg mx-4 rounded-2xl overflow-hidden"
        style={{
          background: '#0D0C0B',
          border: '1px solid rgba(212,168,67,0.3)',
          boxShadow: '0 -8px 40px rgba(0,0,0,0.8), 0 0 40px rgba(212,168,67,0.1)',
        }}
        initial={{ y: 80, opacity: 0 }}
        animate={{ y: 0, opacity: 1 }}
        exit={{ y: 80, opacity: 0 }}
        transition={{ type: 'spring', damping: 25, stiffness: 300 }}
      >
        {/* Золотая линия */}
        <div className="h-px" style={{ background: 'linear-gradient(90deg, transparent, #d4a843, transparent)' }} />

        <div className="p-6">
          {/* Заголовок */}
          <div className="flex items-center justify-between mb-4">
            <div>
              <div className="text-[10px] font-orbitron tracking-[0.3em] uppercase" style={{ color: '#d4a843' }}>
                ВОСПРОИЗВЕДЕНИЕ ЗАПИСИ
              </div>
              <div className="text-[12px] font-montserrat mt-1" style={{ color: '#ffffff60' }}>
                Звонок #{callId}
              </div>
            </div>
            <button
              onClick={onClose}
              className="text-[11px] font-montserrat px-3 py-1.5 rounded-lg"
              style={{ background: 'rgba(255,255,255,0.06)', color: '#ffffff40', border: '1px solid rgba(255,255,255,0.08)' }}
            >
              Закрыть
            </button>
          </div>

          {/* Прогресс-бар */}
          <div
            className="w-full h-2 rounded-full mb-3 cursor-pointer relative overflow-hidden"
            style={{ background: 'rgba(255,255,255,0.08)' }}
            onClick={seek}
          >
            <motion.div
              className="h-full rounded-full"
              style={{
                width: `${progress}%`,
                background: 'linear-gradient(90deg, #7c3aed, #d4a843)',
              }}
            />
          </div>

          {/* Время */}
          <div className="flex justify-between mb-4">
            <span className="text-[11px] font-orbitron" style={{ color: '#ffffff40' }}>
              {formatDuration(Math.floor(currentTime))}
            </span>
            <span className="text-[11px] font-orbitron" style={{ color: '#ffffff40' }}>
              {formatDuration(Math.floor(duration))}
            </span>
          </div>

          {/* Управление */}
          <div className="flex items-center justify-center gap-4">
            <motion.button
              onClick={() => skip(-10)}
              className="w-10 h-10 rounded-full flex items-center justify-center"
              style={{ background: 'rgba(255,255,255,0.06)', color: '#ffffff60' }}
              whileHover={{ scale: 1.1 }}
              whileTap={{ scale: 0.9 }}
            >
              <SkipBack size={16} />
            </motion.button>

            <motion.button
              onClick={togglePlay}
              className="w-14 h-14 rounded-full flex items-center justify-center"
              style={{
                background: 'linear-gradient(135deg, #d4a843, #b8860b)',
                boxShadow: '0 0 20px rgba(212,168,67,0.3)',
              }}
              whileHover={{ scale: 1.08 }}
              whileTap={{ scale: 0.95 }}
            >
              {playing
                ? <Pause size={22} style={{ color: '#0d0c0b' }} />
                : <Play size={22} style={{ color: '#0d0c0b', marginLeft: '2px' }} />
              }
            </motion.button>

            <motion.button
              onClick={() => skip(10)}
              className="w-10 h-10 rounded-full flex items-center justify-center"
              style={{ background: 'rgba(255,255,255,0.06)', color: '#ffffff60' }}
              whileHover={{ scale: 1.1 }}
              whileTap={{ scale: 0.9 }}
            >
              <SkipForward size={16} />
            </motion.button>

            <motion.button
              onClick={toggleMute}
              className="w-10 h-10 rounded-full flex items-center justify-center"
              style={{
                background: muted ? 'rgba(239,68,68,0.15)' : 'rgba(255,255,255,0.06)',
                color: muted ? '#ef4444' : '#ffffff60',
              }}
              whileHover={{ scale: 1.1 }}
              whileTap={{ scale: 0.9 }}
            >
              {muted ? <VolumeX size={16} /> : <Volume2 size={16} />}
            </motion.button>

            {src && (
              <motion.a
                href={src}
                download={`call_${callId}.wav`}
                className="w-10 h-10 rounded-full flex items-center justify-center"
                style={{ background: 'rgba(255,255,255,0.06)', color: '#ffffff60' }}
                whileHover={{ scale: 1.1 }}
                whileTap={{ scale: 0.9 }}
              >
                <Download size={16} />
              </motion.a>
            )}
          </div>
        </div>

        <audio ref={audioRef} src={src} preload="metadata" />
      </motion.div>
    </motion.div>
  )
}

// ─── Строка звонка ────────────────────────────────────────────────────────────

function CallRow({ call, onPlay }) {
  // API возвращает: phone (caller), callee_phone, call_status, timestamp, duration, recording_url, driver_name, ai_rating
  const rawStatus = call.call_status || call.status || 'unknown'
  const status = CALL_STATUSES[rawStatus] || CALL_STATUSES.unknown
  const StatusIcon = status.icon
  const callerPhone = call.phone || call.caller || '—'
  const calleePhone = call.callee_phone || call.callee || '—'
  const callTime = call.timestamp || call.created_at

  return (
    <motion.div
      className="flex items-center gap-4 px-5 py-4 rounded-xl transition-colors cursor-default"
      style={{
        background: 'rgba(255,255,255,0.02)',
        border: '1px solid rgba(255,255,255,0.05)',
      }}
      whileHover={{ background: 'rgba(255,255,255,0.04)', borderColor: 'rgba(212,168,67,0.15)' }}
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
    >
      {/* Статус */}
      <div
        className="w-10 h-10 rounded-full flex items-center justify-center flex-shrink-0"
        style={{ background: status.bg, border: `1px solid ${status.border}` }}
      >
        <StatusIcon size={16} style={{ color: status.color }} />
      </div>

      {/* Номера + имя водителя */}
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 flex-wrap">
          <span className="text-[13px] font-montserrat font-semibold" style={{ color: '#E0E0E0' }}>
            {callerPhone}
          </span>
          <span className="text-[11px] font-montserrat" style={{ color: '#ffffff30' }}>→</span>
          <span className="text-[13px] font-montserrat" style={{ color: '#ffffff60' }}>
            {calleePhone}
          </span>
          {call.driver_name && (
            <span className="text-[11px] font-montserrat px-2 py-0.5 rounded-full" style={{ background: 'rgba(212,168,67,0.1)', color: '#d4a843', border: '1px solid rgba(212,168,67,0.2)' }}>
              {call.driver_name}
            </span>
          )}
        </div>
        <div className="flex items-center gap-3 mt-0.5">
          <span
            className="text-[10px] font-orbitron tracking-wider px-2 py-0.5 rounded-full"
            style={{ background: status.bg, color: status.color, border: `1px solid ${status.border}` }}
          >
            {status.label}
          </span>
          {call.duration > 0 && (
            <span className="text-[11px] font-montserrat flex items-center gap-1" style={{ color: '#ffffff40' }}>
              <Clock size={10} />
              {formatDuration(call.duration)}
            </span>
          )}
          {call.ai_rating && (
            <span className="text-[11px] font-montserrat" style={{ color: '#a78bfa' }}>
              ИИ: {call.ai_rating}/10
            </span>
          )}
        </div>
      </div>

      {/* Дата */}
      <div className="text-right flex-shrink-0">
        <div className="text-[11px] font-montserrat" style={{ color: '#ffffff40' }}>
          {formatDate(callTime)}
        </div>
      </div>

      {/* Кнопка воспроизведения */}
      {call.recording_url ? (
        <motion.button
          onClick={() => onPlay(call)}
          className="w-9 h-9 rounded-full flex items-center justify-center flex-shrink-0"
          style={{
            background: 'linear-gradient(135deg, #7c3aed, #4f46e5)',
            border: '1px solid rgba(124,58,237,0.4)',
            boxShadow: '0 0 12px rgba(124,58,237,0.2)',
          }}
          whileHover={{ scale: 1.1, boxShadow: '0 0 20px rgba(124,58,237,0.4)' }}
          whileTap={{ scale: 0.9 }}
          title="Прослушать запись"
        >
          <Play size={14} style={{ color: '#fff', marginLeft: '1px' }} />
        </motion.button>
      ) : (
        <div
          className="w-9 h-9 rounded-full flex items-center justify-center flex-shrink-0"
          style={{ background: 'rgba(255,255,255,0.04)', border: '1px solid rgba(255,255,255,0.06)' }}
          title="Запись недоступна"
        >
          <Mic size={14} style={{ color: '#ffffff20' }} />
        </div>
      )}
    </motion.div>
  )
}

// ─── Главная страница ─────────────────────────────────────────────────────────

export default function CallArchivePage({ onLogout }) {
  const navigate = useNavigate()
  const [calls, setCalls] = useState([])
  const [loading, setLoading] = useState(true)
  const [searchQuery, setSearchQuery] = useState('')
  const [statusFilter, setStatusFilter] = useState('all')
  const [playingCall, setPlayingCall] = useState(null)
  const [stats, setStats] = useState({ total: 0, answered: 0, missed: 0, total_duration: 0 })

  const LIMIT = 500 // API поддерживает до 500

  const loadCalls = useCallback(async () => {
    setLoading(true)
    try {
      const { data } = await api.get('/api/v1/telephony/calls', { params: { limit: LIMIT } })
      const allCalls = data.calls || data.items || []
      setCalls(allCalls)

      // Считаем статистику на клиенте
      setStats({
        total: data.total || allCalls.length,
        answered: allCalls.filter((c) => ['answered', 'call_ended'].includes(c.call_status || c.status)).length,
        missed: allCalls.filter((c) => ['missed', 'call_missed'].includes(c.call_status || c.status)).length,
        total_duration: allCalls.reduce((s, c) => s + (c.duration || 0), 0),
      })
    } catch {
      setCalls([])
      setStats({ total: 0, answered: 0, missed: 0, total_duration: 0 })
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    loadCalls()
  }, [loadCalls])

  // Клиентская фильтрация
  const filteredCalls = useMemo(() => {
    return calls.filter((c) => {
      const rawStatus = c.call_status || c.status || ''
      const matchStatus = statusFilter === 'all' || rawStatus === statusFilter
      const q = searchQuery.trim().toLowerCase()
      const matchSearch = !q || (c.phone || '').includes(q) || (c.callee_phone || '').includes(q) || (c.driver_name || '').toLowerCase().includes(q)
      return matchStatus && matchSearch
    })
  }, [calls, statusFilter, searchQuery])

  return (
    <div className="min-h-screen" style={{ background: '#0D0C0B' }}>
      <TopBar onLogout={onLogout} />

      <main className="relative z-10 px-4 md:px-6 lg:px-8 py-6 max-w-[1200px] mx-auto">

        {/* Заголовок */}
        <motion.div
          className="mb-8"
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5 }}
        >
          <div className="flex items-center gap-4 mb-4">
            <motion.button
              onClick={() => navigate('/')}
              className="flex items-center gap-2 text-[12px] font-montserrat"
              style={{ color: '#ffffff40' }}
              whileHover={{ color: '#d4a843' }}
            >
              <ArrowLeft size={16} />
              Назад
            </motion.button>
          </div>

          <div className="flex items-center gap-3 mb-2">
            <div
              className="w-10 h-10 rounded-xl flex items-center justify-center"
              style={{ background: 'linear-gradient(135deg, #7c3aed, #4f46e5)', border: '1px solid rgba(124,58,237,0.4)' }}
            >
              <Phone size={18} style={{ color: '#fff' }} />
            </div>
            <div>
              <h1 className="text-[20px] font-orbitron font-bold" style={{ color: '#E0E0E0' }}>
                АРХИВ ЗВОНКОВ
              </h1>
              <p className="text-[11px] font-montserrat" style={{ color: '#ffffff40' }}>
                S-GLOBAL DOMINION · Телефония Эфир
              </p>
            </div>
          </div>
        </motion.div>

        {/* Статистика */}
        <motion.div
          className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6"
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.1, duration: 0.5 }}
        >
          {[
            { label: 'Всего звонков', value: stats.total, color: '#d4a843' },
            { label: 'Принято', value: stats.answered, color: '#00c853' },
            { label: 'Пропущено', value: stats.missed, color: '#ef4444' },
            { label: 'Общее время', value: formatDuration(stats.total_duration), color: '#7c3aed' },
          ].map((stat) => (
            <div
              key={stat.label}
              className="rounded-xl px-4 py-3"
              style={{
                background: 'rgba(255,255,255,0.03)',
                border: '1px solid rgba(255,255,255,0.06)',
              }}
            >
              <div className="text-[10px] font-orbitron tracking-wider uppercase mb-1" style={{ color: '#ffffff40' }}>
                {stat.label}
              </div>
              <div className="text-[22px] font-orbitron font-bold" style={{ color: stat.color }}>
                {stat.value}
              </div>
            </div>
          ))}
        </motion.div>

        {/* Фильтры */}
        <motion.div
          className="flex flex-wrap items-center gap-3 mb-5"
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.2, duration: 0.5 }}
        >
          {/* Поиск */}
          <div
            className="flex items-center gap-2 px-3 py-2 rounded-xl flex-1 min-w-[200px]"
            style={{ background: 'rgba(255,255,255,0.04)', border: '1px solid rgba(255,255,255,0.08)' }}
          >
            <Search size={14} style={{ color: '#ffffff30' }} />
            <input
              type="text"
              placeholder="Поиск по номеру..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="flex-1 bg-transparent text-[13px] font-montserrat outline-none"
              style={{ color: '#E0E0E0' }}
            />
          </div>

          {/* Фильтр по статусу */}
          {['all', 'answered', 'missed', 'outgoing'].map((s) => {
            const labels = { all: 'Все', answered: 'Принятые', missed: 'Пропущенные', outgoing: 'Исходящие' }
            const isActive = statusFilter === s
            return (
              <motion.button
                key={s}
                onClick={() => setStatusFilter(s)}
                className="px-3 py-2 rounded-xl text-[11px] font-montserrat font-semibold"
                style={{
                  background: isActive ? 'rgba(212,168,67,0.15)' : 'rgba(255,255,255,0.04)',
                  border: isActive ? '1px solid rgba(212,168,67,0.4)' : '1px solid rgba(255,255,255,0.08)',
                  color: isActive ? '#d4a843' : '#ffffff60',
                }}
                whileHover={{ background: 'rgba(212,168,67,0.1)' }}
                whileTap={{ scale: 0.95 }}
              >
                {labels[s]}
              </motion.button>
            )
          })}
        </motion.div>

        {/* Список звонков */}
        <motion.div
          className="flex flex-col gap-2"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ delay: 0.3, duration: 0.5 }}
        >
          {loading && calls.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-20 gap-4">
              <motion.div
                className="w-10 h-10 rounded-full border-2"
                style={{ borderColor: 'rgba(212,168,67,0.2)', borderTopColor: '#d4a843' }}
                animate={{ rotate: 360 }}
                transition={{ duration: 1, repeat: Infinity, ease: 'linear' }}
              />
              <span className="text-[12px] font-montserrat" style={{ color: '#ffffff30' }}>
                Загрузка архива...
              </span>
            </div>
          ) : calls.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-20 gap-3">
              <div
                className="w-16 h-16 rounded-full flex items-center justify-center"
                style={{ background: 'rgba(255,255,255,0.04)', border: '1px solid rgba(255,255,255,0.08)' }}
              >
                <Phone size={28} style={{ color: '#ffffff20' }} />
              </div>
              <span className="text-[14px] font-montserrat font-semibold" style={{ color: '#ffffff40' }}>
                Звонков не найдено
              </span>
              <span className="text-[12px] font-montserrat" style={{ color: '#ffffff20' }}>
                Архив пуст или нет записей по фильтру
              </span>
            </div>
          ) : (
            <>
              {filteredCalls.length === 0 ? (
                <div className="flex flex-col items-center justify-center py-12 gap-3">
                  <span className="text-[13px] font-montserrat" style={{ color: '#ffffff30' }}>
                    Нет звонков по выбранному фильтру
                  </span>
                </div>
              ) : (
                filteredCalls.map((call, i) => (
                  <CallRow
                    key={call.id || i}
                    call={call}
                    onPlay={(c) => setPlayingCall(c)}
                  />
                ))
              )}
            </>
          )}
        </motion.div>
      </main>

      {/* Аудиоплеер */}
      <AnimatePresence>
        {playingCall && (
          <AudioPlayer
            src={playingCall.recording_url}
            callId={playingCall.id}
            onClose={() => setPlayingCall(null)}
          />
        )}
      </AnimatePresence>
    </div>
  )
}

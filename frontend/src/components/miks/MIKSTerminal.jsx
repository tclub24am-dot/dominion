import React, { useEffect, useMemo, useState } from 'react'
import { Phone, Radio, Sparkles, MessageSquareText, ShieldCheck } from 'lucide-react'
import JsSIP from 'jssip'

import api from '../../api/client'

const FALLBACK_BOOTSTRAP = {
  user: {
    full_name: 'Оператор MIKS',
    role: 'manager',
    park_name: 'PRO',
  },
  matrix: {
    homeserver_url: 'http://synapse:8008',
    server_name: 'matrix.dominion.local',
    room_id: null,
    ready: false,
  },
  webrtc: {
    provider: 'jssip',
    wss_url: 'wss://89.169.39.111:8089/ws',
    sip_uri: 'sip:system@89.169.39.111',
    realm: '89.169.39.111',
    ice_servers: [],
  },
}

export default function MIKSTerminal() {
  const [bootstrap, setBootstrap] = useState(FALLBACK_BOOTSTRAP)
  const [message, setMessage] = useState('')
  const [tagging, setTagging] = useState(null)
  const [loading, setLoading] = useState(true)
  const [taggingState, setTaggingState] = useState('idle')

  useEffect(() => {
    let mounted = true
    api.get('/api/v1/miks/bootstrap')
      .then(({ data }) => {
        if (mounted) {
          setBootstrap(data)
        }
      })
      .catch(() => {
        if (mounted) {
          setBootstrap(FALLBACK_BOOTSTRAP)
        }
      })
      .finally(() => {
        if (mounted) {
          setLoading(false)
        }
      })

    return () => {
      mounted = false
    }
  }, [])

  const uaPreview = useMemo(() => {
    try {
      const socket = new JsSIP.WebSocketInterface(bootstrap.webrtc.wss_url)
      return {
        socketUrl: socket.url,
        sipUri: bootstrap.webrtc.sip_uri,
        realm: bootstrap.webrtc.realm,
      }
    } catch {
      return {
        socketUrl: bootstrap.webrtc.wss_url,
        sipUri: bootstrap.webrtc.sip_uri,
        realm: bootstrap.webrtc.realm,
      }
    }
  }, [bootstrap])

  const submitForTagging = async (event) => {
    event.preventDefault()
    const trimmed = message.trim()
    if (!trimmed) return

    setTaggingState('loading')
    try {
      const { data } = await api.post('/api/v1/miks/tag-message', { message: trimmed })
      setTagging(data.tagging)
      setTaggingState('done')
    } catch {
      setTagging({ tags: ['miks', 'offline'], summary: 'AI Link временно недоступен' })
      setTaggingState('error')
    }
  }

  return (
    <section className="mt-8 max-w-[1440px] mx-auto rounded-3xl border border-white/[0.08] bg-[#0d1320]/85 p-6 text-[#f5f5f0] shadow-[0_24px_80px_rgba(0,0,0,0.45)] backdrop-blur-xl">
      <div className="flex flex-col gap-6 lg:flex-row lg:items-start lg:justify-between">
        <div className="max-w-2xl">
          <p className="text-[14px] uppercase tracking-[0.38em] text-cyan-300/80">MIKS Web-Terminal</p>
          <h3 className="mt-3 text-[20px] font-bold text-[#f5f5f0]">Связь DOMINION · Matrix + WebRTC + AI Tagging</h3>
          <p className="mt-3 text-[15px] leading-7 text-white/70">
            Веб-терминал под внутренний Dashboard: защищённый чат через Matrix Synapse,
            голосовой мост через Asterisk WSS и оперативная AI-классификация сообщений через Ollama.
          </p>
        </div>

        <div className="grid min-w-[280px] gap-3 rounded-2xl border border-cyan-400/15 bg-black/20 p-4 text-sm text-white/75">
          <StatusRow icon={ShieldCheck} label="Оператор" value={bootstrap.user.full_name} />
          <StatusRow icon={MessageSquareText} label="Matrix" value={bootstrap.matrix.ready ? 'READY' : 'BOOTSTRAP'} />
          <StatusRow icon={Radio} label="WSS" value={bootstrap.webrtc.wss_url} />
          <StatusRow icon={Phone} label="SIP URI" value={bootstrap.webrtc.sip_uri} />
        </div>
      </div>

      <div className="mt-6 grid gap-5 xl:grid-cols-[1.3fr_0.9fr_0.8fr]">
        <article className="rounded-2xl border border-white/[0.06] bg-white/[0.03] p-5">
          <div className="flex items-center gap-3">
            <MessageSquareText className="h-5 w-5 text-cyan-300" />
            <h4 className="text-[20px] font-bold">Matrix Core</h4>
          </div>
          <div className="mt-4 space-y-3 text-[15px] text-white/70">
            <p>Homeserver: <span className="text-white">{bootstrap.matrix.homeserver_url}</span></p>
            <p>Server name: <span className="text-white">{bootstrap.matrix.server_name}</span></p>
            <p>Room: <span className="text-white">{bootstrap.matrix.room_id || 'room pending'}</span></p>
            <p>Статус API: <span className="text-white">{loading ? 'loading' : 'synced'}</span></p>
          </div>
        </article>

        <article className="rounded-2xl border border-white/[0.06] bg-white/[0.03] p-5">
          <div className="flex items-center gap-3">
            <Phone className="h-5 w-5 text-emerald-300" />
            <h4 className="text-[20px] font-bold">WebRTC Bridge</h4>
          </div>
          <div className="mt-4 space-y-3 text-[15px] text-white/70">
            <p>Provider: <span className="text-white">{bootstrap.webrtc.provider}</span></p>
            <p>Socket: <span className="text-white break-all">{uaPreview.socketUrl}</span></p>
            <p>Realm: <span className="text-white">{uaPreview.realm}</span></p>
            <p>Готовность: <span className="text-white">WSS transport staged</span></p>
          </div>
        </article>

        <article className="rounded-2xl border border-white/[0.06] bg-white/[0.03] p-5">
          <div className="flex items-center gap-3">
            <Sparkles className="h-5 w-5 text-violet-300" />
            <h4 className="text-[20px] font-bold">AI Link</h4>
          </div>
          <form className="mt-4 space-y-3" onSubmit={submitForTagging}>
            <textarea
              value={message}
              onChange={(event) => setMessage(event.target.value)}
              placeholder="Введите текст Matrix-сообщения для автотегирования"
              className="min-h-[120px] w-full rounded-2xl border border-white/10 bg-[#060b14] px-4 py-3 text-[15px] text-[#f5f5f0] outline-none placeholder:text-white/25"
            />
            <button
              type="submit"
              className="w-full rounded-2xl border border-violet-400/30 bg-violet-500/15 px-4 py-3 text-[14px] font-bold uppercase tracking-[0.22em] text-violet-200"
            >
              {taggingState === 'loading' ? 'AI TAGGING...' : 'Отправить в Ollama'}
            </button>
          </form>
          <div className="mt-4 rounded-2xl border border-white/5 bg-black/20 p-4 text-[14px] text-white/70">
            <p className="font-bold text-white">{tagging?.summary || 'Ожидание AI-анализа'}</p>
            <div className="mt-3 flex flex-wrap gap-2">
              {(tagging?.tags || ['matrix', 'voice', 'dominion']).map((tag) => (
                <span key={tag} className="rounded-full border border-cyan-400/20 bg-cyan-400/10 px-3 py-1 text-[12px] uppercase tracking-[0.16em] text-cyan-100">
                  {tag}
                </span>
              ))}
            </div>
          </div>
        </article>
      </div>
    </section>
  )
}

function StatusRow({ icon: Icon, label, value }) {
  return (
    <div className="grid grid-cols-[20px_88px_1fr] items-center gap-3">
      <Icon className="h-4 w-4 text-cyan-300" />
      <span className="text-white/45">{label}</span>
      <span className="truncate text-right text-white">{value}</span>
    </div>
  )
}

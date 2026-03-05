(() => {
  const chatBody = document.getElementById("chatBody");
  const chatInput = document.getElementById("chatInput");
  const chatSend = document.getElementById("chatSend");
  const channel = "ОБЩАЯ";

  if (!chatBody || !chatInput || !chatSend) return;

  function appendBubble(text, isAi = false) {
    const bubble = document.createElement("div");
    bubble.className = `bubble${isAi ? " ai" : ""}`;
    if (isAi) {
      const title = document.createElement("div");
      title.className = "ai-title";
      title.textContent = "Oracle AI";
      bubble.appendChild(title);
    }
    bubble.appendChild(document.createTextNode(text));
    chatBody.appendChild(bubble);
    chatBody.scrollTop = chatBody.scrollHeight;
  }

  async function sendMessage() {
    const text = chatInput.value.trim();
    if (!text) return;
    appendBubble(`Мастер: ${text}`);
    chatInput.value = "";
    try {
      await fetch("/api/v1/messenger/messages", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({ channel, content: text }),
      });
    } catch (e) {
      appendBubble("Система: нет связи с сервером.");
    }
  }

  chatSend.addEventListener("click", sendMessage);
  chatInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  });

  const ws = new WebSocket(
    `${location.protocol === "https:" ? "wss" : "ws"}://${location.host}/api/v1/ws/messenger?channel=${encodeURIComponent(channel)}`
  );
  ws.onmessage = (event) => {
    try {
      const payload = JSON.parse(event.data);
      if (payload?.type === "message" && payload.message?.content) {
        const isAi = payload.message.role === "assistant" || payload.message.author === "Oracle AI";
        appendBubble(payload.message.content, isAi);
      }
    } catch {}
  };
})();

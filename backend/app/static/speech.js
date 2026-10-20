(() => {
  const apiHeaders = () => {
    const key = localStorage.getItem("b2_api_key") || localStorage.getItem("memory_api_key");
    return key ? { "X-API-Key": key } : {};
  };

  async function transcribeBlob(blob) {
    const form = new FormData();
    form.append("file", blob, "audio.webm");
    const res = await fetch("/api/v1/speech/transcribe", {
      method: "POST",
      headers: apiHeaders(),
      body: form,
    });
    if (!res.ok) {
      const err = await res.text();
      throw new Error(err || "Transcription failed");
    }
    const data = await res.json();
    return data.text || "";
  }

  function bindMicButtons() {
    document.querySelectorAll(".mic-btn[data-speech-target]").forEach((btn) => {
      if (btn.dataset.bound) return;
      btn.dataset.bound = "1";

      let mediaRecorder = null;
      let chunks = [];

      btn.addEventListener("click", async () => {
        const targetId = btn.getAttribute("data-speech-target");
        const field = document.getElementById(targetId);
        if (!field) return;

        if (mediaRecorder && mediaRecorder.state === "recording") {
          mediaRecorder.stop();
          return;
        }

        try {
          const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
          chunks = [];
          mediaRecorder = new MediaRecorder(stream);
          mediaRecorder.ondataavailable = (e) => {
            if (e.data.size > 0) chunks.push(e.data);
          };
          mediaRecorder.onstop = async () => {
            btn.classList.remove("recording");
            btn.textContent = "Mic";
            stream.getTracks().forEach((t) => t.stop());
            const blob = new Blob(chunks, { type: "audio/webm" });
            btn.disabled = true;
            btn.textContent = "…";
            try {
              const text = await transcribeBlob(blob);
              const sep = field.value && !field.value.endsWith(" ") ? " " : "";
              field.value = (field.value || "") + sep + text;
              field.dispatchEvent(new Event("input", { bubbles: true }));
            } catch (err) {
              alert(err.message || String(err));
            } finally {
              btn.disabled = false;
              btn.textContent = "Mic";
            }
          };
          mediaRecorder.start();
          btn.classList.add("recording");
          btn.textContent = "Stop";
        } catch (err) {
          alert("Microphone permission needed: " + (err.message || err));
        }
      });
    });
  }

  async function speakText(text) {
    const form = new FormData();
    form.append("text", text);
    const res = await fetch("/api/v1/speech/speak", {
      method: "POST",
      headers: apiHeaders(),
      body: form,
    });
    if (!res.ok) {
      const err = await res.text();
      throw new Error(err || "TTS failed");
    }
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const audio = new Audio(url);
    audio.play();
  }

  function bindSpeakAnswer() {
    const btn = document.getElementById("speak-answer");
    const textEl = document.getElementById("answer-text");
    if (!btn || !textEl || btn.dataset.bound) return;
    btn.dataset.bound = "1";
    btn.addEventListener("click", async () => {
      btn.disabled = true;
      try {
        await speakText(textEl.textContent || "");
      } catch (err) {
        alert(err.message || String(err));
      } finally {
        btn.disabled = false;
      }
    });
  }

  document.addEventListener("DOMContentLoaded", () => {
    bindMicButtons();
    bindSpeakAnswer();
  });
})();

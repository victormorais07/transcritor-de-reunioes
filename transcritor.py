"""
Transcritor de Reuniões — uso pessoal.

Clique em INICIAR: grava o seu microfone ("Eu") e o som do computador
("Participantes" — quem fala na chamada do Teams/Meet/Zoom) e transcreve
localmente com Whisper. Clique em PARAR: a sessão termina e o arquivo .md
é finalizado. Iniciar de novo cria um arquivo novo.

Os arquivos ficam em "Transcricoes", ao lado do programa.
"""

import difflib
import os
import queue
import re
import sys
import threading
import time
import tkinter as tk
from datetime import datetime
from tkinter import messagebox, ttk

os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")

import numpy as np
import pyaudiowpatch as pyaudio

# ----------------------------------------------------------------- config ---
MODELO = "small"          # tiny | base | small | medium  (maior = melhor e mais lento)
ALVO_SR = 16000           # Whisper trabalha em 16 kHz
BLOCO_MIN_S = 18          # tamanho do bloco enviado para transcrição...
BLOCO_MAX_S = 25          # ...cortado no ponto mais silencioso entre MIN e MAX
IDIOMAS = {"Português": "pt", "Inglês": "en", "Espanhol": "es", "Automático": None}

if getattr(sys, "frozen", False):
    BASE_DIR = os.path.dirname(sys.executable)
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PASTA_MODELOS = os.path.join(BASE_DIR, "modelos")


def pasta_documentos():
    """Pasta 'Documentos' real do Windows (funciona mesmo se estiver no OneDrive)."""
    try:
        import ctypes
        from ctypes import wintypes

        buf = ctypes.create_unicode_buffer(wintypes.MAX_PATH)
        ctypes.windll.shell32.SHGetFolderPathW(None, 5, None, 0, buf)  # CSIDL_PERSONAL
        if buf.value and os.path.isdir(buf.value):
            return buf.value
    except Exception:
        pass
    return os.path.join(os.path.expanduser("~"), "Documents")


PASTA_SAIDA = os.path.join(pasta_documentos(), "Transcrições")


def _palavras(txt):
    return re.findall(r"\w+", txt.lower())


def e_eco(linha, linhas):
    """True se uma fala do microfone ('Eu') for só o som das caixas vazando:
    mesma hora e maioria das palavras igual a uma fala dos Participantes."""
    ini, fim, rot, txt = linha
    if rot != "Eu":
        return False
    ctx = " ".join(t for (i, f, r, t) in linhas
                   if r == "Participantes" and i < fim + 3 and f > ini - 3)
    pal, ref = _palavras(txt), set(_palavras(ctx))
    if not pal or not ref:
        return False
    iguais = sum(1 for p in pal
                 if p in ref or difflib.get_close_matches(p, ref, 1, 0.75))
    return iguais / len(pal) >= 0.5


def fmt_tempo(seg):
    seg = int(seg)
    return f"{seg // 3600:02d}:{seg % 3600 // 60:02d}:{seg % 60:02d}"


def para_16k(audio, sr):
    """Converte áudio mono float32 de `sr` para 16 kHz."""
    if sr == ALVO_SR or len(audio) == 0:
        return audio.astype(np.float32)
    if sr % ALVO_SR == 0:  # ex.: 48000 -> 16000: média de blocos (filtro simples)
        r = sr // ALVO_SR
        n = len(audio) // r * r
        return audio[:n].reshape(-1, r).mean(axis=1).astype(np.float32)
    n_out = int(len(audio) * ALVO_SR / sr)
    x_old = np.linspace(0, 1, len(audio), endpoint=False)
    x_new = np.linspace(0, 1, n_out, endpoint=False)
    return np.interp(x_new, x_old, audio).astype(np.float32)


# ----------------------------------------------------------- captura -------
class Fonte:
    """Um stream de áudio (microfone ou loopback) com linha do tempo contínua.

    O loopback do Windows não entrega nada quando não há som tocando, então
    preenchemos os buracos com silêncio usando o relógio — assim os tempos
    das falas de "Eu" e "Participantes" continuam alinhados.
    """

    def __init__(self, pa, info, rotulo, t0):
        self.rotulo = rotulo
        self.sr = int(info["defaultSampleRate"])
        self.canais = max(1, min(2, int(info["maxInputChannels"])))
        self.t0 = t0
        self.lock = threading.Lock()
        self.pedacos = []
        self.recebidas = 0       # amostras (taxa nativa) desde o início, incl. preenchimento
        self.inicio_buffer = 0   # amostra correspondente ao começo do buffer atual
        self.stream = pa.open(
            format=pyaudio.paInt16,
            channels=self.canais,
            rate=self.sr,
            input=True,
            input_device_index=info["index"],
            frames_per_buffer=int(self.sr * 0.1),
            stream_callback=self._callback,
        )

    def _callback(self, dados, frames, info_tempo, status):
        arr = np.frombuffer(dados, dtype=np.int16).astype(np.float32) / 32768.0
        if self.canais > 1:
            arr = arr.reshape(-1, self.canais).mean(axis=1)
        esperado = int((time.monotonic() - self.t0) * self.sr)
        with self.lock:
            buraco = esperado - (self.recebidas + len(arr))
            if buraco > self.sr // 2:  # mais de 0,5 s sem dados -> silêncio
                self.pedacos.append(np.zeros(buraco, dtype=np.float32))
                self.recebidas += buraco
            self.pedacos.append(arr)
            self.recebidas += len(arr)
        return (None, pyaudio.paContinue)

    def duracao_buffer(self):
        with self.lock:
            return (self.recebidas - self.inicio_buffer) / self.sr

    def retirar(self, final=False):
        """Retira um bloco do buffer, cortando no trecho mais silencioso.
        Devolve (audio_16k, inicio_em_segundos) ou None."""
        with self.lock:
            if not self.pedacos:
                return None
            audio = np.concatenate(self.pedacos)
            inicio = self.inicio_buffer
            if final:
                corte = len(audio)
            else:
                a, b = int(BLOCO_MIN_S * self.sr), int(BLOCO_MAX_S * self.sr)
                janela = int(0.1 * self.sr)
                trecho = audio[a:b]
                n = len(trecho) // janela
                if n == 0:
                    corte = len(audio)
                else:
                    energia = (trecho[: n * janela].reshape(n, janela) ** 2).mean(axis=1)
                    corte = a + int(np.argmin(energia)) * janela + janela // 2
            resto = audio[corte:]
            self.pedacos = [resto] if len(resto) else []
            self.inicio_buffer = inicio + corte
        return para_16k(audio[:corte], self.sr), inicio / self.sr

    def fechar(self):
        try:
            self.stream.stop_stream()
            self.stream.close()
        except Exception:
            pass


# ----------------------------------------------------------- sessão --------
class Sessao:
    def __init__(self, idioma_nome):
        self.inicio = datetime.now()
        self.fim = None
        self.idioma_nome = idioma_nome
        self.idioma = IDIOMAS[idioma_nome]
        self.linhas = []  # (segundos, rotulo, texto)
        self.lock = threading.Lock()
        self.encerrada = False
        os.makedirs(PASTA_SAIDA, exist_ok=True)
        base = os.path.join(PASTA_SAIDA, f"{self.inicio:%Y-%m-%d %Hh%M} - Reunião")
        self.arquivo, n = base + ".md", 2
        while os.path.exists(self.arquivo):
            self.arquivo, n = f"{base} ({n}).md", n + 1
        self.salvar()

    def adicionar(self, novas):
        with self.lock:
            self.linhas.extend(novas)
            self.linhas.sort(key=lambda l: l[0])
        self.salvar()

    def linhas_finais(self):
        """Linhas ordenadas, sem os ecos (fala do PC captada pelo microfone)."""
        with self.lock:
            linhas = list(self.linhas)
        return [l for l in linhas if not e_eco(l, linhas)]

    def salvar(self):
        linhas = self.linhas_finais()
        fim = self.fim
        cab = [
            f"# Reunião — {self.inicio:%d/%m/%Y %H:%M}",
            "",
            f"- **Início:** {self.inicio:%d/%m/%Y %H:%M:%S}",
        ]
        if fim:
            cab += [
                f"- **Fim:** {fim:%d/%m/%Y %H:%M:%S}",
                f"- **Duração:** {fmt_tempo((fim - self.inicio).total_seconds())}",
            ]
        else:
            cab += ["- **Status:** gravando…"]
        cab += [f"- **Idioma:** {self.idioma_nome}", "", "## Transcrição", ""]
        corpo = []
        anterior = None
        for seg, _, rot, txt in linhas:
            if rot == anterior and corpo:
                corpo[-1] += " " + txt  # junta falas seguidas da mesma pessoa
            else:
                corpo.append(f"**[{fmt_tempo(seg)}] {rot}:** {txt}")
            anterior = rot
        if not corpo:
            corpo = ["_(nenhuma fala transcrita ainda)_"]
        conteudo = "\n".join(cab) + "\n" + "\n\n".join(corpo) + "\n"
        tmp = self.arquivo + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(conteudo)
        os.replace(tmp, self.arquivo)


class Gravacao:
    """Captura das duas fontes + fatiamento em blocos para a fila."""

    def __init__(self, fila, sessao, ao_erro):
        self.fila = fila
        self.sessao = sessao
        self.pa = pyaudio.PyAudio()
        self.parar_evt = threading.Event()
        t0 = time.monotonic()
        self.fontes = []
        avisos = []

        wasapi = self.pa.get_host_api_info_by_type(pyaudio.paWASAPI)
        try:
            mic = self.pa.get_device_info_by_index(wasapi["defaultInputDevice"])
            self.fontes.append(Fonte(self.pa, mic, "Eu", t0))
        except Exception as e:
            avisos.append(f"Microfone indisponível: {e}")
        try:
            loop = self.pa.get_default_wasapi_loopback()
            self.fontes.append(Fonte(self.pa, loop, "Participantes", t0))
        except Exception as e:
            avisos.append(f"Som do computador indisponível: {e}")

        if not self.fontes:
            self.pa.terminate()
            raise RuntimeError("\n".join(avisos) or "Nenhum dispositivo de áudio.")
        if avisos:
            ao_erro("\n".join(avisos))
        for f in self.fontes:
            f.stream.start_stream()
        self.thread = threading.Thread(target=self._laco, daemon=True)
        self.thread.start()

    def _laco(self):
        while not self.parar_evt.wait(1.0):
            for f in self.fontes:
                if f.duracao_buffer() >= BLOCO_MAX_S:
                    self._enviar(f, final=False)

    def _enviar(self, fonte, final):
        r = fonte.retirar(final=final)
        if r is None:
            return
        audio, inicio = r
        if len(audio) < ALVO_SR * 0.5:
            return
        if np.sqrt(np.mean(audio ** 2)) < 2e-4:  # bloco praticamente mudo
            return
        self.fila.put(("bloco", self.sessao, fonte.rotulo, audio, inicio))

    def parar(self):
        self.parar_evt.set()
        self.thread.join()
        for f in self.fontes:
            f.fechar()
        for f in self.fontes:
            self._enviar(f, final=True)
        self.pa.terminate()
        self.sessao.fim = datetime.now()
        self.fila.put(("finalizar", self.sessao))


# ------------------------------------------------------- transcrição -------
class Transcritor(threading.Thread):
    def __init__(self, fila, eventos):
        super().__init__(daemon=True)
        self.fila = fila
        self.eventos = eventos  # fila para a interface
        self.modelo = None
        self.ocupado = False

    def _carregar(self):
        from faster_whisper import WhisperModel

        self.eventos.put(("status", f"Carregando modelo '{MODELO}' (1ª vez baixa da internet)…"))
        os.makedirs(PASTA_MODELOS, exist_ok=True)
        try:
            import ctranslate2

            if ctranslate2.get_cuda_device_count() > 0:
                m = WhisperModel(MODELO, device="cuda", compute_type="int8_float32",
                                 download_root=PASTA_MODELOS)
                teste = (np.random.randn(ALVO_SR * 2) * 0.01).astype(np.float32)
                segs, _ = m.transcribe(teste, language="pt")
                list(segs)  # força rodar de fato na GPU (detecta DLLs CUDA ausentes)
                self.eventos.put(("status", "Pronto (GPU)"))
                return m
        except Exception:
            pass
        m = WhisperModel(MODELO, device="cpu", compute_type="int8",
                         cpu_threads=os.cpu_count() or 4, download_root=PASTA_MODELOS)
        self.eventos.put(("status", "Pronto (CPU)"))
        return m

    def run(self):
        try:
            self.modelo = self._carregar()
        except Exception as e:
            self.eventos.put(("erro", f"Falha ao carregar o modelo:\n{e}"))
            return
        self.eventos.put(("pronto",))
        while True:
            item = self.fila.get()
            self.ocupado = True
            try:
                if item[0] == "bloco":
                    _, sessao, rotulo, audio, inicio = item
                    segs, _ = self.modelo.transcribe(
                        audio,
                        language=sessao.idioma,
                        beam_size=1,
                        vad_filter=True,
                        vad_parameters={"min_silence_duration_ms": 500},
                        condition_on_previous_text=False,
                    )
                    novas = [(inicio + s.start, inicio + s.end, rotulo, s.text.strip())
                             for s in segs if s.text.strip()]
                    if novas:
                        sessao.adicionar(novas)
                        self.eventos.put(("texto", sessao, novas))
                elif item[0] == "finalizar":
                    sessao = item[1]
                    sessao.encerrada = True
                    sessao.salvar()
                    self.eventos.put(("finalizada", sessao))
            except Exception as e:
                self.eventos.put(("erro", f"Erro na transcrição: {e}"))
            finally:
                self.ocupado = False
                self.fila.task_done()


# ---------------------------------------------------------- interface ------
class App:
    def __init__(self, root):
        self.root = root
        root.title("Transcritor de Reuniões")
        root.geometry("620x520")
        root.minsize(480, 380)

        self.fila = queue.Queue()
        self.eventos = queue.Queue()
        self.gravacao = None
        self.sessao = None
        self.modelo_pronto = False

        topo = ttk.Frame(root, padding=12)
        topo.pack(fill="x")
        self.btn = tk.Button(topo, text="●  INICIAR", font=("Segoe UI", 14, "bold"),
                             bg="#2e7d32", fg="white", activebackground="#1b5e20",
                             activeforeground="white", relief="flat", padx=18, pady=8,
                             command=self.alternar, state="disabled")
        self.btn.pack(side="left")
        info = ttk.Frame(topo)
        info.pack(side="left", padx=14)
        self.lbl_tempo = ttk.Label(info, text="00:00:00", font=("Consolas", 20))
        self.lbl_tempo.pack(anchor="w")
        self.lbl_status = ttk.Label(info, text="Iniciando…", foreground="#555")
        self.lbl_status.pack(anchor="w")

        direita = ttk.Frame(topo)
        direita.pack(side="right")
        ttk.Label(direita, text="Idioma:").pack(anchor="e")
        self.idioma = tk.StringVar(value="Português")
        self.cb = ttk.Combobox(direita, textvariable=self.idioma, values=list(IDIOMAS),
                               state="readonly", width=12)
        self.cb.pack(anchor="e")
        ttk.Button(direita, text="Abrir pasta", command=self.abrir_pasta).pack(anchor="e", pady=(6, 0))

        self.txt = tk.Text(root, wrap="word", font=("Segoe UI", 10), padx=8, pady=8,
                           state="disabled", relief="flat", bg="#fafafa")
        self.txt.tag_configure("Eu", foreground="#1565c0", font=("Segoe UI", 10, "bold"))
        self.txt.tag_configure("Participantes", foreground="#6a1b9a", font=("Segoe UI", 10, "bold"))
        self.txt.tag_configure("info", foreground="#888", font=("Segoe UI", 9, "italic"))
        self.txt.pack(fill="both", expand=True, padx=12, pady=(0, 12))

        self.transcritor = Transcritor(self.fila, self.eventos)
        self.transcritor.start()
        root.protocol("WM_DELETE_WINDOW", self.fechar)
        self.root.after(200, self.processar_eventos)
        self.root.after(500, self.tique)

    # --- ações
    def alternar(self):
        if self.gravacao is None:
            self.iniciar()
        else:
            self.parar()

    def iniciar(self):
        sessao = Sessao(self.idioma.get())
        try:
            self.gravacao = Gravacao(self.fila, sessao,
                                     lambda m: self.eventos.put(("aviso", m)))
        except Exception as e:
            os.remove(sessao.arquivo)
            messagebox.showerror("Erro", f"Não foi possível gravar:\n{e}")
            return
        self.sessao = sessao
        self.txt.configure(state="normal")
        self.txt.delete("1.0", "end")
        self.txt.configure(state="disabled")
        self.escrever_info(f"Gravando → {os.path.basename(sessao.arquivo)}")
        self.btn.configure(text="■  PARAR", bg="#c62828", activebackground="#8e0000")
        self.cb.configure(state="disabled")

    def parar(self):
        g, self.gravacao = self.gravacao, None
        self.btn.configure(state="disabled")
        g.parar()
        self.escrever_info("Sessão encerrada. Finalizando transcrição…")
        self.btn.configure(text="●  INICIAR", bg="#2e7d32", activebackground="#1b5e20",
                           state="normal")
        self.cb.configure(state="readonly")

    def abrir_pasta(self):
        os.makedirs(PASTA_SAIDA, exist_ok=True)
        os.startfile(PASTA_SAIDA)

    def fechar(self):
        if self.gravacao is not None:
            self.parar()
        if self.fila.unfinished_tasks:
            if "--teste" not in sys.argv and not messagebox.askyesno(
                "Ainda transcrevendo",
                "Ainda há áudio sendo transcrito. Esperar terminar antes de fechar?\n\n"
                "Sim = esperar e fechar sozinho  |  Não = fechar agora (perde o final)"):
                self.root.destroy()
                return
            self.lbl_status.configure(text="Terminando a transcrição para fechar…")
            self.btn.configure(state="disabled")
            self._esperar_e_fechar()
        else:
            self.root.destroy()

    def _esperar_e_fechar(self):
        if self.fila.unfinished_tasks:
            self.root.after(500, self._esperar_e_fechar)
        else:
            self.root.destroy()

    # --- interface
    def escrever_info(self, msg):
        self.txt.configure(state="normal")
        self.txt.insert("end", msg + "\n\n", "info")
        self.txt.configure(state="disabled")
        self.txt.see("end")

    def mostrar_sessao(self, sessao):
        """Redesenha a transcrição da sessão (já sem ecos)."""
        self.txt.configure(state="normal")
        self.txt.delete("1.0", "end")
        self.txt.insert("end", f"Gravando → {os.path.basename(sessao.arquivo)}\n\n", "info")
        for seg, _, rot, texto in sessao.linhas_finais():
            self.txt.insert("end", f"[{fmt_tempo(seg)}] {rot}: ", rot)
            self.txt.insert("end", texto + "\n")
        self.txt.configure(state="disabled")
        self.txt.see("end")

    def tique(self):
        if self.gravacao is not None:
            seg = (datetime.now() - self.sessao.inicio).total_seconds()
            self.lbl_tempo.configure(text=fmt_tempo(seg))
            pend = self.fila.unfinished_tasks
            self.lbl_status.configure(
                text="Gravando…" + (f"  ({pend} bloco(s) na fila)" if pend > 1 else ""))
        elif self.modelo_pronto:
            pend = self.fila.unfinished_tasks
            self.lbl_status.configure(
                text=f"Transcrevendo o restante… ({pend})" if pend else "Pronto")
        self.root.after(500, self.tique)

    def processar_eventos(self):
        try:
            while True:
                ev = self.eventos.get_nowait()
                tipo = ev[0]
                if tipo == "status":
                    self.lbl_status.configure(text=ev[1])
                elif tipo == "pronto":
                    self.modelo_pronto = True
                    self.btn.configure(state="normal")
                    if "--teste" in sys.argv:  # autoteste: grava 30 s e fecha
                        self.iniciar()
                        self.root.after(30000, self.fechar)
                elif tipo == "texto":
                    sessao = ev[1]
                    if sessao is self.sessao:
                        self.mostrar_sessao(sessao)
                elif tipo == "finalizada":
                    sessao = ev[1]
                    if sessao is self.sessao and self.gravacao is None:
                        self.escrever_info(f"✔ Arquivo salvo: {sessao.arquivo}")
                elif tipo == "aviso":
                    self.escrever_info("⚠ " + ev[1])
                elif tipo == "erro":
                    self.lbl_status.configure(text="Erro — veja a mensagem")
                    messagebox.showerror("Erro", ev[1])
        except queue.Empty:
            pass
        self.root.after(200, self.processar_eventos)


def main():
    root = tk.Tk()
    try:
        from ctypes import windll
        windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()

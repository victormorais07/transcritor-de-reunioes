# 🎙️ Transcritor de Reuniões

**Grave e transcreva suas reuniões direto no seu PC: sem bot na chamada, sem assinatura, sem enviar seu áudio para lugar nenhum.**

Você clica em **Iniciar** quando a reunião começa e em **Parar** quando termina. O programa entrega um arquivo Markdown organizado, com data, horário, duração e a transcrição separada por quem falou: **você** ou **os outros participantes**.

Funciona com **Microsoft Teams, Google Meet, Zoom, Discord, Slack** ou qualquer coisa que toque som no computador, porque ele escuta o áudio do próprio Windows e não depende de integração com nenhum aplicativo.

---

## ✨ Destaques

| | |
|---|---|
| 🔒 **100% local e privado** | A transcrição é feita no seu computador com o Whisper. Nada vai para a nuvem. |
| 💸 **Gratuito** | Sem API paga, sem limite de minutos, sem plano. |
| 🗣️ **Separa quem fala** | Seu microfone aparece como **Eu** e o som da chamada como **Participantes**. |
| 👻 **Invisível na reunião** | Nenhum "bot gravador" entra na chamada. |
| 📝 **Saída em Markdown** | Abre no Notion, Obsidian, VS Code ou qualquer editor de texto. |
| ⏱️ **Ao vivo** | A transcrição vai aparecendo na janela enquanto você grava. |
| 🔇 **Filtro de eco** | Se você usa caixa de som, ele descarta as falas duplicadas que o microfone capta. |
| 🌎 **Vários idiomas** | Português, inglês, espanhol ou detecção automática. |

---

## 📖 Manual de uso

### 1. Abrir o programa

Dê dois cliques em **`Transcritor de Reunioes.exe`** (ou no atalho da Área de Trabalho).

No início, o status mostra *"Carregando modelo…"*. Em alguns segundos ele muda para **Pronto (CPU)** ou **Pronto (GPU)** e o botão **● INICIAR** fica verde.

### 2. Escolher o idioma

No canto superior direito, selecione o idioma da reunião. O padrão é **Português**. Use **Automático** só em reuniões que misturam idiomas, porque fixar o idioma deixa a transcrição mais precisa.

### 3. Iniciar a gravação

Entre na reunião e clique em **● INICIAR**.

- O botão fica vermelho (**■ PARAR**) e o cronômetro começa a contar.
- O arquivo é criado na hora em `Documentos\Transcrições`.
- As falas começam a aparecer na janela com uns **20 a 30 segundos de atraso**. Isso é normal, porque ele transcreve em blocos.

### 4. Parar

Clique em **■ PARAR**. A sessão é encerrada e o programa termina de transcrever o último trecho (*"Transcrevendo o restante…"*). Quando aparecer **✔ Arquivo salvo**, o `.md` está completo, com horário de fim e duração.

### 5. Gravar outra sessão

Clique em **● INICIAR** de novo. Cada sessão gera **um arquivo novo**, e a anterior não é alterada.

### 6. Encontrar os arquivos

Clique em **Abrir pasta** ou vá em:

```
Documentos\
└── Transcrições\
    ├── 2026-11-25 14h30 - Reunião.md
    ├── 2026-11-25 16h05 - Reunião.md
    └── 2026-11-26 09h00 - Reunião.md
```

Os nomes começam pela data, então ficam em ordem cronológica. Se quiser, renomeie o final, por exemplo `2026-11-25 14h30 - Planejamento Q1.md`.

### Exemplo de arquivo gerado

```markdown
# Reunião — 25/11/2026 14:30

- **Início:** 25/11/2026 14:30:05
- **Fim:** 25/11/2026 15:02:11
- **Duração:** 00:32:06
- **Idioma:** Português

## Transcrição

**[00:00:12] Participantes:** Bom dia a todos. Vamos começar a reunião de planejamento.
O primeiro ponto da pauta é o orçamento do próximo trimestre.

**[00:00:31] Eu:** Bom dia! Antes disso, conseguimos revisar os números de outubro?

**[00:00:38] Participantes:** Sim, já estão na planilha compartilhada.
```

---

## 💡 Dicas para uma boa transcrição

- 🎧 **Use fone de ouvido.** É o que mais melhora o resultado: o microfone pega só a sua voz e não o som da chamada.
- 🔊 **Escolha os dispositivos antes de iniciar.** O programa usa o microfone e a saída de som **padrão do Windows** no momento do clique. Se trocar de fone, troque antes de clicar em Iniciar.
- 🎵 **Evite outros sons no PC** (música, vídeos), porque tudo que toca no computador entra como "Participantes".
- ❌ **Pode fechar a janela gravando.** Ele para a sessão, termina a transcrição e salva antes de fechar.

---

## ❓ Problemas comuns

| Sintoma | O que fazer |
|---|---|
| Não aparece nada do "Eu" | Confira se o microfone certo é o **padrão** em *Configurações → Sistema → Som → Entrada*. |
| Não aparece nada dos "Participantes" | Confira se a reunião está tocando no dispositivo de **saída padrão**. |
| Falas aparecem duplicadas | O microfone está captando as caixas de som. Use fone, ou abaixe o volume. |
| "Bloco(s) na fila" só aumenta | O PC está mais lento que a fala. Troque o modelo para `base` (veja *Configuração*). |
| Palavras erradas em termos técnicos | Use o modelo `medium` se o PC aguentar. |

---

## ⚙️ Como funciona por dentro

```
 Microfone ──┐                        ┌─► "Eu"
             ├─► blocos de ~20 s ─► Whisper ─┤          ─► filtro de eco ─► .md
 Som do PC ──┘   (corte no silêncio)          └─► "Participantes"
 (loopback)
```

1. **Captura**: usa a API **WASAPI** do Windows (via [PyAudioWPatch](https://github.com/s0d3s/PyAudioWPatch)) para gravar ao mesmo tempo o microfone e o *loopback* da saída de som.
2. **Linha do tempo**: quando nada está tocando, o loopback não envia dados. O programa preenche esses intervalos com silêncio para manter o horário das falas alinhado entre as duas fontes.
3. **Fatiamento**: o áudio é cortado em blocos de 18 a 25 s, sempre no ponto mais silencioso, para não partir palavras ao meio.
4. **Transcrição**: [faster-whisper](https://github.com/SYSTRAN/faster-whisper) com o modelo `small`, que usa a GPU se houver CUDA e, se não, roda na CPU em int8. O filtro VAD ignora trechos sem voz.
5. **Filtro de eco**: uma fala do "Eu" é descartada quando a maioria das palavras dela coincide com uma fala dos "Participantes" no mesmo momento.
6. **Salvamento**: o `.md` é reescrito a cada bloco transcrito, então mesmo um fechamento inesperado preserva quase tudo.

---

## 🛠️ Para desenvolvedores

### Rodar a partir do código

Requer **Windows** e **Python 3.10+**.

```powershell
git clone <url-deste-repositorio>
cd transcritor-de-reunioes
python -m venv .venv
.\.venv\Scripts\pip install -r requirements.txt
.\.venv\Scripts\python transcritor.py
```

Na primeira execução, o modelo (cerca de 480 MB) é baixado para a pasta `modelos/`.

### Gerar o executável

```powershell
.\build.ps1
```

O resultado fica em `dist\Transcritor de Reunioes\`, com o modelo já incluído para funcionar offline. Para usar em outro PC, copie essa pasta inteira.

### Configuração

No início de [`transcritor.py`](transcritor.py):

| Variável | Padrão | Descrição |
|---|---|---|
| `MODELO` | `small` | `tiny`, `base`, `small` ou `medium` (maior = mais preciso e mais lento) |
| `BLOCO_MIN_S` / `BLOCO_MAX_S` | `18` / `25` | Tamanho dos blocos enviados para transcrição |
| `IDIOMAS` | PT, EN, ES, Auto | Idiomas que aparecem na lista |
| `PASTA_SAIDA` | `Documentos\Transcrições` | Onde os arquivos são salvos |

### Estrutura

```
transcritor.py     # programa completo (captura, transcrição, interface)
build.ps1          # gera o executável com PyInstaller
requirements.txt   # dependências
```

---

## ⚠️ Aviso

Grave reuniões apenas com o conhecimento e o consentimento dos participantes e respeite as leis e políticas da sua empresa sobre gravação.

---

Feito por **Victor Morais**.

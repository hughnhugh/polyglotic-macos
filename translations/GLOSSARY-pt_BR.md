# Our Portuguese (Brazil) words

The app's own terms in Brazilian Portuguese (`pt_BR`), used consistently across every string (Portugal's Windows reads it too). Reviewed in projects 852 and 863 on 2026-11-24 and refreshed for 0.1.12 in project 971: adjust a term here first, then every string using it.

Style & register:
- Friendly, clear, idiomatic Brazilian Portuguese using "você" (and "nós" / "Fale conosco", never mixing "a gente").
- Infinitive for buttons/actions (`Entrar`, `Iniciar legendas`, `Travar tudo`), imperative for direct guidance (`Segure {key} e fale`, `Escolha um idioma`).
- Clean UI grammar: `em um` / `em uma` over colloquial `num` / `numa`; `ativar` / `desativar` (`Ativado` / `Desativado`) for software settings and toggles; `app` / `apps` consistently (reserving `Aplicativos` for macOS's Applications folder and Windows' `Aplicativos de inicialização`).
- Em-dash (` — `) or colon (`:`) instead of raw ASCII ` - `; `"aspas"` (straight quotes matching the file convention); Polyglotic, Plus, Lite, Anki, Windows, macOS, HSK stay as they are.
- Qt `pt_BR` plural rule (`n > 1`): form 0 handles `0` and `1` (strict singular, e.g. `o último %Ln minuto`, never `os últimos %Ln minuto`); form 1 handles `2+` (`os últimos %Ln minutos`).

| English | Português | Note |
|---|---|---|
| caption | legenda | verb: `legendar` |
| caption window | janela de legendas | |
| finished caption | legenda final | won't change anymore (never `legenda concluída`) |
| Steady | Estável | caption timing |
| Quick preview | Prévia | caption timing |
| Live updates | Ao vivo | caption timing |
| speaking pace | ritmo da fala | compact unit: `pal/min` |
| caption info | dados da legenda | source, language, time and speaking pace |
| Long lines | Linhas longas | controls how original and translated lines are arranged |
| Display new lines / Grouped | Linha por linha / Linhas agrupadas | interleave original and translated lines / show all original lines first |
| Whole captions | Legendas inteiras | caption timing |
| Instant | Instantâneo | caption timing |
| Calm | Calmo | caption timing |
| transcript | transcrição | |
| translation | tradução | |
| Translate into | Traduzir para | |
| Original only | Só o original | |
| Detect | Detectar | |
| spoken language | idioma falado | |
| source (audio) | fonte de áudio | in system/audio lists |
| source (caption header) | origem | app name / "Você" over a caption; avoids ambiguity with `fonte` (font) |
| This PC / This Mac | Este PC / Este Mac | |
| Everything the PC plays | Tudo o que o PC toca | use `tocar` consistently (not `reproduzir`) |
| Everything else | Todo o resto | Home switch: `Legendar também os outros sons` |
| quiet (no audio playing) | sem som | Home status paired with `tocando` |
| muted (audio muted) | no mudo | Windows/macOS PT-BR idiom |
| Quiet view | Modo discreto | low-distraction grey/gold caption mode (not `Visão tranquila`) |
| Quiet (colour palette) | Discreto | colour preset |
| Muted (vibrance) | Suaves | slider end paired with `Vivas` |
| Preset | Predefinição | |
| Helpers | Recursos auxiliares | preset menu group |
| Look | Aparência | |
| Word links | Ligações de palavras | singular: `ligação` (never `link` or `vínculo`) |
| Readings | Leituras | pinyin/furigana/jyutping/etc. above words |
| re-speak / re-spoken | repetir / repetida | hold key and repeat what the other person said |
| dictation | ditado | |
| lookup | consulta | verb "look up": `consultar` (never `busca`) |
| deck | baralho | Anki's Portuguese word |
| known / ignored / new | conhecida / ignorada / nova | word statuses |
| Repeated words | Palavras recorrentes | new words the learner has heard several times |
| saved sentences | frases salvas | saved selections from captions |
| category | categoria | |
| level | nível | |
| listening allowance | cota de escuta | |
| plan / pass | plano / passe | |
| Lock all / Unlock | Travar tudo / Destravar | |
| Hide all | Ocultar tudo | |
| Resume | Retomar | |
| tray | bandeja | Windows notification area |
| hotkeys | atalhos | |
| invite code | código de convite | |
| Sign in / Sign out | Entrar / Sair da conta | distinct from `Quit` (`Sair`) |
| Signed in / Not signed in | Sessão iniciada / Sessão não iniciada | distinct from `Not connected` (`Sem conexão`) and `Not plugged in` (`Desconectado`) |
| learning data | dados de aprendizado | |
| Home | Início | page |
| Words | Palavras | page |
| Learning | Aprendizado | page |
| Settings | Configurações | page |
| Help | Ajuda | page |
| Account | Conta | page |

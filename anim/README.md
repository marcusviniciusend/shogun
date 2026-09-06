# anim — animação do kanji 将軍 em Remotion

Projeto Remotion que gera a animação do 将軍 sendo escrito a pincel, usada no
splash e no indicador de "pensando" do cliente desktop.

**Não faz parte do build do app.** Ele roda à mão, quando o desenho ou as cores
mudam, e o resultado é copiado para `desktop/src/assets/`. Manter aqui é o que
permite regerar os vídeos em vez de tratá-los como binários órfãos.

## Composições — uma por tema do app

A cor fica **gravada no vídeo**, não no CSS, então cada tema precisa do seu
render. Os valores espelham o kanji estático do cabeçalho em
`desktop/src/App.css`.

| id | cor | tamanho | duração |
| --- | --- | --- | --- |
| `SplashWashi` | sumi `#211e1a` | 800x400 | 168 frames @30fps (5,6s) |
| `SplashSumi` | bengara claro `#d4664f` | 800x400 | 168 frames |
| `IndicadorWashi` | sumi `#211e1a` | 320x160 | 66 frames (2,2s) |
| `IndicadorSumi` | bengara claro `#d4664f` | 320x160 | 66 frames |

Fases do splash: escrita 8–104, sustenta até 128, desescreve 128–160.
Do indicador: escrita 2–40, sustenta até 48, desescreve 48–63.

Há também `SamuraiCorrendo` (400x280), usada para extrair a folha de sprites do
samurai — o app consome o PNG, não este vídeo.

## Renderizar

```bash
cd anim
npm install

npx remotion render SplashWashi    out/splash-washi.webm    --codec=vp9 --image-format=png --pixel-format=yuva420p
npx remotion render SplashSumi     out/splash-sumi.webm     --codec=vp9 --image-format=png --pixel-format=yuva420p
npx remotion render IndicadorWashi out/indicador-washi.webm --codec=vp9 --image-format=png --pixel-format=yuva420p
npx remotion render IndicadorSumi  out/indicador-sumi.webm  --codec=vp9 --image-format=png --pixel-format=yuva420p

cp out/*.webm ../desktop/src/assets/
```

As três flags são obrigatórias e não são intercambiáveis:

- `--image-format=png` — sem ela o render **recusa** o pixel format com alpha;
- `--pixel-format=yuva420p` — é o que carrega o canal alpha;
- `--codec=vp9` — VP8 também aceita alpha, mas sai ~2,5x maior no mesmo
  conteúdo (medido: indicador 44 kB em VP8 contra 17 kB em VP9).

Preview interativo: `npx remotion studio`.

`out/` é ignorado pelo git — os arquivos que o app usa vivem em
`desktop/src/assets/`, e é de lá que o bundler os pega.

## Decisões técnicas

- **Traços reais, ordem caligráfica**: os 19 paths (将 10 + 軍 9) vêm do projeto
  KanjiVG — nenhuma aproximação foi necessária (`src/kanji.ts`).
- **Stroke reveal**: `pathLength=1` + `stroke-dashoffset` interpolado por frame
  (`interpolate` + `Easing.bezier(0.35,0,0.35,1)`, acelerando no meio do gesto).
  Traços sequenciais com 12% de sobreposição; a desescrita retrai cada traço na
  ordem **inversa** — o pincel desfazendo.
- **Textura de tinta**: `feTurbulence` + `feDisplacementMap` para borda
  irregular, e duas passadas por traço — base larga translúcida (sangramento) +
  fio central denso — com peso maior nos pontos curtos, que levam mais tinta
  (`src/ShogunKanji.tsx`).
- **Timing pelo Remotion, não SMIL**: `useCurrentFrame()` em vez de `<animate>`,
  para o ciclo ser controlado pelo timeline e o render ser determinístico.

## Atribuição

Os dados dos traços vêm do **KanjiVG** (Ulrich Apel,
http://kanjivg.tagaini.net), licenciado em **CC BY-SA 3.0** — atribuição também
registrada no cabeçalho de `src/kanji.ts`. O restante do projeto segue a licença
do repositório.

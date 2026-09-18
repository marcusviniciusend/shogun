# L2 — Módulo `mobile/`

Cliente React Native (Expo). **Congelado** até pós-v1.0 do desktop.

```
mobile/
  App.tsx · index.ts · app.json
  src/
  assets/
```

## Estado

Plano de integração aprovado no PR #17, esperando o Marcus decidir o **timing
do descongelamento**. Ordem acordada quando descongelar:

1. **Token seguro** — `expo-secure-store`, com migração da chave antiga;
2. **Chat texto ponta a ponta** — espelhar o desktop: erros por tipo, 429 no
   `ApiError`, `/health`, sessão persistida;
3. **Tela Config**;
4. **Histórico / reenvio** — usar `GET /sessoes`; o histórico local vira só cache;
5. **STT/TTS** — mesmo corte do desktop: falar antes de ouvir.

## Cuidados

- Não iniciar trabalho aqui sem o descongelamento explícito.
- A revisão do contrato `abrir_app` para o mobile também está represada até lá.
- Quando descongelar, o desktop é a referência: copiar decisão, não reinventar.

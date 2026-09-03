# shared

Tipos e contratos compartilhados entre o servidor e os clientes.

A fonte da verdade são os schemas em `contracts/` (JSON Schema), a partir dos quais
são derivados os tipos TypeScript (`ts/`) e os modelos Pydantic (`python/`), de modo
que server e clients nunca saiam de sincronia.

```
shared/
├── contracts/   # JSON Schema — fonte da verdade
├── ts/          # tipos TypeScript (desktop e mobile)
└── python/      # modelos Pydantic (server)
```

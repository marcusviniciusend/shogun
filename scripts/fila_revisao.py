"""Fila de revisao consolidada — monta a mesa de revisao de uma rodada de uma vez.

O que e: um script de leitura que gera uma pagina unica em markdown com tudo
que a sessao de revisao humana precisa — branches pendentes (commits a frente,
diffstat, merge limpo ou nao, distancia do dev, link de compare, rascunho de PR
correspondente em .maestri/) e PRs abertos com seus checks, via API publica do
GitHub.

Por que: formaliza o indice que o coordenador ja produzia a mao nos arquivos
.maestri/prs-para-abrir-rodada-*.md. E a opcao B da secao 4 de
docs/escalabilidade-rodadas.md, item 3 da recomendacao priorizada (secao 6):
"um script que monta a mesa de uma vez — uma pagina unica por rodada com
diffstat, rascunho e checks — revisar N PRs numa sentada".

O script NAO abre, NAO mergeia e NAO altera nada — leitura apenas. A API do
GitHub e consultada sem token (o repositorio e publico; limite anonimo de
60 requisicoes/hora). Falha de rede ou rate limit nao derruba o script: a
secao de PRs degrada com aviso e o resto (so-git) continua.

Uso (a partir da raiz do repositorio):

    python scripts/fila_revisao.py                       # stdout
    python scripts/fila_revisao.py --offline             # pula a API de proposito
    python scripts/fila_revisao.py --no-fetch            # nao roda git fetch antes
    python scripts/fila_revisao.py --out .maestri/fila-revisao.md

Requisitos: Python 3.11+, git >= 2.38 (para git merge-tree --write-tree; a
ausencia e tratada com mensagem clara, nao com crash). Stdlib apenas.
"""

from __future__ import annotations

import argparse
import datetime
import json
import re
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

API_TIMEOUT = 10  # segundos por requisicao
USER_AGENT = "shogun-fila-revisao"  # a API do GitHub exige User-Agent


# ---------------------------------------------------------------------------
# git (I/O)
# ---------------------------------------------------------------------------

def rodar_git(args: list[str], cwd: Path | None = None) -> tuple[int, str, str]:
    """Roda um comando git e devolve (codigo, stdout, stderr) sem levantar."""
    proc = subprocess.run(
        ["git", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    return proc.returncode, proc.stdout.strip(), proc.stderr.strip()


def git_ou_falha(args: list[str], cwd: Path | None = None) -> str:
    """Roda git e aborta o script com mensagem clara se o comando falhar."""
    codigo, saida, erro = rodar_git(args, cwd)
    if codigo != 0:
        sys.exit(f"erro: git {' '.join(args)} falhou: {erro or saida}")
    return saida


def raiz_do_repo() -> Path:
    return Path(git_ou_falha(["rev-parse", "--show-toplevel"]))


def raiz_do_checkout_principal() -> Path:
    """Raiz do checkout principal, mesmo quando o script roda num worktree.

    .maestri/ e gitignored e so existe no checkout principal; um worktree
    isolado (norma do projeto) nao o enxerga pelo proprio toplevel. O
    diretorio comum do git (<principal>/.git) aponta o caminho de volta.
    """
    comum = Path(git_ou_falha(["rev-parse", "--path-format=absolute", "--git-common-dir"]))
    return comum.parent


def branches_pendentes(remoto: str = "origin") -> list[str]:
    """Branches origin/feature/* ainda nao mergeadas em origin/dev."""
    saida = git_ou_falha(
        ["branch", "-r", "--no-merged", f"{remoto}/dev", "--list", f"{remoto}/feature/*"]
    )
    nomes = []
    for linha in saida.splitlines():
        nome = linha.strip()
        if nome and "->" not in nome:
            nomes.append(nome)
    return sorted(nomes)


def merge_limpo(base: str, branch: str) -> tuple[bool | None, str]:
    """Verifica com git merge-tree --write-tree se o merge seria limpo.

    Devolve (True, "") se limpo, (False, detalhe) se conflita, e
    (None, motivo) quando nao da para saber (git antigo, erro inesperado).
    """
    codigo, saida, erro = rodar_git(["merge-tree", "--write-tree", base, branch])
    if codigo == 0:
        return True, ""
    if codigo == 1:
        # linhas apos o OID sao os nomes dos arquivos em conflito
        arquivos = [l for l in saida.splitlines()[1:] if l.strip()]
        return False, ", ".join(arquivos) if arquivos else "conflito (detalhe indisponivel)"
    if "usage:" in erro.lower() or "unknown option" in erro.lower():
        return None, "git merge-tree --write-tree indisponivel (requer git >= 2.38)"
    return None, f"merge-tree falhou (codigo {codigo}): {erro or saida}"


def coletar_branch(nome_remoto: str, remoto: str, raiz_principal: Path,
                   compare_base_url: str | None) -> dict:
    """Coleta tudo que a fila mostra sobre uma branch pendente."""
    base = f"{remoto}/dev"
    curto = nome_remoto.removeprefix(f"{remoto}/")  # ex.: feature/x

    commits = git_ou_falha(["log", "--oneline", f"{base}..{nome_remoto}"])
    diffstat = git_ou_falha(["diff", "--stat", f"{base}...{nome_remoto}"])
    atras = git_ou_falha(["rev-list", "--count", f"{nome_remoto}..{base}"])
    limpo, detalhe = merge_limpo(base, nome_remoto)

    rascunho = caminho_rascunho(raiz_principal, curto)
    return {
        "branch": curto,
        "commits": commits.splitlines(),
        "diffstat": diffstat,
        "atras": int(atras),
        "merge_limpo": limpo,
        "merge_detalhe": detalhe,
        "rascunho": rascunho,
        "compare": (
            f"{compare_base_url}/compare/dev...{curto}?expand=1"
            if compare_base_url else None
        ),
    }


# ---------------------------------------------------------------------------
# funcoes puras
# ---------------------------------------------------------------------------

def extrair_owner_repo(url_remoto: str) -> tuple[str, str] | None:
    """Extrai (owner, repo) de uma URL de remoto do GitHub.

    Aceita https://github.com/owner/repo(.git), git@github.com:owner/repo(.git)
    e ssh://git@github.com/owner/repo(.git). Devolve None se nao reconhecer.
    """
    padroes = [
        r"^https?://github\.com/([^/]+)/([^/]+?)(?:\.git)?/?$",
        r"^git@github\.com:([^/]+)/([^/]+?)(?:\.git)?$",
        r"^ssh://git@github\.com/([^/]+)/([^/]+?)(?:\.git)?/?$",
    ]
    for padrao in padroes:
        m = re.match(padrao, url_remoto.strip())
        if m:
            return m.group(1), m.group(2)
    return None


def caminho_rascunho(raiz_principal: Path, branch_curto: str) -> Path | None:
    """Caminho do rascunho .maestri/pr-pendente-<branch>.md, se existir.

    A convencao do coordenador troca as barras do nome da branch por hifens:
    feature/taxa-de-fallback -> pr-pendente-feature-taxa-de-fallback.md.
    """
    nome = "pr-pendente-" + branch_curto.replace("/", "-") + ".md"
    caminho = raiz_principal / ".maestri" / nome
    return caminho if caminho.is_file() else None


def formatar_branch(info: dict) -> list[str]:
    """Formata a secao de uma branch pendente em linhas de markdown."""
    linhas = [f"### `{info['branch']}`", ""]

    if info["merge_limpo"] is True:
        merge_txt = "limpo ✅"
    elif info["merge_limpo"] is False:
        merge_txt = f"**CONFLITO** — {info['merge_detalhe']}"
    else:
        merge_txt = f"indeterminado — {info['merge_detalhe']}"
    linhas.append(f"- Merge com `dev`: {merge_txt}")

    atras = info["atras"]
    if atras == 0:
        linhas.append("- Em dia com `origin/dev` (0 commits atras)")
    else:
        plural = "commit" if atras == 1 else "commits"
        linhas.append(
            f"- {atras} {plural} atras de `origin/dev` — a protecao estrita vai pedir *Update branch*"
        )

    if info["rascunho"]:
        linhas.append(f"- Rascunho de PR: `{info['rascunho']}`")
    else:
        linhas.append("- Rascunho de PR: nao encontrado em .maestri/")

    if info["compare"]:
        linhas.append(f"- Abrir (base `dev` fixada na URL): {info['compare']}")

    n = len(info["commits"])
    plural = "commit a frente" if n == 1 else "commits a frente"
    linhas += ["", f"Commits ({n} {plural}):", "", "```"]
    linhas += info["commits"] or ["(nenhum)"]
    linhas += ["```", "", "Diffstat contra o merge-base:", "", "```"]
    linhas += [l.strip() for l in (info["diffstat"] or "(vazio)").splitlines()]
    linhas += ["```", ""]
    return linhas


def formatar_pr(pr: dict, checks: list[dict] | None, aviso_checks: str | None) -> list[str]:
    """Formata a secao de um PR aberto em linhas de markdown."""
    base = pr.get("base", {}).get("ref", "?")
    head = pr.get("head", {}).get("ref", "?")
    numero = pr.get("number", "?")
    titulo = pr.get("title", "(sem titulo)")
    corpo = (pr.get("body") or "").strip()

    linhas = [f"### PR #{numero} — `{head}` -> `{base}`", ""]
    if base != "dev":
        linhas.append(f"- **ATENCAO: a base e `{base}`, nao `dev`** — conferir antes de qualquer coisa")
    linhas.append(f"- Titulo: {titulo}")
    linhas.append("- Corpo: preenchido" if corpo else "- Corpo: **vazio**")
    linhas.append(f"- Link: {pr.get('html_url', '')}")

    if checks is None:
        linhas.append(f"- Checks: {aviso_checks or 'nao consultados'}")
    elif not checks:
        linhas.append("- Checks: nenhum check-run no head SHA (CI ainda nao rodou?)")
    else:
        linhas.append("- Checks do head SHA:")
        for check in checks:
            conclusao = check.get("conclusion") or check.get("status") or "?"
            linhas.append(f"  - {check.get('name', '?')}: {conclusao}")
    linhas.append("")
    return linhas


def montar_markdown(
    agora: str,
    sha_dev: str,
    branches: list[dict],
    prs: list[dict] | None,
    checks_por_pr: dict[int, tuple[list[dict] | None, str | None]],
    aviso_api: str | None,
    offline: bool,
) -> str:
    """Monta a pagina inteira. Funcao pura: recebe dados, devolve markdown."""
    linhas = [
        "# Fila de revisao consolidada",
        "",
        f"Data: {agora}",
        f"`origin/dev`: `{sha_dev}`",
        f"Branches pendentes: {len(branches)} · PRs abertos: "
        + (str(len(prs)) if prs is not None else "nao consultado"),
        "",
        "> Gerado por `scripts/fila_revisao.py` (docs/escalabilidade-rodadas.md,",
        "> secao 4, opcao B). Leitura apenas — nada foi aberto nem mergeado.",
        "",
        "## Branches pendentes (origin/feature/* nao mergeadas em origin/dev)",
        "",
    ]

    if branches:
        for info in branches:
            linhas += formatar_branch(info)
    else:
        linhas += ["Nenhuma branch pendente — a mesa esta limpa.", ""]

    linhas += ["## PRs abertos", ""]
    if offline:
        linhas += ["Modo --offline: a API do GitHub nao foi consultada.", ""]
    elif prs is None:
        linhas += [
            f"**AVISO: a consulta a API do GitHub falhou** — {aviso_api}",
            "A secao acima (so-git) esta completa; ficaram de fora numero, titulo,",
            "base e checks dos PRs abertos. Rode de novo mais tarde ou use --offline",
            "para omitir este aviso de proposito.",
            "",
        ]
    elif not prs:
        linhas += ["Nenhum PR aberto.", ""]
    else:
        for pr in prs:
            checks, aviso = checks_por_pr.get(pr.get("number"), (None, aviso_api))
            linhas += formatar_pr(pr, checks, aviso)

    return "\n".join(linhas).rstrip() + "\n"


# ---------------------------------------------------------------------------
# API do GitHub (I/O)
# ---------------------------------------------------------------------------

def api_get(url: str):
    """GET anonimo na API do GitHub. Levanta as excecoes de urllib."""
    requisicao = urllib.request.Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": USER_AGENT,
        },
    )
    with urllib.request.urlopen(requisicao, timeout=API_TIMEOUT) as resposta:
        return json.load(resposta)


def descrever_erro_api(exc: Exception) -> str:
    """Transforma a excecao da API numa frase curta para o aviso."""
    if isinstance(exc, urllib.error.HTTPError):
        if exc.code == 403:
            return (
                "HTTP 403 (provavel rate limit anonimo: 60 requisicoes/hora; "
                "espere a janela virar)"
            )
        return f"HTTP {exc.code}"
    if isinstance(exc, urllib.error.URLError):
        return f"sem rede ou DNS ({exc.reason})"
    return f"{type(exc).__name__}: {exc}"


def coletar_prs_e_checks(owner: str, repo: str):
    """Busca PRs abertos e os check-runs de cada head SHA.

    Devolve (prs, checks_por_pr, aviso). prs e None quando nem a listagem
    funcionou; um PR sem checks consultaveis ganha aviso individual.
    """
    try:
        prs = api_get(f"https://api.github.com/repos/{owner}/{repo}/pulls?state=open")
    except Exception as exc:  # rede, rate limit, JSON invalido — nada derruba
        return None, {}, descrever_erro_api(exc)

    checks_por_pr: dict[int, tuple[list[dict] | None, str | None]] = {}
    for pr in prs:
        sha = pr.get("head", {}).get("sha")
        if not sha:
            checks_por_pr[pr.get("number")] = (None, "head SHA ausente na resposta")
            continue
        try:
            dados = api_get(
                f"https://api.github.com/repos/{owner}/{repo}/commits/{sha}/check-runs"
            )
            checks_por_pr[pr.get("number")] = (dados.get("check_runs", []), None)
        except Exception as exc:
            checks_por_pr[pr.get("number")] = (None, descrever_erro_api(exc))
    return prs, checks_por_pr, None


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Monta a fila de revisao consolidada em markdown (leitura apenas)."
    )
    parser.add_argument(
        "--no-fetch", action="store_true",
        help="nao rodar git fetch --prune antes de listar as branches",
    )
    parser.add_argument(
        "--offline", action="store_true",
        help="pular a API do GitHub de proposito (secao de PRs omitida)",
    )
    parser.add_argument(
        "--out", metavar="CAMINHO",
        help="escrever a pagina neste arquivo em vez de stdout "
             "(uso tipico: --out .maestri/fila-revisao.md)",
    )
    args = parser.parse_args()

    raiz_do_repo()  # falha cedo, com mensagem clara, se nao estivermos num repo git
    raiz_principal = raiz_do_checkout_principal()
    remoto = "origin"

    if not args.no_fetch:
        codigo, _, erro = rodar_git(["fetch", "--prune", remoto])
        if codigo != 0:
            print(
                f"aviso: git fetch falhou ({erro}); seguindo com o estado local "
                "das refs remotas (equivale a --no-fetch)",
                file=sys.stderr,
            )

    url_remoto = git_ou_falha(["remote", "get-url", remoto])
    owner_repo = extrair_owner_repo(url_remoto)
    compare_base_url = (
        f"https://github.com/{owner_repo[0]}/{owner_repo[1]}" if owner_repo else None
    )
    if not owner_repo:
        print(
            f"aviso: nao reconheci owner/repo na URL do remoto ({url_remoto}); "
            "links de compare e API do GitHub ficam de fora",
            file=sys.stderr,
        )

    sha_dev = git_ou_falha(["rev-parse", "--short", f"{remoto}/dev"])
    agora = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")

    branches = [
        coletar_branch(nome, remoto, raiz_principal, compare_base_url)
        for nome in branches_pendentes(remoto)
    ]

    prs: list[dict] | None = None
    checks_por_pr: dict = {}
    aviso_api: str | None = None
    if not args.offline:
        if owner_repo:
            prs, checks_por_pr, aviso_api = coletar_prs_e_checks(*owner_repo)
        else:
            aviso_api = "owner/repo nao identificado a partir do remoto"

    pagina = montar_markdown(
        agora, sha_dev, branches, prs, checks_por_pr, aviso_api, args.offline
    )

    if args.out:
        destino = Path(args.out)
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_text(pagina, encoding="utf-8")
        print(f"fila de revisao escrita em {destino}")
    else:
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass  # stdout nao reconfiguravel (ex.: redirecionado); segue como esta
        try:
            print(pagina, end="")
            sys.stdout.flush()
        except (BrokenPipeError, OSError):
            # leitor fechou o pipe cedo (ex.: | head); nao e erro do script
            sys.exit(0)


if __name__ == "__main__":
    main()
